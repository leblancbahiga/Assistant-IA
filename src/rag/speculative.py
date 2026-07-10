"""NURU V15 Phase 5 — Speculative RAG (Item 39, P1 #48).

Spéculation : générer une réponse RAPIDE sans RAG, pendant que la RAG
prépare le contexte en parallèle. Si les docs sont pertinents (>0.7),
on régénère avec contexte. Sinon, la réponse rapide est livrée telle quelle.

Latence perçue cible : <500 ms pour 80% des requêtes.

Architecture :
  ┌──────────────┐     parallele     ┌─────────────────┐
  │  Requête     │─────┬────────────→│ RAGEngine        │
  │  utilisateur  │     │             │ (retrieve +      │
  └──────────────┘     │             │  reranker)       │
                       │             └────────┬─────────┘
                       │                      │
                 ┌─────▼──────┐        ┌──────▼──────────┐
                 │ CloudLLM   │        │ top_score > 0.7 │
                 │ (fast,     │        └──────┬──────────┘
                 │  no RAG)   │          │         │
                 └─────┬──────┘      oui        non
                       │               │         │
                 ┌─────▼──────┐   ┌────▼───┐    ┌─▼──────────┐
                 │ fast_stream│   │Regen   │    │ deliver    │
                 │ delivered  │   │avec RAG│    │ fast_reply │
                 └────────────┘   └────────┘    └────────────┘
"""

import asyncio
import logging
import time
from typing import Any, AsyncGenerator, Optional, Tuple

logger = logging.getLogger(__name__)


