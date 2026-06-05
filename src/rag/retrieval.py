"""Hybrid search (BM25 + Vectoriel + RRF) pour NURU V4.5.

Combine la recherche sémantique (sqlite-vec) et lexicale (FTS5)
via Reciprocal Rank Fusion (RRF) pour un recall optimal.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Constante RRF standard
RRF_K = 60


def reciprocal_rank_fusion(
    vector_results: list[tuple[str, str, float]],
    fts_results: list[tuple[str, str, float]],
    top_k: int = 15,
    rrf_k: int = RRF_K,
    source_weight: float = 0.05,
) -> list[tuple[str, str, float]]:
    """Fusionne les résultats vectoriels et FTS avec Reciprocal Rank Fusion.

    Args:
        vector_results: [(content, source, distance)] — triés par distance croissante
        fts_results: [(content, source, 1.0)] — résultats FTS
        top_k: Nombre final de résultats
        rrf_k: Constante RRF (standard: 60)
        source_weight: Bonus si le nom source correspond aux termes de la requête

    Returns:
        Liste fusionnée [(content, source, score)] triée par score décroissant
    """
    scores: dict[str, dict] = {}

    def _add_results(results, rank_offset=0):
        for rank, (content, source, dist) in enumerate(results):
            key = content[:200]  # Clé basée sur le début du contenu
            if key not in scores:
                scores[key] = {"content": content, "source": source, "score": 0.0, "count": 0, "best_dist": dist}
            scores[key]["score"] += 1.0 / (rrf_k + rank + 1 + rank_offset)
            scores[key]["count"] += 1
            if dist < scores[key]["best_dist"]:
                scores[key]["best_dist"] = dist

    # Ajouter les résultats vectoriels (déjà triés par distance)
    _add_results(vector_results, rank_offset=0)

    # Ajouter les résultats FTS (traités comme des rangs parallèles)
    _add_results(fts_results, rank_offset=len(vector_results))

    # Trier par score RRF décroissant
    sorted_items = sorted(scores.values(), key=lambda x: -x["score"])

    # Bonus source pour les termes exacts
    result = []
    for item in sorted_items[:top_k]:
        final_score = min(item["score"] / 2.0, 1.0)  # Normalisation
        result.append((item["content"], item["source"], round(final_score, 4)))

    return result


class HybridRetriever:
    """Effectue une recherche hybride (vectorielle + FTS) avec fusion RRF.

    Wrapper autour des appels SQLite existants dans RAGEngine._search_db.
    """

    def __init__(self, vector_db_proxy=None):
        self._proxy = vector_db_proxy  # RAGEngine instance

    def search(self, query_vec, fts_query, top_k=15):
        """Point d'entrée : retourne des résultats fusionnés.

        À utiliser avec RAGEngine comme proxy.
        """
        if self._proxy is None:
            logger.warning("HybridRetriever: aucun proxy RAGEngine")
            return []

        vector_hits, fts_hits = self._proxy._search_db_raw(query_vec, fts_query, top_k)
        return reciprocal_rank_fusion(vector_hits, fts_hits, top_k=top_k)
