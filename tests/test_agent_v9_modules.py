"""
Tests NURU V9 — Agent : TaskVerifier, ErrorRecovery, ResumeManager.

Vérifie :
  - TaskVerifier : validation des résultats d'étape
  - ErrorRecovery : décision de récupération par type d'erreur
  - ResumeManager : persistance et restauration de l'état des tâches
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.agent.types import (
    ErrorType,
    RecoveryAction,
    RecoveryDecision,
    StepResult,
    TaskStatus,
    TaskStep,
    ToolCall,
)


# ══════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def verifier():
    from src.agent.verifier import TaskVerifier

    return TaskVerifier()


@pytest.fixture
def recovery():
    from src.agent.recovery import ErrorRecovery

    return ErrorRecovery()


@pytest.fixture
def resume():
    from src.agent.resume import ResumeManager

    # Base de données temporaire
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    mgr = ResumeManager(db_path=db_path)
    yield mgr
    # Nettoyage
    Path(db_path).unlink(missing_ok=True)


# ══════════════════════════════════════════════════════════════════════
# TaskVerifier
# ══════════════════════════════════════════════════════════════════════


class TestTaskVerifier:
    """Tests unitaires pour TaskVerifier."""

    def test_verifier_import(self):
        """Vérifie que TaskVerifier s'importe correctement."""
        from src.agent.verifier import TaskVerifier

        assert TaskVerifier is not None

    def test_verifier_success(self, verifier):
        """Vérifie qu'un résultat valide est accepté (output non vide, pas d'erreur)."""
        step = TaskStep(
            description="Tester résultat valide",
            tool_calls=[ToolCall(tool_name="search_rag")],
        )
        result = StepResult(
            step_id=step.step_id,
            status=TaskStatus.COMPLETED,
            output="Données collectées avec succès",
            confidence=0.85,
        )
        is_ok, score, reason = verifier.verify(step, result)

        assert is_ok is True
        assert score >= 0.8
        assert "valide" in reason or "OK" in reason

    def test_verifier_empty_output(self, verifier):
        """Vérifie qu'un output vide est rejeté."""
        step = TaskStep(
            description="Tester output vide",
            tool_calls=[ToolCall(tool_name="search_rag")],
        )
        result = StepResult(
            step_id=step.step_id,
            status=TaskStatus.COMPLETED,
            output="",
            confidence=0.9,
        )
        is_ok, score, reason = verifier.verify(step, result)

        assert is_ok is False
        assert "vide" in reason.lower()

    def test_verifier_none_output(self, verifier):
        """Vérifie qu'un output None est rejeté."""
        step = TaskStep(
            description="Tester output None",
            tool_calls=[ToolCall(tool_name="search_rag")],
        )
        result = StepResult(
            step_id=step.step_id,
            status=TaskStatus.COMPLETED,
            output=None,
            confidence=0.9,
        )
        is_ok, score, reason = verifier.verify(step, result)

        assert is_ok is False
        assert "None" in reason

    def test_verifier_error(self, verifier):
        """Vérifie qu'une erreur présente provoque un échec."""
        step = TaskStep(
            description="Tester présence d'erreur",
            tool_calls=[ToolCall(tool_name="search_rag")],
        )
        result = StepResult(
            step_id=step.step_id,
            status=TaskStatus.FAILED,
            output=None,
            error="L'outil a échoué: timeout",
            confidence=0.0,
        )
        is_ok, score, reason = verifier.verify(step, result)

        assert is_ok is False
        assert "Erreur" in reason
        assert score == 0.0

    def test_verifier_low_confidence(self, verifier):
        """Vérifie qu'une confiance trop basse par rapport au seuil est rejetée."""
        step = TaskStep(
            description="Tester confiance basse",
            tool_calls=[ToolCall(tool_name="search_rag")],
        )
        result = StepResult(
            step_id=step.step_id,
            status=TaskStatus.COMPLETED,
            output="Résultat quelconque",
            confidence=0.3,  # < seuil search (0.5)
        )
        is_ok, score, reason = verifier.verify(step, result)

        assert is_ok is False
        assert "Confiance" in reason or "confiance" in reason.lower()
        assert score == 0.3

    def test_verifier_expected_output(self, verifier):
        """Vérifie la comparaison avec l'output attendu."""
        step = TaskStep(
            description="Tester expected_output",
            tool_calls=[ToolCall(tool_name="search_rag")],
            expected_output="Données collectées",
        )
        # Cas OK : l'output contient l'attendu
        result_ok = StepResult(
            step_id=step.step_id,
            status=TaskStatus.COMPLETED,
            output="Données collectées avec succès",
            confidence=0.8,
        )
        is_ok, score, reason = verifier.verify(step, result_ok)

        assert is_ok is True

        # Cas KO : l'output ne correspond pas
        result_ko = StepResult(
            step_id=step.step_id,
            status=TaskStatus.COMPLETED,
            output="Rien trouvé",
            confidence=0.8,
        )
        is_ok2, score2, reason2 = verifier.verify(step, result_ko)

        assert is_ok2 is False
        assert "correspond pas" in reason2

    def test_verifier_search_rule(self, verifier):
        """Vérifie que la règle spécifique 'search' est bien utilisée."""
        step = TaskStep(
            description="Tester règle search",
            tool_calls=[ToolCall(tool_name="search_rag")],
        )
        rule = verifier._get_rule(step)

        assert rule["min_confidence"] == 0.5
        assert rule["require_non_empty"] is True

    def test_verifier_default_rule(self, verifier):
        """Vérifie que la règle par défaut s'applique pour un outil inconnu."""
        step = TaskStep(
            description="Tester règle par défaut",
            tool_calls=[ToolCall(tool_name="unknown_tool")],
        )
        rule = verifier._get_rule(step)

        assert rule["min_confidence"] == 0.4  # default

    def test_verifier_in_progress_status(self, verifier):
        """Vérifie qu'un statut non COMPLETED est rejeté."""
        step = TaskStep(
            description="Tester in_progress",
            tool_calls=[ToolCall(tool_name="analyze")],
        )
        result = StepResult(
            step_id=step.step_id,
            status=TaskStatus.IN_PROGRESS,
            output="En cours",
            confidence=0.8,
        )
        is_ok, score, reason = verifier.verify(step, result)

        assert is_ok is False
        assert "Statut" in reason or "statut" in reason.lower()

    def test_verifier_via_init(self):
        """Vérifie que TaskVerifier est accessible via __init__.py."""
        from src.agent import TaskVerifier

        instance = TaskVerifier()
        assert instance is not None
        # Vérifie que les règles existent
        assert "default" in instance.VERIFICATION_RULES


