"""
NURU V10.3h — Archon Agent : auto‑correction & raffinement post‑génération.

Analyse la réponse générée contre le contexte RAG et la raffine
via un LLM spécialisé (cloud). Détecte hallucinations, manque
de précision, et améliore la qualité.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

REFINER_SYSTEM_PROMPT = """Tu es un **relecteur‑vérificateur** spécialisé.

Ton rôle :
1. Vérifie que la réponse ci‑dessous est fidèle au CONTEXTE fourni.
2. Détecte les affirmations non étayées, les hallucinations, les contradictions.
3. Si des problèmes sont détectés, **corrige** la réponse en t'appuyant
   strictement sur le contexte. Si aucune correction n'est nécessaire,
   retourne simplement la réponse originale inchangée.

Règles :
- Ne supprime PAS de contenu valide.
- Améliore la clarté SI ET SEULEMENT SI le contexte le permet.
- Ne fais PAS de paraphrase inutile.
- Si la réponse contient des infos hors contexte, supprime‑les ou
  précise que l'info ne vient pas des documents.
- Ne cite PAS le contexte si la réponse initiale ne le faisait pas,
  sauf si l'ajout de citations améliore significativement la réponse.

Format de sortie :
- Si aucune correction : retourne exactement la réponse originale.
- Si correction : retourne la version corrigée, précédée de
  « [Corrigé] » sur la première ligne.
"""


class ArchonRefiner:
    """Agent de raffinement post‑génération.

    Prend une réponse générée + contexte RAG, utilise un LLM dédié
    pour détecter et corriger les problèmes, et retourne une version
    raffinée si nécessaire.
    """

    def __init__(
        self,
        cloud_llm: Optional[object] = None,
        local_llm: Optional[object] = None,
        enabled: bool = True,
        max_input_chars: int = 8000,
        min_confidence: float = 0.6,
    ):
        self.cloud_llm = cloud_llm
        self.local_llm = local_llm
        self.enabled = enabled
        self.max_input_chars = max_input_chars
        self.min_confidence = min_confidence
        self._stats = {"runs": 0, "corrected": 0, "errors": 0, "total_ms": 0}

    @property
    def stats(self) -> dict:
        return dict(self._stats)

    async def refine(
        self,
        response: str,
        rag_context: str = "",
        rag_score: float = 0.0,
        intent: str = "SIMPLE",
    ) -> str:
        """Analyse et raffine une réponse générée.

        Args:
            response: Réponse générée par le LLM principal.
            rag_context: Contexte RAG utilisé pour la génération.
            rag_score: Score de confiance RAG (0‑1).
            intent: Intent de la requête.

        Returns:
            Réponse raffinée (ou originale si aucune correction nécessaire).
        """
        if not self.enabled:
            return response

        # Court‑circuit : réponse trop courte, score trop bas,
        # pas de contexte RAG, ou intent SIMPLE
        if not self._should_refine(response, rag_context, rag_score, intent):
            return response

        llm = self.cloud_llm or self.local_llm
        if llm is None:
            logger.warning("ArchonRefiner: aucun LLM disponible")
            return response

        # Tronquer si trop long
        context_chunk = rag_context[:self.max_input_chars] if rag_context else ""

        t0 = time.monotonic()
        self._stats["runs"] += 1
        try:
            refined = await llm.generate(
                system=REFINER_SYSTEM_PROMPT,
                prompt=(
                    f"## CONTEXTE\n{context_chunk}\n\n"
                    f"## RÉPONSE À VÉRIFIER\n{response}\n\n"
                    f"## TÂCHE\nVérifie la réponse ci‑dessus contre le contexte. "
                    f"Corrige si nécessaire. Si tout est correct, retourne la réponse "
                    f"originale inchangée."
                ),
                max_tokens=min(len(response) + 500, 2048),
                temperature=0.1,
            )
            elapsed = int((time.monotonic() - t0) * 1000)
            self._stats["total_ms"] += elapsed

            # Vérifier si le refiner a modifié la réponse
            text = refined if isinstance(refined, str) else (refined.text if hasattr(refined, "text") else refined)

            if text.startswith("[Corrigé]"):
                self._stats["corrected"] += 1
                logger.info(
                    f"🔮 ArchonRefiner: réponse corrigée "
                    f"(durée={elapsed}ms, score_rag={rag_score:.2f})"
                )
                return text[len("[Corrigé]"):].strip()

            logger.debug(
                f"🔮 ArchonRefiner: réponse vérifiée — aucune correction "
                f"(durée={elapsed}ms)"
            )
            return response

        except Exception as e:
            self._stats["errors"] += 1
            logger.warning(f"ArchonRefiner: erreur {e}")
            return response

    def _should_refine(
        self, response: str, rag_context: str, rag_score: float, intent: str
    ) -> bool:
        """Détermine si un raffinement est pertinent."""
        if len(response) < 50:
            return False  # Trop court
        if not rag_context.strip():
            return False  # Pas de contexte à vérifier
        if rag_score < self.min_confidence and intent in ("RAG", "COMPLEX"):
            return True  # Score bas → vérification utile
        if intent in ("COMPLEX", "RAG"):
            return True  # Toujours vérifier pour RAG
        return False
