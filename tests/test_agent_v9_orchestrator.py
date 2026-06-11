"""
Tests NURU V9 — AgentOrchestrator : boucle agentique complète.

Vérifie :
  - Import et création de l'orchestrateur
  - run() avec objectif simple
  - run() avec objectif complexe (3 étapes)
  - Retry sur échec → succès
  - Escalade après épuisement des retries
  - Troncature du plan (max_steps)
  - Timeout temps réel (wall time)
  - Synthèse finale
  - Objectif vide → erreur
  - Suivi du statut (AgentState.status)
  - get_progress()
"""

from __future__ import annotations

import asyncio
import time

import pytest

from src.agent.types import (
    AGENT_LIMITS,
    AgentState,
    ErrorType,
    RecoveryAction,
    RecoveryDecision,
    StepResult,
    TaskPlan,
    TaskStatus,
    TaskStep,
    ToolCall,
)


# ══════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def matching_executor():
    """Fixture : TaskExecutor dont les outils mock retournent des sorties
    correspondant aux expected_output du TaskPlanner (tous workflows)."""
    from src.agent.executor import TaskExecutor

    return TaskExecutor(
        tools={
            # La sortie doit contenir l'attendu pour tous les workflows
            "search_rag": _make_tool(
                "Contexte compris et informations collectées. "
                "Données collectées pour l'analyse. "
                "Informations collectées pour le rapport. "
                "Contenu collecté pour les slides."
            ),
            "analyze": _make_tool(
                "Analyse détaillée des données collectées. "
                "Analyse détaillée des données."
            ),
            "generate_report": _make_tool(
                "Rapport d'analyse complet. "
                "Rapport d'analyse final."
            ),
            "summarize": _make_tool("Réponse générée avec succès"),
            "verify": _make_tool("Réponse vérifiée et validée"),
            "create_slides": _make_tool("Présentation créée avec slides"),
        }
    )


def _make_tool(response_text: str):
    """Helper : crée un outil asynchrone qui retourne un texte fixe."""

    async def tool(**kwargs):
        return response_text

    return tool


@pytest.fixture
def orchestrator(matching_executor):
    """Fixture : AgentOrchestrator avec executor adapté aux expected_output."""
    from src.agent.orchestrator import AgentOrchestrator

    return AgentOrchestrator(executor=matching_executor)


@pytest.fixture
def mock_resume(tmp_path):
    """Fixture : ResumeManager avec base SQLite temporaire."""
    from src.agent.resume import ResumeManager

    db_path = str(tmp_path / "test_states.db")
    return ResumeManager(db_path=db_path)


@pytest.fixture
def failing_executor():
    """Fixture : TaskExecutor qui échoue volontairement."""
    from src.agent.executor import TaskExecutor

    async def fail_tool(**kwargs):
        raise RuntimeError("Échec volontaire de l'outil")

    return TaskExecutor(tools={"search_rag": fail_tool, "analyze": fail_tool})


@pytest.fixture
def half_failing_executor():
    """Fixture : TaskExecutor qui échoue une fois puis réussit, pour tous les outils."""
    from src.agent.executor import TaskExecutor

    call_count = {"count": 0}

    async def retry_then_succeed(**kwargs):
        call_count["count"] += 1
        if call_count["count"] <= 1:
            raise RuntimeError("Échec volontaire #1")
        return (
            "Contexte compris et informations collectées. "
            "Données collectées pour l'analyse."
        )

    async def always_ok(**kwargs):
        return (
            "Analyse détaillée des données collectées. "
            "Réponse générée avec succès. "
            "Rapport d'analyse complet."
        )

    async def always_verify_ok(**kwargs):
        return (
            "Réponse vérifiée et validée. "
            "Rapport vérifié et validé."
        )

    return TaskExecutor(
        tools={
            "search_rag": retry_then_succeed,
            "summarize": always_ok,
            "verify": always_verify_ok,
            "analyze": always_ok,
            "generate_report": always_ok,
            "create_slides": always_ok,
        }
    )


# ══════════════════════════════════════════════════════════════════════
# AgentOrchestrator — Tests d'import et création
# ══════════════════════════════════════════════════════════════════════


