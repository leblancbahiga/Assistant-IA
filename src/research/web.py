from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import hashlib

@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str
    relevance_score: float  # 0.0 à 1.0
    source_hash: str = ""  # hash pour dédup
    
    def __post_init__(self):
        if not self.source_hash:
            self.source_hash = hashlib.sha256(self.url.encode()).hexdigest()[:16]

@dataclass
class ResearchQuery:
    query: str
    max_results: int = 5
    min_relevance: float = 0.3
    categories: list[str] = field(default_factory=list)  # "web", "academic", "news"

class WebResearcher:
    """Recherche web avec extraction, scoring et déduplication."""
    
    def __init__(self):
        self._search_history: list[ResearchQuery] = []
        self._results_cache: dict[str, list[SearchResult]] = {}
    
    def score_relevance(self, query: str, title: str, snippet: str) -> float:
        """Score de pertinence basique par chevauchement de mots-clés."""
        query_words = set(query.lower().split())
        text_words = set((title + " " + snippet).lower().split())
        if not query_words:
            return 0.0
        overlap = query_words & text_words
        return min(len(overlap) / len(query_words), 1.0)
    
    def deduplicate(self, results: list[SearchResult]) -> list[SearchResult]:
        """Supprime les doublons par hash URL."""
        seen: set[str] = set()
        deduped = []
        for r in results:
            if r.source_hash not in seen:
                seen.add(r.source_hash)
                deduped.append(r)
        return deduped
    
    def filter_by_relevance(self, results: list[SearchResult], min_score: float) -> list[SearchResult]:
        """Filtre par score minimum."""
        return [r for r in results if r.relevance_score >= min_score]
    
    def rank_results(self, results: list[SearchResult]) -> list[SearchResult]:
        """Trie par pertinence décroissante."""
        return sorted(results, key=lambda r: r.relevance_score, reverse=True)
    
    def search(self, query: ResearchQuery) -> list[SearchResult]:
        """Exécute une recherche (placeholder — l'intégration web viendra via Hermes tools)."""
        self._search_history.append(query)
        # Pour l'instant retourne une liste vide — l'intégration réelle
        # utilisera web_search/web_extract du framework Hermes
        cache_key = query.query.lower().strip()
        return self._results_cache.get(cache_key, [])
    
    def cache_results(self, query: str, results: list[SearchResult]):
        """Met en cache les résultats d'une recherche."""
        self._results_cache[query.lower().strip()] = results
    
    def get_history(self) -> list[ResearchQuery]:
        return list(self._search_history)
    
    def format_results(self, results: list[SearchResult]) -> str:
        """Formate les résultats pour affichage."""
        if not results:
            return "Aucun résultat trouvé."
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. **{r.title}** (score: {r.relevance_score:.2f})")
            lines.append(f"   {r.url}")
            lines.append(f"   {r.snippet[:150]}...")
            lines.append("")
        return "\n".join(lines)
