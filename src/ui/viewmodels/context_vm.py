"""ViewModel du contexte RAG — affichage des sources et scores."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SourceViewModel:
    """Une source documentaire formatée pour l'affichage."""
    name: str
    score: float
    ext: str = "PDF"
    preview: str = ""


class ContextViewModel:
    """Logique d'affichage du contexte RAG : sources, scores, pipeline."""

    def __init__(self):
        self.sources: list[SourceViewModel] = []
        self.confidence: float = 0.0
        self.retrieval_mode: str = "none"
        self.reranker_used: bool = False
        self.chunks_found: int = 0
        self.chunks_injected: int = 0
        self.retrieval_time_ms: float = 0.0

    def update_from_rag(self, rag_result):
        """Met à jour le viewmodel à partir d'un RAGResult."""
        if rag_result is None:
            return
        self.confidence = getattr(rag_result, 'top_score', 0.0)
        self.chunks_found = getattr(rag_result, 'chunks_retrieved', 0)
        self.chunks_injected = getattr(rag_result, 'chunks_injected', 0)
        self.retrieval_time_ms = getattr(rag_result, 'retrieval_time_ms', 0.0)

        sources_raw = getattr(rag_result, 'sources', [])
        self.sources = [
            SourceViewModel(
                name=s.get('name', '?'),
                score=s.get('score', 0.0),
                ext=s.get('ext', 'PDF'),
                preview=s.get('preview', '')[:100],
            )
            for s in sources_raw[:5]
        ]

    def update_from_evidence(self, evidence_pack):
        """Met à jour à partir d'un EvidencePack."""
        if evidence_pack is None:
            return
        self.confidence = evidence_pack.confidence
        self.retrieval_mode = evidence_pack.retrieval_mode
        self.reranker_used = evidence_pack.reranker_used
        self.chunks_found = evidence_pack.chunks_retrieved
        self.chunks_injected = evidence_pack.chunks_injected
        self.retrieval_time_ms = evidence_pack.retrieval_time_ms
        self.sources = [
            SourceViewModel(name=s, score=0.0)
            for s in evidence_pack.sources[:5]
        ]

    def summary(self) -> dict:
        return {
            "confidence": round(self.confidence, 3),
            "mode": self.retrieval_mode,
            "sources": len(self.sources),
            "reranker": self.reranker_used,
            "time_ms": self.retrieval_time_ms,
        }