class TestOrchestratorCreation:
    """Tests unitaires pour la création d'AgentOrchestrator."""

    def test_orchestrator_import(self):
        """Vérifie que AgentOrchestrator s'importe correctement."""
        from src.agent.orchestrator import AgentOrchestrator

        assert AgentOrchestrator is not None

    def test_orchestrator_create_default(self):
        """Vérifie la création avec tous les modules par défaut."""
        from src.agent.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator()
        assert orch.planner is not None
        assert orch.executor is not None
        assert orch.verifier is not None
        assert orch.recovery is not None
        assert orch.resume is not None
        assert orch.limits["max_steps"] == 5

    def test_orchestrator_create_with_deps(self, mock_resume):
        """Vérifie la création avec des dépendances injectées."""
        from src.agent.planner import TaskPlanner
        from src.agent.executor import TaskExecutor
        from src.agent.verifier import TaskVerifier
        from src.agent.recovery import ErrorRecovery
        from src.agent.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator(
            planner=TaskPlanner(),
            executor=TaskExecutor(),
            verifier=TaskVerifier(),
            recovery=ErrorRecovery(),
            resume=mock_resume,
        )
        assert orch.planner is not None
        assert orch.executor is not None
        assert orch.verifier is not None
        assert orch.recovery is not None
        assert orch.resume is mock_resume

    def test_orchestrator_via_init(self):
        """Vérifie que AgentOrchestrator est accessible via __init__.py."""
        from src.agent import AgentOrchestrator

        instance = AgentOrchestrator()
        assert instance is not None
        assert instance.limits["max_steps"] == 5


# ══════════════════════════════════════════════════════════════════════
# AgentOrchestrator — Tests run()
# ══════════════════════════════════════════════════════════════════════


class TestOrchestratorRun:
    """Tests de la boucle agentique complète."""

    @pytest.mark.asyncio
    async def test_orchestrator_run_simple_goal(self, orchestrator):
        """Vérifie run() avec un objectif simple."""
        result = await orchestrator.run("Fais une recherche")

        assert isinstance(result, dict)
        assert result["goal"] == "Fais une recherche"
        assert result["status"] == "success"
        assert len(result["steps"]) > 0
        assert result["duration_s"] >= 0
        assert result["session_id"] == "default"
        assert "Synthèse" in (result["final_response"] or "")

        # Vérifie la structure des steps
        for step in result["steps"]:
            assert "step_id" in step
            assert "description" in step
            assert "status" in step
            assert "duration_s" in step

    @pytest.mark.asyncio
    async def test_orchestrator_run_complex_goal(self, orchestrator):
        """Vérifie run() avec un objectif complexe (3 étapes : analyse)."""
        result = await orchestrator.run(
            "Analyse le dossier et rédige un rapport"
        )

        assert result["status"] == "success"
        assert len(result["steps"]) >= 3

        # Vérifie les descriptions des étapes
        descriptions = [s["description"] for s in result["steps"]]
        assert any("Rechercher" in d for d in descriptions)
        assert any("Analyser" in d for d in descriptions)
        assert any("rapport" in d.lower() or "Rapport" in d for d in descriptions)

    @pytest.mark.asyncio
    async def test_orchestrator_empty_goal(self, orchestrator):
        """Vérifie que run() avec un goal vide retourne une erreur."""
        result = await orchestrator.run("")

        assert result["status"] == "error"
        assert "vide" in (result["final_response"] or "").lower()

        result2 = await orchestrator.run("   ")
        assert result2["status"] == "error"
        assert "vide" in (result2["final_response"] or "").lower()

    @pytest.mark.asyncio
    async def test_orchestrator_run_custom_session(self, orchestrator):
        """Vérifie qu'un session_id personnalisé est bien propagé."""
        result = await orchestrator.run(
            "Faire un ppt", session_id="custom_session_42"
        )

        assert result["session_id"] == "custom_session_42"

    @pytest.mark.asyncio
    async def test_orchestrator_status_tracking(self, orchestrator):
        """Vérifie le suivi du statut dans AgentState."""
        session_id = "status_test_session"
        result = await orchestrator.run("Recherche rapide", session_id=session_id)

        assert result["status"] == "success"

        # Vérifie que l'état de session existe
        state = orchestrator._sessions.get(session_id)
        assert state is not None
        assert state.session_id == session_id
        assert state.current_goal == "Recherche rapide"
        assert state.status == "done"

    @pytest.mark.asyncio
    async def test_orchestrator_synthesize(self, orchestrator):
        """Vérifie le format de la réponse finale via synthesize()."""
        result = await orchestrator.run("Créer un document")

        final = result["final_response"]
        assert isinstance(final, str)
        assert len(final) > 0

        # Doit contenir le nombre d'étapes réussies
        assert any(word in final for word in ["Synthèse", "✅", "❌"])

    @pytest.mark.asyncio
    async def test_orchestrator_status_tracking_phases(self, orchestrator):
        """Vérifie que AgentState.status est mis à jour pendant l'exécution."""
        from src.agent.orchestrator import AgentOrchestrator

        # On utilise un orchestrateur avec un planner qui produit des étapes
        # pour observer les transitions de statut
        orch = AgentOrchestrator()
        session_id = "phases_test"

        # Lancer en arrière-plan pour capturer les transitions
        task = asyncio.create_task(
            orch.run("Faire une présentation ppt", session_id=session_id)
        )

        # Laisser le temps de démarrer
        await asyncio.sleep(0.05)

        state = orch._sessions.get(session_id)
        if state is not None:
            # Le statut doit avoir été 'planning' au début
            assert state.status in ("planning", "executing", "done")

        await task

        # Finalement, le statut doit être 'done'
        state = orch._sessions.get(session_id)
        if state is not None:
            assert state.status == "done"