# ══════════════════════════════════════════════════════════════════════
# ErrorRecovery
# ══════════════════════════════════════════════════════════════════════


class TestErrorRecovery:
    """Tests unitaires pour ErrorRecovery."""

    def test_recovery_import(self):
        """Vérifie que ErrorRecovery s'importe correctement."""
        from src.agent.recovery import ErrorRecovery

        assert ErrorRecovery is not None

    def test_recovery_tool_failure_first_retry(self, recovery):
        """Vérifie que le premier retry pour TOOL_FAILURE est RETRY."""
        decision = recovery.decide(ErrorType.TOOL_FAILURE, attempt=0)

        assert isinstance(decision, RecoveryDecision)
        assert decision.action == RecoveryAction.RETRY
        assert "tentative" in decision.message.lower()

    def test_recovery_tool_failure_second(self, recovery):
        """Vérifie que le second retry pour TOOL_FAILURE est ALTERNATIVE_TOOL."""
        decision = recovery.decide(ErrorType.TOOL_FAILURE, attempt=1)

        assert decision.action == RecoveryAction.ALTERNATIVE_TOOL
        assert "alternatif" in decision.message.lower()

    def test_recovery_tool_failure_exhausted(self, recovery):
        """Vérifie qu'après épuisement des stratégies, on ESCALATE."""
        # 4 stratégies pour TOOL_FAILURE → attempt=5 dépasse
        decision = recovery.decide(ErrorType.TOOL_FAILURE, attempt=5)

        assert decision.action == RecoveryAction.ESCALATE
        assert "épuisées" in decision.message.lower()
        assert "escape" in decision.message.lower() or "escalade" in decision.message.lower()

    def test_recovery_timeout_first(self, recovery):
        """Vérifie que le premier retry pour TIMEOUT est RETRY."""
        decision = recovery.decide(ErrorType.TIMEOUT, attempt=0)

        assert decision.action == RecoveryAction.RETRY

    def test_recovery_timeout_second(self, recovery):
        """Vérifie que le second retry pour TIMEOUT est PARTIAL_RESULT."""
        decision = recovery.decide(ErrorType.TIMEOUT, attempt=1)

        assert decision.action == RecoveryAction.PARTIAL_RESULT
        assert "partiel" in decision.message.lower()

    def test_recovery_hallucination(self, recovery):
        """Vérifie la stratégie pour HALLUCINATION_DETECTED."""
        decision = recovery.decide(ErrorType.HALLUCINATION_DETECTED, attempt=0)

        assert decision.action == RecoveryAction.REGENERATE_STRICT
        assert "régénération" in decision.message.lower() or "regenerat" in decision.message.lower()

    def test_recovery_hallucination_second(self, recovery):
        """Vérifie le fallback RAG pour hallucination."""
        decision = recovery.decide(ErrorType.HALLUCINATION_DETECTED, attempt=1)

        assert decision.action == RecoveryAction.FALLBACK_TO_RAG

    def test_recovery_network_error(self, recovery):
        """Vérifie la stratégie pour NETWORK_ERROR."""
        decision = recovery.decide(ErrorType.NETWORK_ERROR, attempt=0)

        assert decision.action == RecoveryAction.RETRY_BACKOFF
        assert "backoff" in decision.message.lower()
        assert "backoff_seconds" in decision.params

    def test_recovery_network_second(self, recovery):
        """Vérifie le fallback offline pour NETWORK_ERROR."""
        decision = recovery.decide(ErrorType.NETWORK_ERROR, attempt=1)

        assert decision.action == RecoveryAction.OFFLINE_FALLBACK

    def test_recovery_unknown(self, recovery):
        """Vérifie que UNKNOWN retourne RETRY puis ASK_USER."""
        decision_0 = recovery.decide(ErrorType.UNKNOWN, attempt=0)
        assert decision_0.action == RecoveryAction.RETRY

        decision_1 = recovery.decide(ErrorType.UNKNOWN, attempt=1)
        assert decision_1.action == RecoveryAction.ASK_USER

    def test_recovery_ram_exceeded(self, recovery):
        """Vérifie la stratégie pour RAM_EXCEEDED."""
        decision_0 = recovery.decide(ErrorType.RAM_EXCEEDED, attempt=0)
        assert decision_0.action == RecoveryAction.REDUCE_BATCH

        decision_1 = recovery.decide(ErrorType.RAM_EXCEEDED, attempt=1)
        assert decision_1.action == RecoveryAction.UNLOAD_MODELS

    def test_recovery_low_confidence(self, recovery):
        """Vérifie la stratégie pour LOW_CONFIDENCE."""
        decision = recovery.decide(ErrorType.LOW_CONFIDENCE, attempt=0)
        assert decision.action == RecoveryAction.SEARCH_MORE

    def test_recovery_context_passthrough(self, recovery):
        """Vérifie que le contexte est bien passé dans les params."""
        context = {"tool": "search_rag", "query": "test"}
        decision = recovery.decide(ErrorType.TOOL_FAILURE, attempt=0, context=context)

        assert decision.params.get("context") == context

    def test_recovery_via_init(self):
        """Vérifie que ErrorRecovery est accessible via __init__.py."""
        from src.agent import ErrorRecovery

        instance = ErrorRecovery()
        assert instance is not None

    def test_recovery_user_cancelled(self, recovery):
        """Vérifie la stratégie pour USER_CANCELLED."""
        decision = recovery.decide(ErrorType.USER_CANCELLED, attempt=0)
        assert decision.action == RecoveryAction.ASK_USER


