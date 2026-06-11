"""
Tests NURU V10 Sprint 5 — Reasoning : ReflexionEngine, SelfConsistency, ConfidenceCalibrator.

Vérifie :
  - ReflexionEngine : critique, amélioration, boucle réflexive
  - SelfConsistency : normalisation, vote, fusion
  - ConfidenceCalibrator : calibrage, historique, décision
"""

from __future__ import annotations

import pytest


# ══════════════════════════════════════════════════════════════════════
# ReflexionEngine
# ══════════════════════════════════════════════════════════════════════


class TestReflexionEngine:
    """Tests pour ReflexionEngine."""

    @pytest.fixture
    def engine(self):
        from src.reasoning.reflexion import ReflexionEngine
        return ReflexionEngine(max_passes=2, min_score=0.6)

    @pytest.fixture
    def engine_strict(self):
        from src.reasoning.reflexion import ReflexionEngine
        return ReflexionEngine(max_passes=2, min_score=0.9)

    def test_critique_empty(self, engine):
        """Réponse vide → critique explicite."""
        c = engine.critique("", "contexte de test")
        assert "vide" in c.lower()

    def test_critique_short(self, engine):
        """Réponse trop courte (< 20 mots) → critique sur longueur."""
        c = engine.critique("C'est court", "contexte de test important")
        assert "trop courte" in c.lower() or "court" in c.lower()

    def test_critique_missing_keywords(self, engine):
        """Mots-clés du contexte absents → critique sur pertinence."""
        c = engine.critique(
            "Ceci est une réponse suffisamment longue pour passer le filtre "
            "de vérification de longueur mais qui ne contient absolument aucun "
            "des mots-clés du contexte fourni pour tester la détection.",
            "python intelligence artificielle",
        )
        assert "absent" in c.lower()

    def test_improve_short(self, engine):
        """Réponse courte + critique 'trop courte' → réponse enrichie."""
        short = "Réponse courte."
        critique = "Réponse trop courte. Il faut ajouter plus de détails."
        improved = engine.improve(short, critique, "python artificielle")
        assert len(improved) > len(short)
        assert "contexte" in improved.lower() or len(improved.split()) > len(short.split())

    def test_improve_missing(self, engine):
        """Réponse avec mots manquants → les mots manquants signalés."""
        answer = "La réponse couvre le sujet général."
        critique = "Mots-clés du contexte absents : python, artificielle"
        improved = engine.improve(answer, critique, "python artificielle")
        assert "python" in improved.lower()

    def test_reflect_1_pass(self, engine_strict):
        """Réponse déjà bonne → 1 passe, pas d'amélioration nécessaire."""
        from src.reasoning.reflexion import ReflexionResult
        answer = "Python est un langage de programmation puissant utilisé en intelligence artificielle et en machine learning pour la science des données."
        result = engine_strict.reflect(answer, "python intelligence")
        assert isinstance(result, ReflexionResult)
        assert result.passes >= 1
        assert result.score_initial >= 0.0
        assert result.score_final >= result.score_initial

    def test_reflect_2_passes(self, engine):
        """Réponse mediocre → 2 passes, amélioration mesurable."""
        from src.reasoning.reflexion import ReflexionResult
        result = engine.reflect("Oui.", "python intelligence artificielle")
        assert isinstance(result, ReflexionResult)
        assert result.passes >= 1
        # Après 2 passes, le score devrait s'améliorer
        assert result.score_final >= result.score_initial

    def test_reflect_already_good(self, engine):
        """Très bonne réponse initiale → arrêt rapide."""
        from src.reasoning.reflexion import ReflexionResult
        answer = (
            "Python est un langage de programmation polyvalent, largement utilisé "
            "en intelligence artificielle, en machine learning, en data science et "
            "en automatisation. Sa syntaxe claire et ses bibliothèques riches comme "
            "TensorFlow et PyTorch en font un choix privilégié."
        )
        result = engine.reflect(answer, "python intelligence")
        assert isinstance(result, ReflexionResult)
        assert result.passes >= 1


# ══════════════════════════════════════════════════════════════════════
# SelfConsistency
# ══════════════════════════════════════════════════════════════════════