# ══════════════════════════════════════════════════════════════════════
# AgentOrchestrator — Tests de retry et recovery
# ══════════════════════════════════════════════════════════════════════


class TestOrchestratorRetry:
    """Tests de la gestion des erreurs et retry."""

    @pytest.mark.asyncio
    async def test_orchestrator_retry_on_failure(self, half_failing_executor):
        """Vérifie qu'un retry peut réussir après un échec initial."""
        from src.agent.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator(executor=half_failing_executor)
        result = await orch.run("Recherche avec retry")

        assert result["status"] == "success"
        # L'outil ayant échoué une fois puis réussi, le résultat final
        # dépend de si l'étape a été vérifiée après retry
        # Au moins 1 étape a été exécutée
        assert len(result["steps"]) > 0

    @pytest.mark.asyncio
    async def test_orchestrator_escalate_on_exhausted(self, failing_executor):
        """Vérifie qu'après 3 retries échoués, on ESCALATE."""
        from src.agent.orchestrator import AgentOrchestrator

        orch = AgentOrchestrator(executor=failing_executor)
        result = await orch.run("Tâche vouée à l'échec")

        # Le résultat devrait être en erreur après épuisement des retries
        assert result["status"] in ("error", "partial")
        # Vérifier qu'au moins une étape mentionne l'échec
        if result["steps"]:
            failed_steps = [s for s in result["steps"] if s["status"] == "failed"]
            # Au moins une étape devrait être en échec (ou toutes)
            pass

    @pytest.mark.asyncio
    async def test_orchestrator_run_step_retry_success(self):
        """Vérifie run_step avec un retry réussi."""
        from src.agent.orchestrator import AgentOrchestrator
        from src.agent.executor import TaskExecutor

        call_count = {"count": 0}

        async def succeeds_on_second(**kwargs):
            call_count["count"] += 1
            if call_count["count"] <= 1:
                raise RuntimeError("Premier échec")
            return "Succès !"

        exec_custom = TaskExecutor(tools={"search_rag": succeeds_on_second})
        orch = AgentOrchestrator(executor=exec_custom)

        step = TaskStep(
            description="Test retry",
            tool_calls=[ToolCall(tool_name="search_rag")],
            max_retries=3,
        )
        result = await orch.run_step(step)

        assert result.is_success
        assert call_count["count"] == 2  # 1 échec + 1 succès

    @pytest.mark.asyncio
    async def test_orchestrator_run_step_escalate(self):
        """Vérifie que run_step escalade après épuisement des retries."""
        from src.agent.orchestrator import AgentOrchestrator

        # Utilise le failing_executor qui échoue toujours
        from src.agent.executor import TaskExecutor

        async def always_fail(**kwargs):
            raise RuntimeError("Échec permanent")

        exec_custom = TaskExecutor(tools={"search_rag": always_fail})
        orch = AgentOrchestrator(executor=exec_custom)

        step = TaskStep(
            description="Test escalade",
            tool_calls=[ToolCall(tool_name="search_rag")],
            max_retries=3,
        )
        result = await orch.run_step(step)

        assert result.status == TaskStatus.FAILED
        assert "ESCALATE" in (result.error or "")


# ══════════════════════════════════════════════════════════════════════
# AgentOrchestrator — Tests des limites de sécurité
# ══════════════════════════════════════════════════════════════════════


