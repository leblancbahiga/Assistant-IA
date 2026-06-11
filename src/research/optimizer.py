from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class SearchPattern:
    query_pattern: str  # ex: "comment faire X"
    success_rate: float  # 0.0 à 1.0
    avg_relevance: float
    use_count: int

class SearchOptimizer:
    """Optimise les requêtes de recherche avec apprentissage."""
    
    def __init__(self):
        self._patterns: dict[str, SearchPattern] = {}
        self._query_history: list[dict[str, Any]] = []
    
    def record_query(self, query: str, results_count: int, avg_relevance: float):
        """Enregistre le résultat d'une recherche pour apprentissage."""
        pattern_key = self._extract_pattern(query)
        if pattern_key in self._patterns:
            p = self._patterns[pattern_key]
            p.use_count += 1
            # Moyenne mobile
            old_weight = (p.use_count - 1) / p.use_count
            new_weight = 1 / p.use_count
            p.avg_relevance = old_weight * p.avg_relevance + new_weight * avg_relevance
            p.success_rate = 1.0 if results_count > 0 else 0.0
        else:
            self._patterns[pattern_key] = SearchPattern(
                query_pattern=pattern_key,
                success_rate=1.0 if results_count > 0 else 0.0,
                avg_relevance=avg_relevance,
                use_count=1,
            )
        self._query_history.append({
            "query": query,
            "results_count": results_count,
            "avg_relevance": avg_relevance,
        })
    
    def suggest_refinement(self, query: str) -> list[str]:
        """Suggère des raffinements basés sur l'historique."""
        suggestions = []
        pattern_key = self._extract_pattern(query)
        if pattern_key in self._patterns:
            p = self._patterns[pattern_key]
            if p.avg_relevance < 0.5:
                suggestions.append(f"Requête peu efficace (pertinence {p.avg_relevance:.2f}). Essayez d'ajouter des mots-clés spécifiques.")
            if p.use_count > 5:
                suggestions.append(f"Pattern utilisé {p.use_count} fois. Considérez une alternative.")
        # Suggestions génériques
        words = query.split()
        if len(words) < 3:
            suggestions.append("Requête courte — ajoutez des termes descriptifs.")
        if "?" in query:
            suggestions.append("Les requêtes sans '?' fonctionnent souvent mieux.")
        return suggestions
    
    def _extract_pattern(self, query: str) -> str:
        """Extrait un pattern normalisé de la requête."""
        words = query.lower().strip().split()
        # Garder les mots significatifs (> 2 caractères)
        significant = [w for w in words if len(w) > 2]
        return " ".join(significant[:3])  # top 3 mots
    
    def get_best_patterns(self, limit: int = 5) -> list[SearchPattern]:
        """Retourne les patterns les plus efficaces."""
        sorted_patterns = sorted(
            self._patterns.values(),
            key=lambda p: p.avg_relevance,
            reverse=True,
        )
        return sorted_patterns[:limit]
    
    def get_stats(self) -> dict[str, Any]:
        """Statistiques globales."""
        if not self._patterns:
            return {"total_queries": 0, "avg_relevance": 0.0}
        total = sum(p.use_count for p in self._patterns.values())
        avg_rel = sum(p.avg_relevance * p.use_count for p in self._patterns.values()) / total if total > 0 else 0
        return {
            "total_queries": total,
            "unique_patterns": len(self._patterns),
            "avg_relevance": round(avg_rel, 3),
            "best_pattern": max(self._patterns.values(), key=lambda p: p.avg_relevance).query_pattern if self._patterns else None,
        }
