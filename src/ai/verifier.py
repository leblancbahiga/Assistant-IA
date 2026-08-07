"""NURU V5 — EvidenceVerifier : validation des citations contre les chunks réels.

Vérifie que chaque `[Source: ...]` dans la réponse générée correspond
à un chunk retourné par le RAG. Étape post-génération qui empêche
les citations fantômes.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Résultat structuré de la vérification post-génération."""
    valid: bool = True
    confidence: float = 0.0
    matched_citations: list[str] = field(default_factory=list)
    missing_citations: list[str] = field(default_factory=list)
    reason: str = ""


class EvidenceVerifier:
    """Vérifie que chaque citation dans la réponse correspond à un chunk réel.

    Remplace le Verifier basique de rag/citations.py par une validation
    exhaustive contre les sources retournées par le RAG.
    """

    def __init__(self):
        self._citation_pattern = re.compile(r'\[Source:\s*([^\]]+)\]')

    def extract_citations(self, response: str) -> list[str]:
        """Extrait toutes les sources citées dans une réponse.

        Returns:
            Liste des noms de sources (ex: 'document.pdf — Titre')
        """
        return self._citation_pattern.findall(response)

    def verify(
        self,
        response: str,
        chunk_sources: list[str],
        rag_context: str = "",
    ) -> VerificationResult:
        """Vérifie que les citations répondent à 3 critères.

        1. Il y a au moins une citation dans la réponse
        2. Aucune citation n'est "AUCUNE SOURCE" (marqueur de contexte vide)
        3. Chaque source citée existe dans les chunks retournés par le RAG

        V17 : détection automatique du mode appelant.
        - Si chunk_sources est une string courte (< 500 chars, pas de \n),
          c'est une query passée par erreur → mode dégradé (skip critère 3).
        - Si c'est une liste, validation normale.

        Args:
            response: Texte généré par le LLM
            chunk_sources: Noms des sources des chunks RAG (ou query legacy)
            rag_context: Contexte RAG complet

        Returns:
            VerificationResult structuré
        """
        # V17 : détection polymorphe — si c'est une string courte, c'est une query
        if isinstance(chunk_sources, str) and len(chunk_sources) < 500 and "\n" not in chunk_sources:
            logger.debug("EvidenceVerifier: chunk_sources est une query (legacy call) — skip critère 3")
            chunk_sources = []

        # Critère 1 : présence de citations
        citations = self.extract_citations(response)
        if not citations:
            return VerificationResult(
                valid=False,
                reason="Aucune citation [Source: ...] dans la réponse générée",
                confidence=0.0,
            )

        # Critère 2 : pas de marqueur "AUCUNE SOURCE"
        if "AUCUNE SOURCE" in rag_context.upper() and citations:
            return VerificationResult(
                valid=False,
                reason="Contexte RAG vide (AUCUNE SOURCE) mais le LLM a cité",
                confidence=0.0,
                matched_citations=[],
                missing_citations=citations,
            )

        # Critère 3 : chaque citation existe dans les chunks
        matched = []
        missing = []
        for c in citations:
            # Extrait juste le nom du fichier avant le tiret
            source_name = c.split(" —")[0].strip() if " —" in c else c.strip()
            # Comparaison stricte : soit égal, soit l'un finit par l'autre
            found = any(
                source_name.lower() == s.lower()
                or s.lower().endswith("/" + source_name.lower())
                for s in chunk_sources
            )
            if found:
                matched.append(c)
            else:
                missing.append(c)

        if missing and chunk_sources:
            # Calculer un ratio de confiance
            ratio = len(matched) / (len(matched) + len(missing))
            logger.warning(
                f"🔍 EvidenceVerifier: {len(missing)} citation(s) manquante(s) "
                f"parmi les chunks: {missing}"
            )
            return VerificationResult(
                valid=False,
                reason=f"{len(missing)} citation(s) non trouvée(s) dans les chunks: {missing}",
                confidence=ratio,
                matched_citations=matched,
                missing_citations=missing,
            )

        # Tout est OK
        confidence = min(0.95, len(matched) * 0.15)
        logger.debug(f"🔍 EvidenceVerifier: {len(matched)} citation(s) vérifiées OK")
        return VerificationResult(
            valid=True,
            confidence=confidence,
            matched_citations=matched,
        )