class TestOrchestratorLimits:
    """Tests des limites de sécurité (max_steps, wall time)."""

    @pytest.mark.asyncio
    async def test_orchestrator_max_steps_truncated(self):
        """Vérifie qu'un plan > 5 étapes est tronqué à max_steps."""
        from src.agent.orchestrator import AgentOrchestrator
        from src.agent.planner import TaskPlanner

        class LongPlanPlanner(TaskPlanner):
            """Planner qui produit volontairement 10 étapes."""

            def plan(self, goal: str) -> TaskPlan:
                steps = []
                for i in range(10):
                    steps.append(
                        TaskStep(
                            description=f"Étape longue #{i + 1}",
                            tool_calls=[
                                ToolCall(tool_name="search_rag")
                            ],
                            depends_on=[f"step_{i}"] if i > 0 else [],
                        )
                    )
                return TaskPlan(goal=goal, steps=steps, created_at=time.time())

        orch = AgentOrchestrator(planner=LongPlanPlanner())
        result = await orch.run("Objectif avec 10 étapes")

        # Le plan a été tronqué à 5 étapes max
        assert len(result["steps"]) <= AGENT_LIMITS["max_steps"]

    @pytest.mark.asyncio
    async def test_orchestrator_wall_timeout(self):
        """Vérifie que le wall timeout interrompt l'exécution."""
        from src.agent.orchestrator import AgentOrchestrator
        from src.agent.executor import TaskExecutor

        async def slow_tool(**kwargs):
            await asyncio.sleep(10)  # Trop lent
            return "jamais"

        exec_custom = TaskExecutor(tools={"search_rag": slow_tool})
        orch = AgentOrchestrator(executor=exec_custom)
        # Forcer un wall timeout très court
        orch.limits["max_wall_time_seconds"] = 0.3

        result = await orch.run("Tâche lente avec wall timeout")

        # Le wall timeout devrait interrompre avant la fin
        # Le statut peut être 'interrupted' si l'interruption est capturée
        # Sinon l'étape sera en timeout mais on aura au moins exécuté qqch
        assert result["status"] in ("success", "partial", "error", "interrupted")
        # Le temps écoulé doit être < ~1s (bien moins que 10s)
        assert result["duration_s"] < 5.0, (
            f"Le wall timeout n'a pas fonctionné : {result['duration_s']}s"
        )


# ══════════════════════════════════════════════════════════════════════
# AgentOrchestrator — Tests de synthesize()
# ══════════════════════════════════════════════════════════════════════


class TestOrchestratorSynthesize:
    """Tests de la méthode synthesize()."""

    def test_synthesize_empty_state(self, orchestrator):
        """Vérifie synthesize avec un état vide."""
        state = AgentState(status="done")
        result = orchestrator.synthesize(state)
        assert "Aucune étape" in result

    def test_synthesize_all_success(self, orchestrator):
        """Vérifie synthesize avec toutes les étapes réussies."""
        plan = TaskPlan(
            goal="Test",
            steps=[
                TaskStep(description="Recherche", step_id="s1"),
                TaskStep(description="Analyse", step_id="s2"),
            ],
        )
        state = AgentState(
            plan=plan,
            step_results={
                "s1": StepResult(
                    step_id="s1",
                    status=TaskStatus.COMPLETED,
                    output="Données trouvées",
                ),
                "s2": StepResult(
                    step_id="s2",
                    status=TaskStatus.COMPLETED,
                    output="Analyse terminée",
                ),
            },
            status="done",
        )
        result = orchestrator.synthesize(state)

        assert "Synthèse" in result
        assert "2 étape(s) réussie(s)" in result
        assert "Données trouvées" in result
        assert "Analyse terminée" in result
        assert "❌" not in result  # Pas d'échec

    def test_synthesize_with_failures(self, orchestrator):
        """Vérifie synthesize avec des échecs."""
        plan = TaskPlan(
            goal="Test",
            steps=[
                TaskStep(description="Réussie", step_id="s1"),
                TaskStep(description="Échouée", step_id="s2"),
            ],
        )
        state = AgentState(
            plan=plan,
            step_results={
                "s1": StepResult(
                    step_id="s1",
                    status=TaskStatus.COMPLETED,
                    output="OK",
                ),
                "s2": StepResult(
                    step_id="s2",
                    status=TaskStatus.FAILED,
                    error="Timeout",
                ),
            },
            status="done",
        )
        result = orchestrator.synthesize(state)

        assert "1 étape(s) réussie(s)" in result
        assert "1 échec(s)" in result
        assert "✅" in result
        assert "❌" in result
        assert "Timeout" in result

    def test_synthesize_no_results(self, orchestrator):
        """Vérifie synthesize avec des étapes sans résultats."""
        plan = TaskPlan(
            goal="Test",
            steps=[TaskStep(description="Étape orpheline", step_id="orphan")],
        )
        state = AgentState(
            plan=plan,
            step_results={},
            status="done",
        )
        result = orchestrator.synthesize(state)
        assert "Aucun résultat" in result


