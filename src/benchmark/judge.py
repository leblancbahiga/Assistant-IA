"""V18-15 — Juge niveau 1 (déterministe) + taxonomie des hallucinations.

Citation coverage : parser les références `[SOURCE i]` de la réponse et
vérifier leur existence dans le contexte RAG fourni. ZÉRO LLM.

La taxonomie A/B/C/D attribue un label d'hallucination à partir de
(rag_context, coverage, niveau 2).

NOTE CONTRAINTE D'ACTIVATION (V18-15 spec §2.3/§7) : la couverture de citation
dépend de V18-24 (rebranchement prompt) + V18-34b (alignement format
`[SOURCE i]`). Tant que ces décisions ne sont pas implantées, la coverage
peut tendre vers ~0 indépendamment de la qualité du retrieval — le rapport
rejette alors la métrique en tant que « contrainte d'activation non
satisfaite », jamais comme un échec.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Format des sources dans le contexte RAG actif (rag_engine.py).
SOURCE_RE = re.compile(r"\[SOURCE\s+(\d+)\]")


class CitationJudge:
    """Juge niveau 1 — déterministe, zéro LLM.

    Mesure la Citation Coverage : proportion de références `[SOURCE i]`
    présentes dans la réponse qui existent effectivement dans le contexte
    fourni.
    """

    def __init__(self) -> None:
        self.source_re = SOURCE_RE

    # ── Coverage brute ───────────────────────────────────────────

    def coverage(self, response: str, rag_context: str) -> float:
        """Cite coverage = |cités ∩ disponibles| / |cités|.

        Retourne 0.0 si la réponse ne contient aucune citation.
        """
        cit = self.source_re.findall(response or "")
        available = set(self.source_re.findall(rag_context or ""))
        if not cit:
            return 0.0
        present = sum(1 for c in cit if c in available)
        return present / len(cit)

    # ── Coverage par phrase / affirmation ────────────────────────

    def annotated_affirmations(self, response: str, rag_context: str) -> dict:
        """Découpe la réponse en phrases et calcule la coverage par phrase.

        Retourne ::
            {
              "n_affirmations": int,
              "coverage": float,
              "affirmations": [
                   {"text": str, "cited": [id...], "available": [id...],
                    "coverage": float}
              ]
            }
        """
        available = set(self.source_re.findall(rag_context or ""))
        sentences = self._split_sentences(response or "")
        affirmations = []
        for sent in sentences:
            cit = self.source_re.findall(sent)
            present = sum(1 for c in cit if c in available)
            cov = (present / len(cit)) if cit else 0.0
            affirmations.append({
                "text": sent,
                "cited": cit,
                "available": sorted(available),
                "coverage": round(cov, 4),
            })
        n_cit = sum(1 for a in affirmations if a["cited"])
        overall = (sum(a["coverage"] for a in affirmations) / n_cit) if n_cit else 0.0
        return {
            "n_affirmations": len(affirmations),
            "coverage": round(overall, 4),
            "affirmations": affirmations,
        }

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        import re as _re
        sentences = _re.split(r"(?<=[.!?])\s+", text.strip())
        return [s.strip() for s in sentences if s.strip()]


# Taxonomie des hallucinations V18-15 : A / B / C / D
#   A : contexte absent (aucune source pertinente récupérée)
#   B : contexte incomplet (sources présentes mais coverage partielle / manque)
#   C : contradictoire (la réponse contredit le contexte fourni)
#   D : inventé malgré un bon contexte (coverage élevée requise mais le contenu
#       sort du contexte — invariants lexicaux dallent sur SelfEvaluator)
HALLUCINATION_LABELS = ("A", "B", "C", "D")


class HallucinationTaxonomy:
    """Attribue un label A/B/C/D à partir de (ctx, coverage, niveau 2)."""

    def classify(
        self,
        rag_context: str,
        coverage: float,
        level2: Optional[dict] = None,
    ) -> str:
        """Classification déterministe + heuristique.

        level2 : dict optionnel avec faithfulness / hallucination_score
        (de SelfEvaluator) pour affiner B vs D.
        """
        ctx = rag_context or ""
        level2 = level2 or {}

        # A — aucune source récupérée → pas de support disponible
        if not ctx.strip():
            return "A"

        if coverage < 0.5:
            # B — sources présentes mais couverture faible
            return "B"

        # C / D — coverage élevée mais le contenu peut sortir du contexte.
        # Niveau 2 (faithfulness lexical) départage B↔D affiné : un score
        # homevasseux malgré une bonne coverage indique une invention D.
        faithfulness = level2.get("faithfulness")
        if faithfulness is not None and faithfulness < 0.4:
            return "D"

        return "C" if coverage < 0.95 else "B"

    def distribution(self, labels: list[str]) -> dict[str, int]:
        """Compte les labels en A/B/C/D (0 si absent)."""
        dist = {k: 0 for k in HALLUCINATION_LABELS}
        for lab in labels:
            dist[lab] = dist.get(lab, 0) + 1
        return dist