"""
Tests NURU V9 — Learning : FeedbackCollector, PerformanceTracker.

Vérifie :
  - FeedbackCollector : enregistrement thumbs, corrections, ratings, stats
  - PerformanceTracker : enregistrement, agrégation, tendances, helpers
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest


# ══════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def feedback_db():
    """Base de données temporaire pour FeedbackCollector."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    yield tmp.name
    Path(tmp.name).unlink(missing_ok=True)


@pytest.fixture
def tracker_db():
    """Base de données temporaire pour PerformanceTracker."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    yield tmp.name
    Path(tmp.name).unlink(missing_ok=True)


@pytest.fixture
def collector(feedback_db):
    from src.learning.feedback import FeedbackCollector
    return FeedbackCollector(db_path=feedback_db)


@pytest.fixture
def tracker(tracker_db):
    from src.learning.tracker import PerformanceTracker
    return PerformanceTracker(db_path=tracker_db)


@pytest.fixture
def seeded_collector(collector):
    """Collecteur pré-rempli avec divers feedbacks."""
    # 3 thumbs up
    for i in range(3):
        collector.record_thumbs(
            f"question_{i}", f"réponse_{i}", is_positive=True,
            session_id="test_ses",
        )
        time.sleep(0.001)
    # 1 thumbs down
    collector.record_thumbs(
        "mauvaise_question", "mauvaise_réponse", is_positive=False,
        session_id="test_ses",
    )
    time.sleep(0.001)
    # 2 corrections
    for i in range(2):
        collector.record_correction(
            f"query_{i}", f"response_{i}",
            correction=f"correction_{i}", session_id="test_ses",
        )
        time.sleep(0.001)
    # 2 ratings
    collector.record_rating("bof", "réponse médiocre", rating=2, session_id="test_ses")
    time.sleep(0.001)
    collector.record_rating("super", "excellente réponse", rating=5, session_id="test_ses")
    time.sleep(0.001)
    # 1 clarification
    collector.record_clarification(
        "vague", "réponse vague", clarification="plus précis SVP",
        session_id="test_ses",
    )
    return collector


@pytest.fixture
def seeded_tracker(tracker):
    """Tracker pré-rempli avec diverses métriques."""
    # RAG metrics
    tracker.record_rag_result("doc query", recall5=0.8, avg_score=0.75, empty=False)
    tracker.record_rag_result("rare query", recall5=0.3, avg_score=0.4, empty=True)
    # Response metrics
    tracker.record_response_metrics(
        response_time_ms=1200, tokens=350, hallucination=False, has_citation=True,
        tags={"model": "qwen2.5"},
    )
    tracker.record_response_metrics(
        response_time_ms=800, tokens=200, hallucination=True, has_citation=False,
    )
    # Agent metrics
    tracker.record_agent_result(success=True, steps=5, recovery=False)
    tracker.record_agent_result(success=True, steps=8, recovery=True)
    tracker.record_agent_result(success=False, steps=3, recovery=True)
    # Feedback metrics
    tracker.record_feedback_metrics(thumbs_up=True)
    tracker.record_feedback_metrics(thumbs_down=True, rating=2)
    return tracker


# ══════════════════════════════════════════════════════════════════════
# FeedbackCollector
# ══════════════════════════════════════════════════════════════════════


class TestFeedbackCollector:
    """Tests unitaires pour FeedbackCollector."""

    def test_feedback_import(self):
        """Vérifie que FeedbackCollector s'importe correctement."""
        from src.learning.feedback import FeedbackCollector
        assert FeedbackCollector is not None

    def test_feedback_via_init(self):
        """Vérifie que FeedbackCollector est accessible via __init__.py."""
        from src.learning import FeedbackCollector
        assert FeedbackCollector is not None

    def test_feedback_record_thumbs_up(self, collector):
        """Enregistrement d'un thumbs up."""
        fb_id = collector.record_thumbs(
            "Comment ça va ?", "Bien merci !", is_positive=True,
        )
        assert fb_id is not None
        assert len(fb_id) > 0
        assert collector.count() == 1

    def test_feedback_record_thumbs_down(self, collector):
        """Enregistrement d'un thumbs down."""
        fb_id = collector.record_thumbs(
            "Mauvaise question", "Mauvaise réponse", is_positive=False,
        )
        assert fb_id is not None
        assert collector.count() == 1

    def test_feedback_record_correction(self, collector):
        """Enregistrement d'une correction explicite."""
        fb_id = collector.record_correction(
            "Quelle est la capitale ?",
            "La capitale est Londres.",
            correction="La capitale est Paris.",
        )
        assert fb_id is not None
        assert collector.count() == 1

    def test_feedback_record_rating(self, collector):
        """Enregistrement d'un rating 1-5."""
        fb_id = collector.record_rating(
            "Excellent travail", "Merci !", rating=5,
        )
        assert fb_id is not None
        assert collector.count() == 1

    def test_feedback_record_rating_invalid(self, collector):
        """Un rating hors bornes doit lever ValueError."""
        with pytest.raises(ValueError):
            collector.record_rating("test", "test", rating=0)
        with pytest.raises(ValueError):
            collector.record_rating("test", "test", rating=6)

    def test_feedback_get_stats(self, seeded_collector):
        """Vérifie les statistiques après enregistrement."""
        stats = seeded_collector.get_stats()

        assert stats["total"] == 9
        assert stats["thumbs_up"] == 3
        assert stats["thumbs_down"] == 1
        assert stats["corrections"] == 2
        assert stats["ratings"] == 2
        assert stats["clarifications"] == 1
        assert stats["satisfaction_rate"] == pytest.approx(0.75, rel=0.01)
        assert stats["avg_rating"] == pytest.approx(3.5, rel=0.01)

    def test_feedback_get_recent(self, seeded_collector):
        """Vérifie que get_recent retourne les feedbacks récents."""
        recent = seeded_collector.get_recent(limit=5)

        assert len(recent) <= 5
        assert len(recent) > 0
        # Vérifie la structure d'un item
        item = recent[0]
        assert "id" in item
        assert "timestamp" in item
        assert "feedback_type" in item
        assert "query" in item
        assert "response" in item
        # Ordre décroissant
        if len(recent) >= 2:
            assert recent[0]["timestamp"] >= recent[1]["timestamp"]

    def test_feedback_get_corrections(self, seeded_collector):
        """Vérifie que get_corrections filtre par type."""
        corrections = seeded_collector.get_corrections(limit=10)

        assert len(corrections) == 2
        for c in corrections:
            assert c["feedback_type"] == "correction"

    def test_feedback_empty_db(self, collector):
        """Vérifie le comportement sur base vide."""
        assert collector.count() == 0
        stats = collector.get_stats()
        assert stats["total"] == 0
        assert stats["satisfaction_rate"] == 0.0
        assert stats["avg_rating"] == 0.0
        assert collector.get_recent(limit=5) == []
        assert collector.get_corrections(limit=5) == []

    def test_feedback_record_clarification(self, collector):
        """Enregistrement d'une clarification."""
        fb_id = collector.record_clarification(
            "météo", "Il fait beau", clarification="Quel temps à Paris ?"
        )
        assert fb_id is not None
        assert collector.count() == 1

    def test_feedback_round_trip(self, collector):
        """Vérifie le cycle complet enregistrement → lecture."""
        collector.record_thumbs("test", "test", is_positive=True, session_id="s1")
        collector.record_rating("test2", "test2", rating=3, session_id="s1")
        recent = collector.get_recent(limit=10)
        assert len(recent) == 2
        # Vérifie les types
        types = {r["feedback_type"] for r in recent}
        assert "thumbs_up" in types
        assert "rating" in types

    def test_feedback_correction_no_memory(self, feedback_db):
        """Correction sans MemoryManager : pas d'erreur, pas d'error_id."""
        from src.learning.feedback import FeedbackCollector
        c = FeedbackCollector(db_path=feedback_db, memory_manager=None)
        fb_id = c.record_correction("q", "r", correction="fix")
        # Récupère l'entrée
        recent = c.get_recent(limit=1)
        assert recent[0]["error_id"] == ""


