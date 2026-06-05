"""Moteur de politiques de décision pour NURU V4.5.

Centralise les règles de seuils (RAM, confiance, fallback) qui étaient
dispersées dans semantic_router.py et rag_engine.py.
"""
import logging
from typing import Optional
from src.core.query_context import QueryContext

logger = logging.getLogger(__name__)


class PolicyEngine:
    """Décisions basées sur l'état système (RAM, score, connectivité).

    Centralise les seuils pour éviter les dérives entre modules.
    """

    # Seuils de confiance RAG
    HIGH_CONFIDENCE = 0.75     # RAG direct, pas de vérif
    MID_CONFIDENCE = 0.48      # RAG + vérification
    LOW_CONFIDENCE = 0.0       # Clarification ou cloud

    # Zone grise pour le reranker
    RERANK_MIN_SCORE = 0.40
    RERANK_MAX_SCORE = 0.75

    # RAM
    RERANK_MIN_RAM_MB = 1500
    CLOUD_FALLBACK_RAM_GB = 1.5

    def __init__(self):
        logger.info("⚙️ PolicyEngine initialisé")

    # ─── Routage ───

    def route_from_score(self, ctx: QueryContext, max_score: float) -> str:
        """Décide de la route à partir du score RAG et du contexte RAM."""
        if max_score >= self.HIGH_CONFIDENCE:
            return "LOCAL_RAG"
        elif max_score >= self.MID_CONFIDENCE:
            return "LOCAL_RAG"
        elif ctx.is_online:
            return "CLOUD_GROQ"
        else:
            return "CLARIFICATION"

    # ─── Reranker ───

    def should_rerank(self, max_vector_score: float, ram_free_mb: int) -> bool:
        """Active le reranker uniquement dans la zone grise AVEC RAM suffisante."""
        in_gray_zone = self.RERANK_MIN_SCORE < max_vector_score < self.RERANK_MAX_SCORE
        if not in_gray_zone:
            return False
        if ram_free_mb < self.RERANK_MIN_RAM_MB:
            logger.info(
                f"⏭️ Reranker désactivé : RAM {ram_free_mb} MB < {self.RERANK_MIN_RAM_MB} MB"
            )
            return False
        return True

    # ─── Fallback ───

    def should_use_cloud(self, ctx: QueryContext) -> bool:
        """Décide si le cloud est préférable au local."""
        return ctx.is_online and ctx.ram_free_mb < self.CLOUD_FALLBACK_RAM_GB * 1024

    # ─── Mémoire ───

    def should_store_memory(self, confidence: float) -> bool:
        """Ne stocke en mémoire long terme que si confiance suffisante."""
        return confidence >= 0.78
