"""Conteneurs de données immutables pour le pipeline NURU V8+.

QueryContext : état figé d'une requête au moment du routage.
EvidencePack : preuves assemblées par le pipeline RAG.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class QueryContext:
    """Contexte immutable d'une requête au moment de son traitement par l'orchestrateur.

    Figé au début de process_query() pour garantir que les décisions
    (routage, policies) sont basées sur un état cohérent.

    V8+ Sprint 5 :
    - already_retried : flag anti-boucle de reformulation (max 1 retry)
    - already_fact_checked : flag anti-boucle du vérificateur
    """
    query: str
    session_id: str
    is_online: bool = True
    mode: str = "default"
    ram_free_mb: int = 0
    route: str = "unknown"       # Défini après routage
    hybrid_strategy: str = "local_only"  # NURU V6 : stratégie hybride
    # V8+ Sprint 5 : Guards anti-boucle
    already_retried: bool = False
    already_fact_checked: bool = False
    # V17 Phase 2 : correlation ID pour traçabilité pipeline
    correlation_id: str = ""

    @classmethod
    def from_runtime(cls, query: str, session_id: str, is_online: bool = True) -> "QueryContext":
        """Crée un contexte à partir des infos runtime."""
        import psutil
        ram_free = int(psutil.virtual_memory().available / (1024 * 1024))
        import uuid
        return cls(
            query=query,
            session_id=session_id,
            is_online=is_online,
            ram_free_mb=ram_free,
            correlation_id=uuid.uuid4().hex[:8],
        )

    def with_route(self, route: str, hybrid_strategy: str = "local_only") -> "QueryContext":
        """Retourne une copie avec la route et la stratégie hybride définies."""
        return QueryContext(
            query=self.query,
            session_id=self.session_id,
            is_online=self.is_online,
            mode=self.mode,
            ram_free_mb=self.ram_free_mb,
            route=route,
            hybrid_strategy=hybrid_strategy,
            already_retried=self.already_retried,
            already_fact_checked=self.already_fact_checked,
        )

    def with_retry(self) -> "QueryContext":
        """V8+ Sprint 5 : Retourne une copie avec already_retried=True."""
        return QueryContext(
            query=self.query,
            session_id=self.session_id,
            is_online=self.is_online,
            mode=self.mode,
            ram_free_mb=self.ram_free_mb,
            route=self.route,
            hybrid_strategy=self.hybrid_strategy,
            already_retried=True,
            already_fact_checked=self.already_fact_checked,
        )

    def with_fact_checked(self) -> "QueryContext":
        """V8+ Sprint 5 : Retourne une copie avec already_fact_checked=True."""
        return QueryContext(
            query=self.query,
            session_id=self.session_id,
            is_online=self.is_online,
            mode=self.mode,
            ram_free_mb=self.ram_free_mb,
            route=self.route,
            hybrid_strategy=self.hybrid_strategy,
            already_retried=self.already_retried,
            already_fact_checked=True,
        )


@dataclass(frozen=True)
class Citation:
    """Une citation vérifiable pointant vers un chunk source."""
    doc_id: str
    chunk_id: str
    title: Optional[str] = None
    source: Optional[str] = None


@dataclass(frozen=True)
class EvidencePack:
    """Preuves assemblées par le pipeline RAG pour une requête.

    Contient les chunks retenus, leurs citations, et le score de confiance.
    Utilisé par l'orchestrateur pour alimenter le LLM et l'UI.
    """
    query: str
    chunks: list = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    confidence: float = 0.0
    retrieval_mode: str = "none"        # "vector" | "hybrid" | "reranked"
    sources: list[str] = field(default_factory=list)
    retrieval_time_ms: float = 0.0
    chunks_retrieved: int = 0
    chunks_injected: int = 0
    reranker_used: bool = False

    def to_dict(self) -> dict:
        """Sérialisation pour l'UI et les logs."""
        return {
            "confidence": round(self.confidence, 3),
            "num_chunks": len(self.chunks),
            "mode": self.retrieval_mode,
            "sources": self.sources,
            "time_ms": self.retrieval_time_ms,
            "reranker_used": self.reranker_used,
        }

    @property
    def has_evidence(self) -> bool:
        return len(self.chunks) > 0 and self.confidence > 0.0