# ══════════════════════════════════════════════════════════════════════
# PerformanceTracker
# ══════════════════════════════════════════════════════════════════════


class TestPerformanceTracker:
    """Tests unitaires pour PerformanceTracker."""

    def test_tracker_import(self):
        """Vérifie que PerformanceTracker s'importe correctement."""
        from src.learning.tracker import PerformanceTracker
        assert PerformanceTracker is not None

    def test_tracker_via_init(self):
        """Vérifie que PerformanceTracker est accessible via __init__.py."""
        from src.learning import PerformanceTracker
        assert PerformanceTracker is not None

    def test_tracker_record_and_retrieve(self, tracker):
        """Enregistrement et récupération d'une métrique."""
        mid = tracker.record("test_metric", 42.5, category="general",
                              tags={"env": "test"})
        assert mid is not None
        assert tracker.count() == 1

    def test_tracker_record_multiple(self, tracker):
        """Enregistrement de plusieurs métriques."""
        tracker.record("m1", 1.0, category="rag")
        tracker.record("m2", 2.0, category="rag")
        tracker.record("m3", 3.0, category="response")
        assert tracker.count() == 3

    def test_tracker_get_averages(self, seeded_tracker):
        """Vérifie les moyennes par catégorie."""
        rag_avgs = seeded_tracker.get_averages(category="rag", since_hours=24)

        assert "rag_recall@5" in rag_avgs
        assert "rag_avg_score" in rag_avgs
        assert "rag_empty" in rag_avgs
        # recall@5 moyen des 2 entrées : (0.8 + 0.3) / 2 = 0.55
        assert rag_avgs["rag_recall@5"] == pytest.approx(0.55, rel=0.05)
        # avg_score moyen : (0.75 + 0.4) / 2 = 0.575
        assert rag_avgs["rag_avg_score"] == pytest.approx(0.575, rel=0.05)

    def test_tracker_get_averages_all(self, seeded_tracker):
        """Vérifie les moyennes toutes catégories confondues."""
        all_avgs = seeded_tracker.get_averages(category=None, since_hours=24)

        assert "rag_recall@5" in all_avgs
        assert "response_time_ms" in all_avgs
        assert "agent_task_success" in all_avgs
        assert "feedback_thumbs_up" in all_avgs

    def test_tracker_get_trend(self, seeded_tracker):
        """Vérifie la tendance d'une métrique sur plusieurs jours."""
        trend = seeded_tracker.get_trend("rag_recall@5", days=7)

        assert len(trend) >= 1
        entry = trend[0]
        assert "date" in entry
        assert "avg_value" in entry
        assert "count" in entry
        # La valeur agrégée doit être dans l'intervalle
        assert 0.0 <= entry["avg_value"] <= 1.0

    def test_tracker_get_trend_no_data(self, tracker):
        """Tendance sur une métrique inexistante."""
        trend = tracker.get_trend("nonexistent_metric", days=7)
        assert trend == []

    def test_tracker_get_summary(self, seeded_tracker):
        """Vérifie le rapport synthétique."""
        summary = seeded_tracker.get_summary()

        # Vérifie la structure
        assert "rag" in summary
        assert "response" in summary
        assert "agent" in summary
        assert "feedback" in summary
        assert "total_points" in summary
        assert "period_hours" in summary

        # Vérifie les clés internes
        assert "recall@5" in summary["rag"]
        assert "avg_score" in summary["rag"]
        assert "empty_rate" in summary["rag"]
        assert "hyde_trigger_rate" in summary["rag"]

        assert "avg_response_time_ms" in summary["response"]
        assert "avg_tokens" in summary["response"]
        assert "hallucination_rate" in summary["response"]
        assert "citation_rate" in summary["response"]

        assert "task_success_rate" in summary["agent"]
        assert "avg_steps_per_task" in summary["agent"]
        assert "error_recovery_rate" in summary["agent"]

        assert "thumbs_up_rate" in summary["feedback"]
        assert "thumbs_down_rate" in summary["feedback"]
        assert "correction_rate" in summary["feedback"]
        assert "avg_rating" in summary["feedback"]

        assert summary["total_points"] >= 10
        assert summary["period_hours"] == 24

    def test_tracker_rag_metrics_helper(self, tracker):
        """Helper record_rag_result et get_rag_metrics."""
        tracker.record_rag_result("test query", recall5=0.9, avg_score=0.85, empty=False)

        metrics = tracker.get_rag_metrics()
        assert metrics["recall@5"] == pytest.approx(0.9, rel=0.01)
        assert metrics["avg_score"] == pytest.approx(0.85, rel=0.01)
        assert metrics["empty_rate"] == pytest.approx(0.0, abs=0.01)
        assert "hyde_trigger_rate" in metrics
        assert tracker.count() == 4  # 4 metrics recorded

    def test_tracker_rag_metrics_empty(self, tracker):
        """Helper record_rag_result avec empty=True."""
        tracker.record_rag_result("rare", recall5=0.0, avg_score=0.0, empty=True)
        metrics = tracker.get_rag_metrics()
        assert metrics["empty_rate"] == pytest.approx(1.0, abs=0.01)

    def test_tracker_agent_metrics_helper(self, tracker):
        """Helper record_agent_result et get_agent_metrics."""
        tracker.record_agent_result(success=True, steps=5, recovery=False)
        tracker.record_agent_result(success=False, steps=3, recovery=True)

        metrics = tracker.get_agent_metrics()
        assert metrics["task_success_rate"] == pytest.approx(0.5, rel=0.05)
        assert metrics["avg_steps_per_task"] == pytest.approx(4.0, rel=0.05)
        assert metrics["error_recovery_rate"] == pytest.approx(0.5, rel=0.05)
        assert tracker.count() == 6  # 3 metrics × 2 calls

    def test_tracker_response_metrics_helper(self, tracker):
        """Helper record_response_metrics et get_response_metrics."""
        tracker.record_response_metrics(
            response_time_ms=1000, tokens=300, hallucination=False, has_citation=True,
        )
        metrics = tracker.get_response_metrics()
        assert metrics["avg_response_time_ms"] == pytest.approx(1000.0, rel=0.01)
        assert metrics["avg_tokens"] == pytest.approx(300.0, rel=0.01)
        assert metrics["hallucination_rate"] == pytest.approx(0.0, abs=0.01)
        assert metrics["citation_rate"] == pytest.approx(1.0, abs=0.01)

    def test_tracker_feedback_metrics_helper(self, tracker):
        """Helper record_feedback_metrics et get_feedback_metrics."""
        tracker.record_feedback_metrics(thumbs_up=True, rating=4)
        tracker.record_feedback_metrics(thumbs_down=True)

        metrics = tracker.get_feedback_metrics()
        assert metrics["thumbs_up_rate"] == pytest.approx(0.5, rel=0.05)
        assert metrics["thumbs_down_rate"] == pytest.approx(0.5, rel=0.05)
        assert metrics["avg_rating"] == pytest.approx(4.0, rel=0.05)

    def test_tracker_get_rag_metrics_empty(self, tracker):
        """get_rag_metrics sur base vide."""
        metrics = tracker.get_rag_metrics()
        assert metrics["recall@5"] == 0.0
        assert metrics["avg_score"] == 0.0
        assert metrics["empty_rate"] == 0.0
        assert metrics["hyde_trigger_rate"] == 0.0

    def test_tracker_get_response_metrics_empty(self, tracker):
        """get_response_metrics sur base vide."""
        metrics = tracker.get_response_metrics()
        assert metrics["avg_response_time_ms"] == 0.0
        assert metrics["avg_tokens"] == 0.0

    def test_tracker_get_agent_metrics_empty(self, tracker):
        """get_agent_metrics sur base vide."""
        metrics = tracker.get_agent_metrics()
        assert metrics["task_success_rate"] == 0.0
        assert metrics["avg_steps_per_task"] == 0.0

    def test_tracker_get_feedback_metrics_empty(self, tracker):
        """get_feedback_metrics sur base vide."""
        metrics = tracker.get_feedback_metrics()
        assert metrics["thumbs_up_rate"] == 0.0
        assert metrics["thumbs_down_rate"] == 0.0

    def test_tracker_get_averages_empty(self, tracker):
        """get_averages sur base vide."""
        avgs = tracker.get_averages(category="rag", since_hours=24)
        assert avgs == {}

    def test_tracker_empty_db(self, tracker):
        """Vérifie le comportement sur base vide."""
        assert tracker.count() == 0
        summary = tracker.get_summary()
        assert summary["total_points"] == 0
        for cat_key in ("rag", "response", "agent", "feedback"):
            for val in summary[cat_key].values():
                assert val == 0.0

    def test_tracker_category_specific(self, seeded_tracker):
        """Vérifie que les getters par catégorie sont cohérents."""
        rag = seeded_tracker.get_rag_metrics()
        response = seeded_tracker.get_response_metrics()
        agent = seeded_tracker.get_agent_metrics()
        feedback = seeded_tracker.get_feedback_metrics()

        # RAG
        assert rag["recall@5"] > 0
        # Response
        assert response["avg_response_time_ms"] > 0
        # Agent
        assert agent["task_success_rate"] == pytest.approx(2 / 3, rel=0.05)
        # Feedback
        assert feedback["thumbs_up_rate"] > 0 or feedback["thumbs_down_rate"] > 0

    def test_tracker_tags(self, tracker):
        """Vérifie que les tags sont bien stockés."""
        tracker.record("tagged_metric", 1.0, category="test", tags={"key": "val", "num": 42})
        # Vérification indirecte : les données sont persistées
        assert tracker.count() == 1
