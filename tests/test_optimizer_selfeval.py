"""
Tests NURU V9 — Learning : StrategyOptimizer, SelfEvaluator.

Vérifie :
  - StrategyOptimizer : analyse, validation, application, historique, résumé
  - SelfEvaluator : faithfulness, relevance, precision, recall, hallucination, overall
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest


# ══════════════════════════════════════════════════════════════════════
# Fixtures communes
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def optimizer_db():
    """Base de données temporaire pour StrategyOptimizer."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    yield tmp.name
    Path(tmp.name).unlink(missing_ok=True)


@pytest.fixture
def optimizer(optimizer_db):
    from src.learning.optimizer import StrategyOptimizer
    return StrategyOptimizer(db_path=optimizer_db)


# ══════════════════════════════════════════════════════════════════════
# StrategyOptimizer
# ══════════════════════════════════════════════════════════════════════


class TestStrategyOptimizer:
    """Tests unitaires pour StrategyOptimizer."""

    def test_optimizer_import(self):
        """Vérifie que StrategyOptimizer s'importe correctement."""
        from src.learning.optimizer import StrategyOptimizer, Adjustment
        assert StrategyOptimizer is not None
        assert Adjustment is not None

    def test_optimizer_analyze_empty_rate_high(self, optimizer):
        """rag_empty_rate > 0.30 → ajustement sur rag_score_threshold."""
        metrics = {
            "rag_empty_rate": 0.45,
            "rag_score_threshold": 0.50,
            "hallucination_rate": 0.0,
            "task_success_rate": 0.90,
        }
        adjustments = optimizer.analyze(metrics)
        # Doit proposer un ajustement sur rag_score_threshold
        rag_adjs = [a for a in adjustments if a.param == "rag_score_threshold"]
        assert len(rag_adjs) == 1
        adj = rag_adjs[0]
        assert adj.current == 0.50
        assert adj.proposed < adj.current  # baisse
        assert "rag_empty_rate" in adj.reason
        assert adj.applied is False

    def test_optimizer_analyze_hallucination_high(self, optimizer):
        """hallucination_rate > 0.10 → ajustement sur cloud_only_threshold."""
        metrics = {
            "rag_empty_rate": 0.0,
            "hallucination_rate": 0.25,
            "cloud_only_threshold": 0.70,
            "task_success_rate": 0.80,
        }
        adjustments = optimizer.analyze(metrics)
        cloud_adjs = [a for a in adjustments if a.param == "cloud_only_threshold"]
        assert len(cloud_adjs) == 1
        adj = cloud_adjs[0]
        assert adj.current == 0.70
        assert adj.proposed < adj.current  # baisse
        assert "hallucination_rate" in adj.reason

    def test_optimizer_analyze_no_issues(self, optimizer):
        """Tout va bien → pas d'ajustement produit."""
        metrics = {
            "rag_empty_rate": 0.05,
            "hallucination_rate": 0.02,
            "task_success_rate": 0.95,
            "rag_score_threshold": 0.50,
            "cloud_only_threshold": 0.70,
            "routing_confidence": 0.80,
        }
        adjustments = optimizer.analyze(metrics)
        # Aucune règle ne devrait se déclencher
        assert len(adjustments) == 0

    def test_optimizer_analyze_low_success_rate(self, optimizer):
        """task_success_rate < 0.50 → ajustement sur routing_confidence."""
        metrics = {
            "rag_empty_rate": 0.0,
            "hallucination_rate": 0.0,
            "task_success_rate": 0.30,
            "routing_confidence": 0.70,
        }
        adjustments = optimizer.analyze(metrics)
        routing_adjs = [a for a in adjustments if a.param == "routing_confidence"]
        assert len(routing_adjs) == 1
        adj = routing_adjs[0]
        assert adj.current == 0.70
        assert adj.proposed < adj.current
        assert "task_success_rate" in adj.reason

    def test_optimizer_validate_within_bounds(self, optimizer):
        """Ajustement valide dans les bornes."""
        from src.learning.optimizer import Adjustment
        adj = Adjustment(
            param="rag_score_threshold",
            current=0.50,
            proposed=0.48,  # delta = 0.02 < 0.05
            reason="Test dans les bornes",
            timestamp=time.time(),
        )
        assert optimizer.validate(adj) is True

    def test_optimizer_validate_exceeds_bounds(self, optimizer):
        """Ajustement qui dépasse les bornes → rejeté."""
        from src.learning.optimizer import Adjustment

        # Delta trop grand
        adj = Adjustment(
            param="rag_score_threshold",
            current=0.50,
            proposed=0.30,  # delta = 0.20 > 0.05
            reason="Delta trop grand",
            timestamp=time.time(),
        )
        assert optimizer.validate(adj) is False

        # Valeur en dessous du minimum
        adj2 = Adjustment(
            param="rag_score_threshold",
            current=0.30,
            proposed=0.10,  # < 0.20 min
            reason="Sous le minimum",
            timestamp=time.time(),
        )
        assert optimizer.validate(adj2) is False

        # Valeur au-dessus du maximum
        adj3 = Adjustment(
            param="rag_score_threshold",
            current=0.50,
            proposed=0.70,  # > 0.60 max
            reason="Au-dessus du max",
            timestamp=time.time(),
        )
        assert optimizer.validate(adj3) is False

    def test_optimizer_validate_prompt_addition(self, optimizer):
        """prompt_addition n'a pas de limites → toujours valide."""
        from src.learning.optimizer import Adjustment
        adj = Adjustment(
            param="prompt_addition",
            current="",
            proposed="Ajouter vérification des sources",
            reason="Test prompt",
            timestamp=time.time(),
        )
        assert optimizer.validate(adj) is True

    def test_optimizer_apply_and_history(self, optimizer):
        """Appliquer un ajustement et vérifier l'historique."""
        from src.learning.optimizer import Adjustment
        adj = Adjustment(
            param="rag_score_threshold",
            current=0.50,
            proposed=0.48,
            reason="Test historique",
            timestamp=time.time(),
        )
        # Appliquer
        result = optimizer.apply(adj)
        assert result is True
        assert adj.applied is True

        # Vérifier l'historique
        history = optimizer.get_history(limit=10)
        assert len(history) == 1
        entry = history[0]
        assert entry["param"] == "rag_score_threshold"
        assert entry["old_value"] == "0.5"
        assert entry["new_value"] == "0.48"
        assert entry["reason"] == "Test historique"
        assert entry["applied"] is True
        assert "id" in entry
        assert "timestamp" in entry

    def test_optimizer_apply_invalid(self, optimizer):
        """Appliquer un ajustement invalide → False."""
        from src.learning.optimizer import Adjustment
        adj = Adjustment(
            param="rag_score_threshold",
            current=0.50,
            proposed=0.10,  # Trop bas
            reason="Invalide",
            timestamp=time.time(),
        )
        result = optimizer.apply(adj)
        assert result is False
        assert adj.applied is False

        # Historique vide
        history = optimizer.get_history()
        assert len(history) == 0

    def test_optimizer_get_summary(self, optimizer):
        """Résumé des ajustements."""
        from src.learning.optimizer import Adjustment

        # Appliquer 3 ajustements
        for param, old, new in [
            ("rag_score_threshold", 0.50, 0.48),
            ("rag_score_threshold", 0.48, 0.46),
            ("cloud_only_threshold", 0.70, 0.68),
        ]:
            adj = Adjustment(
                param=param, current=old, proposed=new,
                reason=f"Ajustement {param}", timestamp=time.time(),
            )
            optimizer.apply(adj)

        summary = optimizer.get_summary()
        assert summary["total_adjustments"] == 3
        assert summary["params_modified"] == 2
        assert summary["by_param"]["rag_score_threshold"] == 2
        assert summary["by_param"]["cloud_only_threshold"] == 1
        assert len(summary["trend"]) == 3
        assert isinstance(summary["recent_week_count"], int)
        assert summary["recent_week_count"] == 3  # tout est dans la dernière semaine

    def test_optimizer_empty_history(self, optimizer):
        """Historique vide."""
        history = optimizer.get_history()
        assert history == []

    def test_optimizer_empty_summary(self, optimizer):
        """Résumé sur base vide."""
        summary = optimizer.get_summary()
        assert summary["total_adjustments"] == 0
        assert summary["params_modified"] == 0
        assert summary["by_param"] == {}
        assert summary["trend"] == []
        assert summary["recent_week_count"] == 0