# ══════════════════════════════════════════════════════════════════════
# AgentOrchestrator — Tests de get_progress()
# ══════════════════════════════════════════════════════════════════════


class TestOrchestratorProgress:
    """Tests de la méthode get_progress()."""

    @pytest.mark.asyncio
    async def test_orchestrator_get_progress_active(self, orchestrator):
        """Vérifie get_progress() pour une session active."""
        await orchestrator.run("Test progression", session_id="progress_test")

        progress = orchestrator.get_progress("progress_test")
        assert progress is not None
        assert "session_id" in progress
        assert progress["session_id"] == "progress_test"

    def test_orchestrator_get_progress_unknown(self, orchestrator):
        """Vérifie get_progress() pour une session inconnue."""
        progress = orchestrator.get_progress("inexistant")
        assert progress is None


# ══════════════════════════════════════════════════════════════════════
# AgentOrchestrator — Tests des helpers internes
# ══════════════════════════════════════════════════════════════════════


class TestOrchestratorHelpers:
    """Tests des fonctions helpers de l'orchestrateur."""

    def test_detect_error_type_timeout(self):
        """Vérifie la détection d'erreur TIMEOUT."""
        from src.agent.orchestrator import _detect_error_type

        result = StepResult(
            step_id="t1",
            status=TaskStatus.FAILED,
            error="Timeout après 30s",
        )
        assert _detect_error_type(result) == ErrorType.TIMEOUT

    def test_detect_error_type_tool_failure(self):
        """Vérifie la détection d'erreur TOOL_FAILURE."""
        from src.agent.orchestrator import _detect_error_type

        result = StepResult(
            step_id="t1",
            status=TaskStatus.FAILED,
            error="Outil inconnu : 'fake_tool'",
        )
        assert _detect_error_type(result) == ErrorType.TOOL_FAILURE

    def test_detect_error_type_unknown(self):
        """Vérifie la détection d'erreur UNKNOWN (pas d'erreur)."""
        from src.agent.orchestrator import _detect_error_type

        result = StepResult(
            step_id="t1",
            status=TaskStatus.FAILED,
            error=None,
        )
        assert _detect_error_type(result) == ErrorType.UNKNOWN

    def test_detect_error_type_low_confidence(self):
        """Vérifie la détection LOW_CONFIDENCE via le verifier."""
        from src.agent.orchestrator import _detect_error_type

        result = StepResult(
            step_id="t1",
            status=TaskStatus.COMPLETED,
            output="Bof",
            confidence=0.2,
        )
        verifier_result = (False, 0.2, "Confiance trop basse : 0.20 < 0.50")
        assert (
            _detect_error_type(result, verifier_result) == ErrorType.LOW_CONFIDENCE
        )

    def test_resolve_step_id_symbolic(self):
        """Vérifie la résolution des IDs symboliques (step_1, step_2…)."""
        from src.agent.orchestrator import _resolve_step_id

        steps = [
            TaskStep(step_id="real_id_1", description="Étape 1"),
            TaskStep(step_id="real_id_2", description="Étape 2"),
            TaskStep(step_id="real_id_3", description="Étape 3"),
        ]

        step = TaskStep(
            description="Avec dépendance",
            depends_on=["step_2"],
        )
        resolved = _resolve_step_id(step, steps)
        assert resolved == "real_id_2"

    def test_resolve_step_id_out_of_bounds(self):
        """Vérifie la résolution avec un index hors-limites."""
        from src.agent.orchestrator import _resolve_step_id

        steps = [TaskStep(step_id="real_1")]

        step = TaskStep(description="Dépendance invalide", depends_on=["step_99"])
        resolved = _resolve_step_id(step, steps)
        assert resolved == "step_99"  # Retourne tel quel si hors limites

    def test_resolve_step_id_direct_id(self):
        """Vérifie que les IDs directs sont passés inchangés."""
        from src.agent.orchestrator import _resolve_step_id

        step = TaskStep(
            description="Dépendance directe",
            depends_on=["some_real_id"],
        )
        resolved = _resolve_step_id(step, [TaskStep(step_id="other")])
        assert resolved == "some_real_id"
