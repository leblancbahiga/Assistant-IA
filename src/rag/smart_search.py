"""
NURU V10 — Smart Search : recherche hybride RAG + Spotlight + Cloud.

Point d'entrée unique pour toute recherche documentaire.
Combine :
1. Notre index RAG (embedding + FTS) — rapide, notre index
2. Spotlight (mdfind) — instantané, tous les fichiers
3. Cloud (LLM) — si les deux précédents échouent

Usage:
    search = SmartSearch(rag_engine=rag)
    results = await search.search("BEACCOM")
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

@dataclass
class SearchResult:
    content: str
    source: str
    score: float
    strategy: str  # "rag", "spotlight", "cloud"

@dataclass
class SearchResults:
    results: List[SearchResult]
    strategy_used: str
    total_time_ms: float = 0.0

class SmartSearch:
    """Recherche hybride RAG + Spotlight + Cloud."""
    
    def __init__(self, rag_engine=None):
        self.rag_engine = rag_engine
        self._spotlight = None
        self._init_spotlight()
    
    def _init_spotlight(self):
        """Initialise Spotlight si disponible."""
        try:
            from src.rag.spotlight import SpotlightSearch
            self._spotlight = SpotlightSearch()
        except Exception as e:
            logger.warning(f"Spotlight non disponible: {e}")
    
    async def search(self, query: str, max_results: int = 10) -> SearchResults:
        """
        Recherche intelligente : RAG → Spotlight → Cloud.
        
        1. Essayer le RAG d'abord (notre index)
        2. Si pas de résultats, essayer Spotlight (tous les fichiers)
        3. Si toujours rien, retourner vide (le Cloud sera géré par l'orchestrateur)
        """
        start = time.time()
        
        # === ÉTAPE 1 : Notre RAG ===
        if self.rag_engine:
            try:
                rag_context, rag_result = await self.rag_engine.retrieve(query)
                if rag_context and rag_result.top_score > 0.2:
                    results = self._parse_rag_context(rag_context)
                    elapsed = (time.time() - start) * 1000
                    logger.info(f"SmartSearch RAG: {len(results)} résultats ({elapsed:.0f}ms)")
                    return SearchResults(
                        results=results,
                        strategy_used="rag",
                        total_time_ms=elapsed,
                    )
            except Exception as e:
                logger.warning(f"RAG erreur: {e}")
        
        # === ÉTAPE 2 : Spotlight ===
        if self._spotlight:
            try:
                spotlight_results = self._spotlight.search(query, max_results=max_results)
                if spotlight_results:
                    results = [
                        SearchResult(
                            content=f"[Spotlight] {r.filename}",
                            source=r.path,
                            score=0.8,
                            strategy="spotlight",
                        )
                        for r in spotlight_results
                    ]
                    elapsed = (time.time() - start) * 1000
                    logger.info(f"SmartSearch Spotlight: {len(results)} résultats ({elapsed:.0f}ms)")
                    return SearchResults(
                        results=results,
                        strategy_used="spotlight",
                        total_time_ms=elapsed,
                    )
            except Exception as e:
                logger.warning(f"Spotlight erreur: {e}")
        
        # === ÉTAPE 3 : Aucun résultat ===
        elapsed = (time.time() - start) * 1000
        logger.info(f"SmartSearch: aucun résultat ({elapsed:.0f}ms)")
        return SearchResults(
            results=[],
            strategy_used="none",
            total_time_ms=elapsed,
        )
    
    def _parse_rag_context(self, context: str) -> List[SearchResult]:
        """Parse le contexte RAG en résultats structurés."""
        results = []
        lines = context.split("\n")
        current_source = ""
        current_content = []
        
        for line in lines:
            if line.startswith("[SOURCE"):
                if current_source and current_content:
                    results.append(SearchResult(
                        content="\n".join(current_content),
                        source=current_source,
                        score=0.7,
                        strategy="rag",
                    ))
                current_source = line.split("]")[-1].strip() if "]" in line else ""
                current_content = []
            else:
                current_content.append(line)
        
        # Dernier résultat
        if current_source and current_content:
            results.append(SearchResult(
                content="\n".join(current_content),
                source=current_source,
                score=0.7,
                strategy="rag",
            ))
        
        return results