# ══════════════════════════════════════════════════════════════════════
# SelfEvaluator
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def evaluator():
    from src.learning.self_eval import SelfEvaluator
    return SelfEvaluator()


class TestSelfEvaluator:
    """Tests unitaires pour SelfEvaluator."""

    def test_evaluator_import(self):
        """Vérifie que SelfEvaluator s'importe correctement."""
        from src.learning.self_eval import SelfEvaluator, EvalResult
        assert SelfEvaluator is not None
        assert EvalResult is not None

    def test_evaluator_faithfulness_high(self, evaluator):
        """Réponse supportée par les sources → score élevé."""
        sources = [
            "Le chat est un mammifère carnivore de la famille des félidés.",
            "Les chats domestiques pèsent entre 3 et 5 kg en moyenne.",
            "L'espérance de vie d'un chat est de 12 à 15 ans.",
        ]
        response = "Le chat est un mammifère carnivore. Il pèse entre 3 et 5 kg."
        score = evaluator._check_faithfulness(response, sources)
        assert score >= 0.5  # Au moins une phrase supportée

    def test_evaluator_faithfulness_low(self, evaluator):
        """Réponse non supportée par les sources → score bas."""
        sources = [
            "Les roses sont des fleurs de la famille des Rosaceae.",
        ]
        response = "Les chats volent dans les airs avec des ailes."
        score = evaluator._check_faithfulness(response, sources)
        assert score < 0.5  # Affirmations non supportées

    def test_evaluator_faithfulness_no_sources(self, evaluator):
        """Pas de sources → score neutre (0.5)."""
        score = evaluator._check_faithfulness(
            "Le ciel est bleu.",
            [],
        )
        assert score == 0.5

    def test_evaluator_relevance_high(self, evaluator):
        """Réponse pertinente qui contient les mots-clés de la requête."""
        query = "Quelle est la capitale de la France ?"
        response = "La capitale de la France est Paris, située dans le nord du pays."
        score = evaluator._check_relevance(query, response)
        assert score > 0.5  # Au moins "capitale" et "France" dans la réponse
        assert score <= 1.0

    def test_evaluator_relevance_low(self, evaluator):
        """Réponse hors-sujet qui ne contient pas les mots-clés."""
        query = "Quelle est la capitale de la France ?"
        response = "Il fait beau aujourd'hui."
        score = evaluator._check_relevance(query, response)
        assert score == 0.0  # Aucun mot-clé trouvé

    def test_evaluator_relevance_empty(self, evaluator):
        """Requête vide → score 0."""
        score = evaluator._check_relevance("", "Réponse quelconque")
        assert score == 0.0

    def test_evaluator_precision_high(self, evaluator):
        """Contexte pertinent par rapport à la requête."""
        context = (
            "La capitale de la France est Paris. "
            "Paris est une grande ville européenne. "
            "La France est un pays d'Europe occidentale."
        )
        query = "Quelle est la capitale de la France ?"
        score = evaluator._check_precision(context, query)
        assert score > 0.5

    def test_evaluator_precision_empty(self, evaluator):
        """Contexte vide → score 0."""
        score = evaluator._check_precision("", "Requête")
        assert score == 0.0

    def test_evaluator_recall_high(self, evaluator):
        """Contexte couvre les sources."""
        context = "Paris est la capitale de la France. Les roses sont rouges."
        sources = [
            "Paris est la capitale de la France.",
            "Les roses sont rouges et les violettes sont bleues.",
        ]
        score = evaluator._check_recall(context, sources)
        assert score > 0.5  # Au moins la première source est couverte

    def test_evaluator_recall_low(self, evaluator):
        """Contexte ne couvre pas les sources."""
        context = "Il fait beau aujourd'hui."
        sources = ["Paris est la capitale de la France."]
        score = evaluator._check_recall(context, sources)
        assert score == 0.0  # Aucune source couverte

    def test_evaluator_recall_no_sources(self, evaluator):
        """Pas de sources → score neutre (0.5)."""
        score = evaluator._check_recall("Du texte de contexte.", [])
        assert score == 0.5

    def test_evaluator_hallucination(self, evaluator):
        """Affirmations non supportées → score d'hallucination bas.

        Deux phrases : une supportée (mots-clés dans les sources),
        une non supportée (aucun mot-clé commun avec les sources).
        faithfulness = 0.5 → hallucination_score = 1.0 - 0.5 = 0.5
        """
        sources = ["Paris est la capitale de la France."]
        response = "Paris est la capitale de la France. Les chats sont des animaux."
        score = evaluator._check_hallucination(response, sources)
        # Une phrase supportée sur deux → faithfulness ≈ 0.5 → hallucination_score ≈ 0.5
        assert 0.3 < score < 0.8, f"Score inattendu: {score}"

    def test_evaluator_hallucination_no_sources(self, evaluator):
        """Pas de sources → score neutre (0.6)."""
        score = evaluator._check_hallucination("Du texte.", [])
        assert score == 0.6

    def test_evaluator_overall_score(self, evaluator):
        """Vérifie la moyenne pondérée overall."""
        result = evaluator.evaluate(
            query="Quelle est la capitale de la France ?",
            response="La capitale de la France est Paris.",
            sources=["Paris est la capitale de la France."],
            context="La capitale de la France est Paris.",
        )
        # Tous les scores doivent être dans [0, 1]
        assert 0.0 <= result.faithfulness <= 1.0
        assert 0.0 <= result.answer_relevance <= 1.0
        assert 0.0 <= result.context_precision <= 1.0
        assert 0.0 <= result.context_recall <= 1.0
        assert 0.0 <= result.hallucination_score <= 1.0
        assert 0.0 <= result.overall <= 1.0

    def test_evaluator_no_sources(self, evaluator):
        """Pas de sources → scores par défaut raisonnables."""
        result = evaluator.evaluate(
            query="Quel temps fait-il ?",
            response="Il fait beau aujourd'hui.",
            sources=None,
            context="",
        )
        # faithfulness = 0.5 (neutre, pas de sources)
        assert result.faithfulness == 0.5
        # hallucination = 0.6 (neutre, pas de sources)
        assert result.hallucination_score == 0.6
        # context_precision = 0.0 (contexte vide)
        assert result.context_precision == 0.0
        # context_recall = 0.5 (pas de sources)
        assert result.context_recall == 0.5
        # overall doit être calculé
        assert result.overall > 0.0

    def test_evaluator_empty_response(self, evaluator):
        """Réponse vide → scores à 0."""
        result = evaluator.evaluate(
            query="Question ?",
            response="",
            sources=["Source de test."],
            context="Contexte de test.",
        )
        assert result.faithfulness == 0.0
        assert result.answer_relevance == 0.0

    def test_evaluator_sentence_splitting(self, evaluator):
        """Vérifie le découpage en phrases."""
        sentences = evaluator._split_sentences(
            "Première phrase. Deuxième phrase! Troisième phrase?"
        )
        assert len(sentences) == 3
        assert sentences[0] == "Première phrase."
        assert sentences[1] == "Deuxième phrase!"
        assert sentences[2] == "Troisième phrase?"