class SpeculativeRAG:
    """Wrapper RAG qui exécute la spéculation : génération rapide parallélisée
    avec la RAG lourde.

    Usage:
        spec = SpeculativeRAG(rag_engine, cloud_llm)
        response, is_speculative = await spec.answer(query)
        print(f"{'[Speculative]' if is_speculative else '[RAG]'} {response}")
    """

    def __init__(
        self,
        rag_engine: Any,
        cloud_llm: Any,
        confidence_threshold: float = 0.7,
        fast_timeout: float = 3.0,
        slow_timeout: float = 15.0,
    ):
        """
        Args:
            rag_engine: Instance de RAGEngine (contient retrieve + generate)
            cloud_llm: Instance de CloudLLM pour la génération rapide
            confidence_threshold: Score minimum du top doc RAG pour régénérer (0.7)
            fast_timeout: Timeout max de la génération rapide en secondes
            slow_timeout: Timeout max de la régénération RAG en secondes
        """
        self._rag = rag_engine
        self._cloud = cloud_llm
        self._threshold = confidence_threshold
        self._fast_timeout = fast_timeout
        self._slow_timeout = slow_timeout

        # Stats
        self.stats = {
            "total": 0,
            "speculative_hits": 0,   # réponse rapide livrée sans RAG
            "rag_regenerated": 0,    # régénération avec contexte RAG
            "fast_failures": 0,      # timeout ou erreur de la génération rapide
        }

    # ─── API Publique ────────────────────────────────────────────────

    async def answer(self, query: str) -> Tuple[str, bool]:
        """Réponse spéculative : rapide sans RAG, ou complète avec RAG.

        Returns:
            (response, speculative_hit) où speculative_hit=True signifie
            que la réponse rapide a été livrée (RAG non nécessaire).
        """
        self.stats["total"] += 1

        # Lancer les deux branches en parallèle
        fast_task = asyncio.create_task(self._fast_answer(query))
        rag_task = asyncio.create_task(self._rag_retrieve(query))

        # Attendre la première réponse (fast) ou la RAG terminée
        done, pending = await asyncio.wait(
            [fast_task, rag_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        fast_done = fast_task in done
        rag_done = rag_task in done

        if fast_done:
            # La réponse rapide est disponible immédiatement
            fast_response, fast_ok = fast_task.result()
            if fast_ok:
                # Réponse rapide livrée ; laisser la RAG finir en arrière-plan
                if not rag_done:
                    await asyncio.wait([rag_task], timeout=self._slow_timeout)

                rag_result = rag_task.result() if rag_task.done() else (0.0, [])
                top_score, _ = rag_result

                if top_score >= self._threshold:
                    # RAG a trouvé des docs pertinents → régénérer avec contexte
                    logger.info(
                        "♻️ Speculative RAG : régénération avec contexte "
                        f"(top_score={top_score:.3f} ≥ {self._threshold})"
                    )
                    rag_response = await self._rag_generate(query)
                    self.stats["rag_regenerated"] += 1
                    return rag_response, False

                # RAG non nécessaire (top_score trop bas)
                logger.debug(
                    f"Speculative RAG : livraison rapide "
                    f"(top_score={top_score:.3f} < {self._threshold})"
                )
                self.stats["speculative_hits"] += 1
                return fast_response, True

        # La génération rapide a échoué → attendre la RAG
        self.stats["fast_failures"] += 1
        if not rag_done:
            await asyncio.wait([rag_task], timeout=self._slow_timeout)

        if rag_task.done():
            top_score, _ = rag_task.result()
            if top_score >= self._threshold:
                response = await self._rag_generate(query)
                self.stats["rag_regenerated"] += 1
                return response, False

        # Fallback : réponse rapide même si sub-optimale, ou erreur
        if fast_done:
            fast_response, _ = fast_task.result()
            return fast_response, True

        return "(Le service est momentanément indisponible)", False

    async def answer_stream(
        self, query: str
    ) -> AsyncGenerator[Tuple[str, bool], None]:
        """Version streaming de la réponse spéculative.

        Yield : (token, speculative_hit) où speculative_hit=True signifie
        que ce token vient du modèle rapide (sans RAG).
        """
        self.stats["total"] += 1

        # Démarrer les deux branches
        fast_gen = self._fast_stream(query)
        rag_task = asyncio.create_task(self._rag_retrieve(query))

        # Streamer la réponse rapide immédiatement
        speculative_hit = True
        fast_tokens: list[str] = []
        rag_done = False

        try:
            async for token in self._timeout_iter(fast_gen, self._fast_timeout):
                fast_tokens.append(token)
                yield token, True  # streaming immédiat

            # Si on est arrivé ici, on a une réponse rapide complète
            self.stats["speculative_hits"] += 1
        except asyncio.TimeoutError:
            # La génération rapide a timeouté → on a au moins streamé partiellement
            logger.warning("Speculative RAG : fast stream timeout")
            self.stats["fast_failures"] += 1
        except Exception as e:
            logger.warning(f"Speculative RAG : fast stream error: {e}")
            self.stats["fast_failures"] += 1

        # Attendre la RAG (déjà en cours)
        if not rag_task.done():
            await asyncio.wait([rag_task], timeout=self._slow_timeout)
            rag_done = rag_task.done()

        top_score = 0.0
        if rag_task.done():
            top_score, _ = rag_task.result()

        if top_score >= self._threshold:
            # RAG pertinente → régénérer, remplacer les tokens rapides
            logger.info(
                "♻️ Speculative RAG stream : régénération avec contexte "
                f"(top_score={top_score:.3f})"
            )
            rag_response = await self._rag_generate(query)
            self.stats["rag_regenerated"] += 1
            yield "\n\n[Contexte RAG ajouté]\n\n", False
            yield rag_response, False

    # ─── Interne : Génération rapide ─────────────────────────────────

    async def _fast_answer(self, query: str) -> Tuple[str, bool]:
        """Génère une réponse rapide SANS RAG.

        Returns:
            (response, success)
        """
        try:
            # Prompt minimal : pas de contexte RAG, seulement la requête
            fast_prompt = self._build_fast_prompt(query)

            # Utiliser CloudLLM pour la génération rapide
            tokens: list[str] = []
            async for token in self._cloud.generate_stream(
                fast_prompt, intent="RAG"
            ):
                tokens.append(token)

            response = "".join(tokens)
            return response, bool(response.strip())
        except asyncio.TimeoutError:
            logger.warning("Speculative RAG : fast answer timeout")
            return "", False
        except Exception as e:
            logger.warning(f"Speculative RAG : fast answer error: {e}")
            return "", False

    async def _fast_stream(self, query: str) -> AsyncGenerator[str, None]:
        """Stream de la réponse rapide sans RAG."""
        fast_prompt = self._build_fast_prompt(query)
        async for token in self._cloud.generate_stream(fast_prompt, intent="RAG"):
            yield token

    @staticmethod
    def _build_fast_prompt(query: str) -> str:
        """Construit un prompt minimal pour la génération rapide.

        Pas de contexte RAG, pas d'instructions complexes.
        Juste le strict nécessaire pour une réponse rapide et correcte.
        """
        return (
            "Réponds brièvement à la question suivante.\n"
            "Si tu ne connais pas la réponse, dis-le clairement.\n\n"
            f"Question: {query}\n\n"
            "Réponse:"
        )

    # ─── Interne : RAG lourde ────────────────────────────────────────

    async def _rag_retrieve(self, query: str) -> Tuple[float, Any]:
        """Exécute la RAG lourde (retrieve + reranker) en parallèle.

        Returns:
            (top_score, raw_results)
        """
        try:
            context, result = await self._rag.retrieve(query)
            top_score = result.top_score if result else 0.0
            return top_score, result
        except Exception as e:
            logger.warning(f"Speculative RAG : retrieve error: {e}")
            return 0.0, None

    async def _rag_generate(self, query: str) -> str:
        """Génère une réponse AVEC contexte RAG.

        Utilise le CloudLLM passé au constructeur (pas la RAG engine).
        """
        try:
            context, result = await self._rag.retrieve(query)

            if not context or not context.strip():
                return "(Aucun document pertinent trouvé pour cette question.)"

            # Construire un prompt RAG complet
            rag_prompt = (
                "Tu es NURU, assistant IA personnel. "
                "Réponds UNIQUEMENT à partir des documents ci-dessous.\n\n"
                "=== DOCUMENTS ===\n"
                f"{context}\n"
                "=== FIN DES DOCUMENTS ===\n\n"
                f"Question: {query}\n\n"
                "Réponse (avec citations [Source: fichier]):"
            )

            response_tokens: list[str] = []
            async for token in self._cloud.generate_stream(
                rag_prompt, intent="RAG"
            ):
                response_tokens.append(token)

            return "".join(response_tokens)
        except Exception as e:
            logger.error(f"Speculative RAG : regenerate error: {e}")
            return "(Erreur lors de la régénération avec contexte RAG)"

    # ─── Utilitaires ─────────────────────────────────────────────────

    @staticmethod
    async def _timeout_iter(async_gen: AsyncGenerator[str, None], timeout: float):
        """Wrapper asyncio.timeout pour un async generator."""
        try:
            async with asyncio.timeout(timeout):
                async for token in async_gen:
                    yield token
        except asyncio.TimeoutError:
            raise
        except Exception:
            raise

    def get_stats(self) -> dict:
        total = self.stats["total"] or 1  # évite division par zéro
        return {
            **self.stats,
            "speculative_rate": round(self.stats["speculative_hits"] / total, 3),
            "regeneration_rate": round(self.stats["rag_regenerated"] / total, 3),
        }

    def reset_stats(self) -> None:
        for k in self.stats:
            self.stats[k] = 0