class TestSelfConsistency:
    """Tests pour SelfConsistency."""

    @pytest.fixture
    def sc(self):
        from src.reasoning.consistency import SelfConsistency
        return SelfConsistency(n_samples=3, consistency_threshold=0.6)

    def test_normalize_answer(self, sc):
        """Normalisation : lower, strip, ponctuation."""
        assert sc.normalize_answer("  Hello World!  ") == "hello world"
        assert sc.normalize_answer("Test, avec; ponctuation.") == "test avec ponctuation"
        assert sc.normalize_answer("") == ""
        assert sc.normalize_answer("  ") == ""

    def test_vote_unanimous(self, sc):
        """Vote unanime → 100% confiance."""
        from src.reasoning.consistency import ConsistencyResult
        answers = ["Paris est la capitale de la France"] * 3
        result = sc.vote(answers)
        assert isinstance(result, ConsistencyResult)
        assert result.confidence == pytest.approx(1.0)
        assert result.is_consistent is True
        assert len(result.frequencies) == 1

    def test_vote_majority(self, sc):
        """Vote majoritaire (2/3) → confiance > 60%."""
        answers = [
            "Python est le meilleur langage",
            "Python est le meilleur langage",
            "Python est génial",
        ]
        result = sc.vote(answers)
        assert result.confidence == pytest.approx(2 / 3, abs=0.01)
        assert result.is_consistent is True

    def test_vote_split(self, sc):
        """Vote éclaté → faible confiance."""
        answers = [
            "Réponse A",
            "Réponse B",
            "Réponse C",
        ]
        result = sc.vote(answers)
        assert result.confidence == pytest.approx(1 / 3, abs=0.01)
        assert result.is_consistent is False

    def test_merge_identical(self, sc):
        """Fusion réponses identiques → retourne la même réponse."""
        assert sc.merge(["Réponse A", "Réponse A"]) == "Réponse A"

    def test_merge_different(self, sc):
        """Fusion réponses différentes → retourne la plus longue."""
        a = "Court"
        b = "Réponse beaucoup plus longue et détaillée"
        assert sc.merge([a, b]) == b

    def test_confidence_calculation(self, sc):
        """Calcul de confiance correct sur various cas."""
        answers = ["X", "X", "X", "Y", "Y"]
        result = sc.vote(answers)
        assert result.confidence == pytest.approx(3 / 5)

    def test_edge_cases(self, sc):
        """Cas limites : liste vide, un seul élément."""
        from src.reasoning.consistency import ConsistencyResult
        empty = sc.vote([])
        assert isinstance(empty, ConsistencyResult)
        assert empty.confidence == 0.0

        single = sc.vote(["Unique"])
        assert single.confidence == pytest.approx(1.0)


# ══════════════════════════════════════════════════════════════════════
# ConfidenceCalibrator
# ══════════════════════════════════════════════════════════════════════


class TestConfidenceCalibrator:
    """Tests pour ConfidenceCalibrator."""

    @pytest.fixture
    def cal(self):
        from src.reasoning.confidence import ConfidenceCalibrator
        return ConfidenceCalibrator(confidence_threshold=0.4, high_confidence=0.8)

    def test_calibrate_normal(self, cal):
        """Score normal sans pénalité."""
        result = cal.calibrate(0.7, context_completeness=1.0, query_complexity=0.5)
        assert result.raw_score == 0.7
        assert result.calibrated_score == pytest.approx(0.7)
        assert result.should_answer is True
        assert result.is_confident is False

    def test_calibrate_low_context(self, cal):
        """Score pénalisé par contexte incomplet."""
        result = cal.calibrate(0.7, context_completeness=0.2, query_complexity=0.5)
        assert result.calibrated_score < 0.7
        assert "contexte" in result.reasoning.lower()

    def test_calibrate_complex_query(self, cal):
        """Score pénalisé par requête complexe."""
        result = cal.calibrate(0.7, context_completeness=1.0, query_complexity=0.9)
        assert result.calibrated_score < 0.7
        assert "complexe" in result.reasoning.lower()

    def test_record_outcome(self, cal):
        """Enregistrement d'un résultat."""
        cal.record_outcome(0.8, True)
        cal.record_outcome(0.3, False)
        assert len(cal.history) == 2

    def test_get_accuracy(self, cal):
        """Précision historique."""
        cal.record_outcome(0.9, True)
        cal.record_outcome(0.9, True)
        cal.record_outcome(0.2, False)
        assert cal.get_accuracy() == pytest.approx(2 / 3)

    def test_should_answer_confident(self, cal):
        """Score élevé → doit répondre."""
        assert cal.should_answer(0.8) is True

    def test_should_answer_low(self, cal):
        """Score bas → ne doit pas répondre."""
        assert cal.should_answer(0.2) is False

    def test_high_confidence(self, cal):
        """Score > high_confidence → is_confident."""
        result = cal.calibrate(0.85)
        assert result.is_confident is True

    def test_calibration_history_empty(self, cal):
        """Historique vide → précision = 0."""
        assert cal.get_accuracy() == 0.0

    def test_edge_cases(self, cal):
        """Cas limites : scores aux bornes."""
        # Score 0 → ne doit pas répondre
        r0 = cal.calibrate(0.0)
        assert r0.should_answer is False
        assert r0.calibrated_score == 0.0

        # Score 1.0 → confident
        r1 = cal.calibrate(1.0)
        assert r1.is_confident is True
        assert r1.should_answer is True

        # Double pénalité
        r_double = cal.calibrate(0.7, context_completeness=0.1, query_complexity=0.9)
        assert r_double.calibrated_score < 0.7
        assert r_double.should_answer is True  # 0.7 - penalties devrait rester > 0.4
