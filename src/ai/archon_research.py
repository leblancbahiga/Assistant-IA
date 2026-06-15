"""
NURU V10.3j — ResearchArchon : décomposition → recherches parallèles → synthèse.

Pour les requêtes COMPLEX, décompose la question en sous‑questions,
exécute une recherche RAG indépendante pour chacune, puis synthétise
les résultats en une réponse complète via le LLM cloud.

Usage :
  archon = ResearchArchon(cloud_llm=cloud, rag_pipeline=rag)
  answer = await archon.research("question complexe sur le climat")
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


DECOMPOSE_PROMPT = """Tu es un analyste de recherche. Décompose la question 
suivante en 2 ou 3 sous‑questions précises qui permettent de la couvrir 
complètement. Chaque sous‑question doit être indépendante et cibler un 
aspect différent.

Format : une sous‑question par ligne, sans numérotation ni préfixe.

Question : {query}
Sous‑questions :"""


SYNTHESIZE_PROMPT = """Tu es un rédacteur expert. Combine les résultats 
de recherche suivants en une réponse complète, bien structurée et fluide.

Question originale : {query}

Résultats de recherche :
{results}

Rédige une synthèse cohérente qui reprend les points essentiels de chaque 
résultat sans les répéter inutilement. Structure avec des paragraphes."""


class ResearchArchon:
    """Agent de recherche multi‑étapes pour requêtes complexes."""

    def __init__(
        self,
        cloud_llm=None,
        rag_pipeline=None,
        max_sub_queries: int = 3,
        enabled: bool = True,
    ):
        self._cloud = cloud_llm
        self._rag = rag_pipeline
        self.max_sub_queries = max_sub_queries
        self.enabled = enabled
        self.stats = {"runs": 0, "sub_queries": 0, "errors": 0, "total_ms": 0}

    async def research(self, query: str) -> str:
        """
        Pipeline complet : décomposition → recherches → synthèse.

        Retourne la réponse synthétisée, ou chaîne vide si désactivé
        ou si la décomposition ne produit rien.
        """
        if not self.enabled or not self._cloud or not self._rag:
            return ""

        t0 = time.monotonic()
        self.stats["runs"] += 1

        try:
            # Phase 1 : Décomposition
            sub_questions = await self._decompose(query)
            if not sub_questions:
                logger.info("ResearchArchon : aucune sous‑question générée")
                return ""

            self.stats["sub_queries"] += len(sub_questions)
            logger.info(
                "ResearchArchon : %d sous‑questions générées", len(sub_questions)
            )

            # Phase 2 : Recherches parallèles
            results = await self._research_parallel(sub_questions)

            # Phase 3 : Synthèse
            answer = await self._synthesize(query, sub_questions, results)
            elapsed = (time.monotonic() - t0) * 1000
            self.stats["total_ms"] += elapsed
            logger.info(
                "ResearchArchon : synthèse terminée en %dms (%d sous‑questions)",
                elapsed,
                len(sub_questions),
            )
            return answer

        except Exception as e:
            self.stats["errors"] += 1
            logger.error("ResearchArchon : erreur → %s", e)
            return ""

    async def _decompose(self, query: str) -> list[str]:
        """Décompose la question en sous‑questions via le LLM cloud."""
        prompt = DECOMPOSE_PROMPT.format(query=query[:2000])
        try:
            raw = await asyncio.to_thread(
                self._cloud.generate, prompt, 20.0
            )
        except Exception as e:
            logger.warning("ResearchArchon._decompose échec : %s", e)
            return []

        lines = [
            line.strip().lstrip("-*0123456789.). ")
            for line in raw.strip().split("\n")
            if line.strip()
        ]
        # Filtrer les lignes trop courtes ou vides
        lines = [l for l in lines if len(l) > 15]
        return lines[: self.max_sub_queries]

    async def _research_parallel(self, sub_questions: list[str]) -> list[str]:
        """Lance les recherches RAG en parallèle et retourne les synthèses."""

        async def _research_one(sq: str) -> str:
            try:
                # Phase 2a : RAG retrieval
                rag_ctx, _ = await self._rag.retrieve_primary(sq, None)
                if not rag_ctx or not rag_ctx.strip():
                    # Fallback : essayer retrieve_multi
                    rag_ctx, _, _ = await self._rag.retrieve_multi(
                        sq, "RAG", "", None
                    )
                if not rag_ctx or not rag_ctx.strip():
                    return f"## {sq}\n\nAucune source trouvée dans la base documentaire."

                # Phase 2b : Génération LLM focalisée
                focus_prompt = (
                    f"Contexte documentaire :\n{rag_ctx[:4000]}\n\n"
                    f"Question spécifique : {sq}\n\n"
                    f"Réponds uniquement à partir du contexte fourni, "
                    f"en citant les sources si possible."
                )
                result = await asyncio.to_thread(
                    self._cloud.generate, focus_prompt, 30.0
                )
                return f"## {sq}\n\n{result.strip()}"

            except Exception as e:
                logger.warning("ResearchArchon sous‑question échouée [%s] : %s", sq[:50], e)
                return f"## {sq}\n\nErreur lors de la recherche."

        tasks = [_research_one(sq) for sq in sub_questions]
        return await asyncio.gather(*tasks)

    async def _synthesize(
        self, query: str, sub_questions: list[str], results: list[str]
    ) -> str:
        """Synthétise les résultats en réponse finale."""
        results_block = "\n\n---\n\n".join(results)
        prompt = SYNTHESIZE_PROMPT.format(
            query=query, results=results_block
        )
        try:
            answer = await asyncio.to_thread(
                self._cloud.generate, prompt, 45.0
            )
            return answer.strip()
        except Exception as e:
            logger.warning("ResearchArchon._synthesize échec : %s", e)
            # Fallback : concaténer les résultats bruts
            return results_block
