"""
NURU V10 — Smart Search : recherche hybride RAG + Spotlight + Cloud.

Point d'entrée unique : cherche dans l'index RAG, puis Spotlight (lit le contenu),
puis formate pour le LLM.
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    content: str
    source: str
    score: float
    strategy: str  # "rag", "spotlight"


@dataclass
class SearchResults:
    results: List[SearchResult]
    context: str  # Contexte formaté pour le LLM
    strategy_used: str
    total_time_ms: float = 0.0


class SmartSearch:
    """Recherche hybride RAG + Spotlight."""

    def __init__(self, rag_engine=None):
        self.rag_engine = rag_engine
        self._spotlight = None
        self._init_spotlight()

    def _init_spotlight(self):
        try:
            from src.rag.spotlight import SpotlightSearch
            self._spotlight = SpotlightSearch()
        except Exception as e:
            logger.warning(f"Spotlight non disponible: {e}")

    async def search(self, query: str, max_results: int = 5) -> SearchResults:
        """
        Recherche intelligente avec CONTEXTE LISIBLE.

        1. Essayer le RAG (notre index)
        2. Si pas de résultats, Spotlight + lecture du contenu
        3. Formater un contexte pour le LLM
        """
        start = time.time()

        # === ÉTAPE 1 : Notre RAG ===
        if self.rag_engine:
            try:
                rag_context, rag_result = await self.rag_engine.retrieve(query)
                if rag_context and rag_result.top_score > 0.2:
                    elapsed = (time.time() - start) * 1000
                    logger.info(f"SmartSearch RAG: top_score={rag_result.top_score:.2f} ({elapsed:.0f}ms)")
                    return SearchResults(
                        results=[],
                        context=rag_context,
                        strategy_used="rag",
                        total_time_ms=elapsed,
                    )
            except Exception as e:
                logger.warning(f"RAG erreur: {e}")

        # === ÉTAPE 2 : Spotlight + lecture du contenu ===
        if self._spotlight:
            try:
                spotlight_results = self._spotlight.search(query, max_results=max_results, read_content=True)
                if spotlight_results:
                    # Construire le contexte à partir du CONTENU lu
                    context_parts = []
                    results = []
                    for r in spotlight_results:
                        if r.content:
                            context_parts.append(
                                f"[SOURCE: {r.filename}]\n{r.content}\n"
                            )
                            results.append(SearchResult(
                                content=r.content[:500],
                                source=r.path,
                                score=0.7,
                                strategy="spotlight",
                            ))
                        else:
                            context_parts.append(
                                f"[SOURCE: {r.filename}] (fichier trouvé mais contenu non lisible)\n"
                            )

                    context = "=== DOCUMENTS TROUVÉS ===\n" + "\n".join(context_parts)
                    elapsed = (time.time() - start) * 1000
                    logger.info(f"SmartSearch Spotlight: {len(spotlight_results)} fichiers ({elapsed:.0f}ms)")
                    return SearchResults(
                        results=results,
                        context=context,
                        strategy_used="spotlight",
                        total_time_ms=elapsed,
                    )
            except Exception as e:
                logger.warning(f"Spotlight erreur: {e}")

        # === ÉTAPE 3 : Aucun résultat ===
        elapsed = (time.time() - start) * 1000
        return SearchResults(
            results=[],
            context="",
            strategy_used="none",
            total_time_ms=elapsed,
        )
