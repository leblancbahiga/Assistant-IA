"""Citations et vérification pour NURU V4.5.

CitationBuilder : construit des citations formatées à partir des chunks.
Verifier : vérifie qu'une réponse s'appuie sur des preuves.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """Une citation vérifiable pointant vers une source."""
    doc_id: str = ""
    chunk_id: str = ""
    title: str = ""
    source: str = ""
    score: float = 0.0

    def to_str(self) -> str:
        """Format: [Source: document.pdf — Titre]"""
        parts = [f"Source: {self.source}"]
        if self.title:
            parts.append(self.title)
        return f"[{' — '.join(parts)}]"


@dataclass
class VerificationResult:
    """Résultat de la vérification post-génération."""
    valid: bool = True
    confidence: float = 0.0
    citations: list[Citation] = field(default_factory=list)
    reason: str = ""
    suggestion: str = ""


class CitationBuilder:
    """Construit des citations formatées à partir des chunks RAG."""

    def make(self, chunks: list) -> list[Citation]:
        """Crée des citations pour chaque chunk.

        Args:
            chunks: liste de tuples (content, source, score) ou SemanticChunk

        Returns:
            Liste de Citation
        """
        citations = []
        for c in chunks:
            if hasattr(c, 'title'):
                # SemanticChunk
                citations.append(Citation(
                    doc_id=getattr(c, 'doc_id', ''),
                    chunk_id=getattr(c, 'chunk_id', ''),
                    title=c.title or "",
                    source=c.source or "",
                    score=getattr(c, 'tokens', 0),
                ))
            elif isinstance(c, tuple) and len(c) >= 2:
                citations.append(Citation(
                    source=str(c[1]),
                    score=float(c[2]) if len(c) > 2 else 0.0,
                ))
        return citations

    def extract_from(self, response: str) -> list[str]:
        """Extrait les citations déjà présentes dans une réponse."""
        return re.findall(r'\[Source:[^\]]+\]', response)

    def format_context(self, citations: list[Citation]) -> str:
        """Formate les citations pour le prompt LLM."""
        if not citations:
            return "[AUCUNE SOURCE DOCUMENTAIRE PERTINENTE TROUVÉE]"
        return "\n".join(c.to_str() for c in citations)


class Verifier:
    """Vérifie qu'une réponse générée s'appuie sur des preuves."""

    def __init__(self, citation_builder: Optional[CitationBuilder] = None):
        self.citer = citation_builder or CitationBuilder()

    def verify(self, response: str, chunks: list) -> VerificationResult:
        """Vérifie qu'au moins une citation existe dans la réponse.

        Règle : si pas de chunks, pas de vérification possible → invalide.
        Si la réponse ne cite aucune source → invalide (hallucination probable).
        """
        if not chunks:
            return VerificationResult(
                valid=False,
                reason="Aucun chunk source fourni",
                suggestion="Répondre : Je ne trouve pas cette information dans mes documents."
            )

        citations_in_response = self.citer.extract_from(response)
        if not citations_in_response:
            return VerificationResult(
                valid=False,
                confidence=0.0,
                reason="Aucune citation trouvée dans la réponse",
                suggestion="Vérifier que le prompt système force les citations [Source: ...]"
            )

        return VerificationResult(
            valid=True,
            confidence=min(0.95, len(citations_in_response) * 0.1),
            citations=[Citation(source=c) for c in citations_in_response],
        )