# ══════════════════════════════════════════════════════════════════════
# ResumeManager
# ══════════════════════════════════════════════════════════════════════


class TestResumeManager:
    """Tests unitaires pour ResumeManager."""

    def test_resume_import(self):
        """Vérifie que ResumeManager s'importe correctement."""
        from src.agent.resume import ResumeManager

        assert ResumeManager is not None

    def test_resume_save_and_load(self, resume):
        """Vérifie le cycle complet sauvegarde → chargement."""
        task_id = "task_001"
        state = {
            "session_id": "session_abc",
            "current_goal": "Analyser les données",
            "current_step_index": 2,
            "status": "interrupted",
            "step_count": 5,
        }

        resume.save_state(task_id, state)
        loaded = resume.load_state(task_id)

        assert loaded is not None
        assert loaded["session_id"] == "session_abc"
        assert loaded["current_goal"] == "Analyser les données"
        assert loaded["current_step_index"] == 2

    def test_resume_update_existing(self, resume):
        """Vérifie que save_state met à jour (INSERT OR REPLACE)."""
        task_id = "task_update"
        state_1 = {"status": "interrupted", "step": 1}
        state_2 = {"status": "completed", "step": 5, "result": "OK"}

        resume.save_state(task_id, state_1)
        resume.save_state(task_id, state_2)
        loaded = resume.load_state(task_id)

        assert loaded is not None
        assert loaded["status"] == "completed"
        assert loaded["step"] == 5
        assert loaded["result"] == "OK"

    def test_resume_list_interrupted(self, resume):
        """Vérifie que list_interrupted retourne les tâches récentes."""
        resume.save_state("task_a", {"status": "interrupted", "data": "a"})
        resume.save_state("task_b", {"status": "interrupted", "data": "b"})
        resume.save_state("task_c", {"status": "completed", "data": "c"})

        tasks = resume.list_interrupted(limit=10)

        assert len(tasks) >= 3
        # Vérifie la structure
        for t in tasks:
            assert "task_id" in t
            assert "status" in t
            assert "created_at" in t
            assert "updated_at" in t

        # Les plus récentes en premier
        assert tasks[0]["updated_at"] >= tasks[1]["updated_at"]

    def test_resume_list_interrupted_limit(self, resume):
        """Vérifie que le paramètre limit est respecté."""
        for i in range(5):
            resume.save_state(f"task_{i}", {"status": "interrupted"})

        tasks = resume.list_interrupted(limit=3)
        assert len(tasks) == 3

    def test_resume_delete(self, resume):
        """Vérifie la suppression d'un état."""
        resume.save_state("task_del", {"status": "interrupted"})
        assert resume.load_state("task_del") is not None

        deleted = resume.delete_state("task_del")
        assert deleted is True
        assert resume.load_state("task_del") is None

    def test_resume_delete_not_found(self, resume):
        """Vérifie que delete_state retourne False pour un ID inexistant."""
        deleted = resume.delete_state("nonexistent")
        assert deleted is False

    def test_resume_not_found(self, resume):
        """Vérifie que load_state retourne None pour un ID inexistant."""
        loaded = resume.load_state("unknown_task_id")
        assert loaded is None

    def test_resume_via_init(self):
        """Vérifie que ResumeManager est accessible via __init__.py."""
        from src.agent import ResumeManager

        instance = ResumeManager(db_path=":memory:")
        assert instance is not None
        # Nettoyage : pas de fichier à supprimer pour :memory:
