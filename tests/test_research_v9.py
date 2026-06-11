"""
Tests unitaires pour WebResearcher + SearchOptimizer — NURU V10 Sprint 7
"""
import pytest
from src.research.web import WebResearcher, SearchResult, ResearchQuery
from src.research.optimizer import SearchOptimizer, SearchPattern


# ═══════════════════════════════════════════════════════════════
#  TestWebResearcher — 10 tests
# ═══════════════════════════════════════════════════════════════

class TestWebResearcher:
    def setup_method(self):
        self.researcher = WebResearcher()

    # 1 — score_relevance exact
    def test_score_relevance_exact(self):
        score = self.researcher.score_relevance(
            "python machine learning",
            "Python for Machine Learning",
            "A guide to python and machine learning techniques"
        )
        assert score == 1.0  # tous les mots-clés présents

    # 2 — score empty query
    def test_score_relevance_empty_query(self):
        score = self.researcher.score_relevance("", "Title", "Snippet")
        assert score == 0.0

    # 3 — score partial overlap
    def test_score_relevance_partial(self):
        score = self.researcher.score_relevance(
            "python machine learning",
            "Python Tutorial",
            "Learn python basics"
        )
        # "python" present, "machine" absent, "learning" absent → 1/3
        assert abs(score - 1/3) < 0.01

    # 4 — deduplicate
    def test_deduplicate(self):
        results = [
            SearchResult(url="https://a.com", title="A", snippet="sa", relevance_score=0.8),
            SearchResult(url="https://b.com", title="B", snippet="sb", relevance_score=0.6),
            SearchResult(url="https://a.com", title="A dup", snippet="dup", relevance_score=0.5),
        ]
        deduped = self.researcher.deduplicate(results)
        assert len(deduped) == 2
        assert deduped[0].url == "https://a.com"
        assert deduped[1].url == "https://b.com"

    # 5 — deduplicate keep first occurrence
    def test_deduplicate_keep_first(self):
        r1 = SearchResult(url="https://x.com", title="First", snippet="s1", relevance_score=0.9)
        r2 = SearchResult(url="https://x.com", title="Second", snippet="s2", relevance_score=0.3)
        deduped = self.researcher.deduplicate([r1, r2])
        assert len(deduped) == 1
        assert deduped[0].title == "First"

    # 6 — filter_by_relevance
    def test_filter_by_relevance(self):
        results = [
            SearchResult(url="https://a.com", title="A", snippet="sa", relevance_score=0.9),
            SearchResult(url="https://b.com", title="B", snippet="sb", relevance_score=0.2),
            SearchResult(url="https://c.com", title="C", snippet="sc", relevance_score=0.5),
        ]
        filtered = self.researcher.filter_by_relevance(results, 0.5)
        assert len(filtered) == 2
        assert all(r.relevance_score >= 0.5 for r in filtered)

    # 7 — rank_results
    def test_rank_results(self):
        results = [
            SearchResult(url="https://a.com", title="A", snippet="sa", relevance_score=0.3),
            SearchResult(url="https://b.com", title="B", snippet="sb", relevance_score=0.9),
            SearchResult(url="https://c.com", title="C", snippet="sc", relevance_score=0.6),
        ]
        ranked = self.researcher.rank_results(results)
        assert [r.title for r in ranked] == ["B", "C", "A"]

    # 8 — search
    def test_search_returns_empty(self):
        query = ResearchQuery(query="test query", max_results=5)
        results = self.researcher.search(query)
        assert results == []
        assert len(self.researcher.get_history()) == 1

    # 9 — cache and retrieve
    def test_cache_and_retrieve(self):
        cached = [
            SearchResult(url="https://cached.com", title="Cached", snippet="sc", relevance_score=0.8)
        ]
        self.researcher.cache_results("python tutorial", cached)
        query = ResearchQuery(query="python tutorial")
        results = self.researcher.search(query)
        assert len(results) == 1
        assert results[0].title == "Cached"

    # 10 — format_results
    def test_format_results(self):
        results = [
            SearchResult(url="https://a.com", title="Title A", snippet="A short snippet for testing", relevance_score=0.85),
        ]
        formatted = self.researcher.format_results(results)
        assert "Title A" in formatted
        assert "0.85" in formatted
        assert "https://a.com" in formatted

    # 11 — format empty results
    def test_format_results_empty(self):
        assert self.researcher.format_results([]) == "Aucun résultat trouvé."


# ═══════════════════════════════════════════════════════════════
#  TestSearchOptimizer — 10 tests
# ═══════════════════════════════════════════════════════════════

class TestSearchOptimizer:
    def setup_method(self):
        self.optimizer = SearchOptimizer()

    # 1 — record_query
    def test_record_query(self):
        self.optimizer.record_query("python tutorial", 5, 0.8)
        stats = self.optimizer.get_stats()
        assert stats["total_queries"] == 1
        assert stats["avg_relevance"] == 0.8

    # 2 — record multiple queries same pattern
    def test_record_multiple(self):
        self.optimizer.record_query("python tutorial", 5, 0.8)
        self.optimizer.record_query("python tutorial avancé", 3, 0.6)
        stats = self.optimizer.get_stats()
        assert stats["total_queries"] == 2
        # Both share pattern "python tutorial" (top 3 significant words)
        # Weighted avg: (0.8*1 + 0.6*1) / 2 = 0.7
        assert abs(stats["avg_relevance"] - 0.7) < 0.01

    # 3 — suggest_refinement short query
    def test_suggest_refinement_short(self):
        suggestions = self.optimizer.suggest_refinement("python")
        assert any("courte" in s for s in suggestions)

    # 4 — suggest_refinement low relevance
    def test_suggest_refinement_low_relevance(self):
        # Record pattern with low relevance
        for _ in range(3):
            self.optimizer.record_query("machine learning basics", 1, 0.3)
        suggestions = self.optimizer.suggest_refinement("machine learning basics")
        assert any("peu efficace" in s for s in suggestions)

    # 5 — extract_pattern
    def test_extract_pattern(self):
        pattern = self.optimizer._extract_pattern("Comment faire du machine learning en Python")
        # significant words > 2 chars: ["comment", "faire", "machine", "learning", "python"]
        # top 3: "comment faire machine"
        assert pattern == "comment faire machine"

    # 6 — get_best_patterns
    def test_get_best_patterns(self):
        self.optimizer.record_query("alpha beta gamma", 5, 0.9)
        self.optimizer.record_query("alpha delta epsilon", 3, 0.5)
        best = self.optimizer.get_best_patterns(limit=1)
        assert len(best) == 1
        assert best[0].avg_relevance == 0.9

    # 7 — get_stats empty
    def test_get_stats_empty(self):
        stats = self.optimizer.get_stats()
        assert stats["total_queries"] == 0
        assert stats["avg_relevance"] == 0.0

    # 8 — get_stats populated
    def test_get_stats_populated(self):
        self.optimizer.record_query("deep learning framework", 5, 0.9)
        self.optimizer.record_query("deep learning tutorial", 3, 0.7)
        stats = self.optimizer.get_stats()
        assert stats["total_queries"] == 2
        assert stats["unique_patterns"] == 2  # different patterns
        assert stats["best_pattern"] is not None

    # 9 — history tracking
    def test_history_tracking(self):
        self.optimizer.record_query("query one", 2, 0.6)
        self.optimizer.record_query("query two", 4, 0.8)
        assert len(self.optimizer._query_history) == 2
        assert self.optimizer._query_history[0]["query"] == "query one"
        assert self.optimizer._query_history[1]["results_count"] == 4

    # 10 — pattern learning (moving average)
    def test_pattern_learning(self):
        # Same pattern, multiple observations (top 3 significant words must match)
        self.optimizer.record_query("python advanced tutorial basics", 5, 0.9)
        self.optimizer.record_query("python advanced tutorial guide", 3, 0.5)
        # Pattern "python advanced tutorial" should have moving average
        pattern_key = self.optimizer._extract_pattern("python advanced tutorial basics")
        p = self.optimizer._patterns[pattern_key]
        assert p.use_count == 2
        # Moving avg: old_weight=(2-1)/2=0.5, new_weight=1/2=0.5
        # 0.5 * 0.9 + 0.5 * 0.5 = 0.7
        assert abs(p.avg_relevance - 0.7) < 0.01

    # 11 — suggest_refinement with ? mark
    def test_suggest_refinement_question_mark(self):
        suggestions = self.optimizer.suggest_refinement("comment faire ?")
        assert any("?" in s for s in suggestions)

    # 12 — suggest_refinement high usage
    def test_suggest_refinement_high_usage(self):
        for _ in range(6):
            self.optimizer.record_query("popular topic search extra", 5, 0.8)
        suggestions = self.optimizer.suggest_refinement("popular topic search more")
        assert any("Pattern utilisé" in s for s in suggestions)

    # 13 — dedup with different URLs
    def test_deduplicate_different_urls(self):
        r = WebResearcher()
        results = [
            SearchResult(url="https://a.com", title="A", snippet="sa", relevance_score=0.8),
            SearchResult(url="https://b.com", title="B", snippet="sb", relevance_score=0.6),
        ]
        deduped = r.deduplicate(results)
        assert len(deduped) == 2
