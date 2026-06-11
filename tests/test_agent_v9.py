"""
Tests NURU V9 — Agent : TaskPlanner et TaskExecutor.

Vérifie :
  - Décomposition de plans par mots-clés
  - Contraintes AGENT_LIMITS (max_steps)
  - Formatage lisible des plans
  - Exécution d'outils simulés et personnalisés
  - Gestion du timeout
  - Structure des StepResult
"""

from __future__ import annotations

import asyncio
import time

import pytest

from src.agent.types import (
    AGENT_LIMITS,
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
def planner():
    from src.agent.planner import TaskPlanner

    return TaskPlanner()


@pytest.fixture
def executor():
    from src.agent.executor import TaskExecutor

    return TaskExecutor()


# ══════════════════════════════════════════════════════════════════════
# TaskPlanner — Création de plan
# ══════════════════════════════════════════════════════════════════════


class TestTaskPlanner:
    """Tests unitaires pour TaskPlanner."""

    def test_planner_create_plan(self, planner):
        """Vérifie que plan() retourne un TaskPlan valide."""
        plan = planner.plan("Analyser les résultats financiers")

        assert isinstance(plan, TaskPlan)
        assert plan.goal == "Analyser les résultats financiers"
        assert len(plan.steps) > 0
        assert plan.created_at > 0

        # Chaque étape est un TaskStep
        for step in plan.steps:
            assert isinstance(step, TaskStep)
            assert step.step_id
            assert step.description

    def test_planner_max_steps(self, planner):
        """Vérifie que le plan ne dépasse pas max_steps=5."""
        plan = planner.plan("Un objectif très long" * 100)
        max_steps = AGENT_LIMITS["max_steps"]
        assert len(plan.steps) <= max_steps

    def test_planner_analyse_keyword(self, planner):
        """Vérifie que 'analyser' déclenche le workflow analyse."""
        plan = planner.plan("Analyser les données du marché")
        descriptions = [s.description for s in plan.steps]

        assert any("Rechercher" in d for d in descriptions)
        assert any("Analyser" in d or "analyse" in d.lower() for d in descriptions)
        assert any("rapport" in d.lower() or "Rapport" in d for d in descriptions)

        # Vérifie les dépendances en chaîne
        assert plan.steps[0].depends_on == []
        assert "step_1" in plan.steps[1].depends_on
        assert "step_2" in plan.steps[2].depends_on

    def test_planner_report_keyword(self, planner):
        """Vérifie que 'rapport' déclenche le workflow report."""
        plan = planner.plan("Créer un rapport mensuel")
        descriptions = [s.description for s in plan.steps]

        assert any("Rechercher" in d for d in descriptions)
        assert any("Rédiger" in d or "rapport" in d.lower() for d in descriptions)
        assert any("Vérifier" in d for d in descriptions)

        # Vérifie les dépendances
        assert "step_1" in plan.steps[1].depends_on
        assert "step_2" in plan.steps[2].depends_on

    def test_planner_ppt_keyword(self, planner):
        """Vérifie que 'powerpoint' déclenche le workflow présentation."""
        plan = planner.plan("Préparer une présentation PowerPoint")
        descriptions = [s.description for s in plan.steps]

        assert any("Collecter" in d or "contenu" in d.lower() for d in descriptions)
        assert any("slides" in d.lower() or "Créer" in d for d in descriptions)

        # Seulement 2 étapes pour le workflow ppt
        assert len(plan.steps) == 2

    def test_planner_ppt_keyword_synonyms(self, planner):
        """Vérifie les synonymes : ppt, présentation, slides."""
        for kw in ["ppt", "présentation", "slides", "slide", "powerpoint"]:
            plan = planner.plan(f"Faire un {kw}")
            assert len(plan.steps) == 2, f"Échec pour mot-clé '{kw}'"

    def test_planner_report_keyword_synonyms(self, planner):
        """Vérifie les synonymes : report, document."""
        for kw in ["report", "document"]:
            plan = planner.plan(f"Créer un {kw}")
            assert len(plan.steps) == 3, f"Échec pour mot-clé '{kw}'"

    def test_planner_analyse_keyword_synonyms(self, planner):
        """Vérifie les synonymes : analyse, analyze."""
        for kw in ["analyse", "analyze"]:
            plan = planner.plan(f"{kw} les résultats")
            assert len(plan.steps) == 3, f"Échec pour mot-clé '{kw}'"

    def test_planner_default_workflow(self, planner):
        """Vérifie le workflow par défaut pour un goal sans mot-clé."""
        plan = planner.plan("Salut, comment ça va ?")
        descriptions = [s.description for s in plan.steps]

        assert any("Comprendre" in d for d in descriptions)
        assert any("Générer" in d for d in descriptions)
        assert any("Vérifier" in d for d in descriptions)
        assert len(plan.steps) == 3

    def test_planner_format_plan(self, planner):
        """Vérifie le formatage lisible du plan."""
        plan = planner.plan("Analyser les ventes")
        formatted = planner.format_plan(plan)

        assert "📋 Plan pour :" in formatted
        assert "Analyser les ventes" in formatted
        assert "1." in formatted
        # Vérifie que chaque étape a sa ligne
        lines = formatted.strip().split("\n")
        # 1 titre + N étapes
        assert len(lines) == 1 + len(plan.steps)

        # Vérifie les outils dans le formatage
        for step in plan.steps:
            for tc in step.tool_calls:
                assert tc.tool_name in formatted

    def test_planner_via_init(self):
        """Vérifie que TaskPlanner est accessible via __init__.py."""
        from src.agent import TaskPlanner

        instance = TaskPlanner()
        plan = instance.plan("test")
        assert isinstance(plan, TaskPlan)

    def test_planner_all_steps_have_tools(self, planner):
        """Vérifie que chaque étape a au moins un tool_call."""
        for kw in ["analyser", "rapport", "ppt", "bonjour"]:
            plan = planner.plan(f"Test {kw}")
            for step in plan.steps:
                assert len(step.tool_calls) >= 1, (
                    f"L'étape '{step.description}' n'a pas de tool_call"
                )


# ══════════════════════════════════════════════════════════════════════
# TaskExecutor — Exécution d'étapes
# ══════════════════════════════════════════════════════════════════════


class TestTaskExecutor:
    """Tests unitaires pour TaskExecutor."""

    @pytest.mark.asyncio
    async def test_executor_import(self):
        """Vérifie que TaskExecutor s'importe correctement."""
        from src.agent.executor import TaskExecutor

        assert TaskExecutor is not None

    @pytest.mark.asyncio
    async def test_executor_mock_tool(self, executor):
        """Vérifie qu'un outil simulé retourne une réponse factice."""
        step = TaskStep(
            description="Tester outil simulé",
            tool_calls=[ToolCall(tool_name="search_rag")],
        )
        result = await executor.execute(step)

        assert isinstance(result, StepResult)
        assert result.status == TaskStatus.COMPLETED
        assert "Résultats de recherche simulés" in (result.output or "")
        assert result.duration_s >= 0
        assert len(result.tool_results) == 1
        assert result.tool_results[0]["tool"] == "search_rag"
        assert result.tool_results[0]["status"] == "success"

    @pytest.mark.asyncio
    async def test_executor_custom_tool(self):
        """Vérifie qu'un outil injecté est appelé avec ses paramètres."""
        call_log = []

        async def my_custom_tool(query: str = "", **kwargs):
            call_log.append(query)
            return f"Résultat personnalisé pour : {query}"

        exec_custom = __import__(
            "src.agent.executor", fromlist=["TaskExecutor"]
        ).TaskExecutor(tools={"search_rag": my_custom_tool})

        step = TaskStep(
            description="Tester outil personnalisé",
            tool_calls=[
                ToolCall(
                    tool_name="search_rag",
                    parameters={"query": "test custom"},
                )
            ],
        )
        result = await exec_custom.execute(step)

        assert result.status == TaskStatus.COMPLETED
        assert "Résultat personnalisé pour : test custom" in (result.output or "")
        assert call_log == ["test custom"]

    @pytest.mark.asyncio
    async def test_executor_multiple_tools(self, executor):
        """Vérifie que plusieurs outils s'exécutent en séquence."""
        step = TaskStep(
            description="Tester outils multiples",
            tool_calls=[
                ToolCall(tool_name="search_rag"),
                ToolCall(tool_name="analyze"),
                ToolCall(tool_name="verify"),
            ],
        )
        result = await executor.execute(step)

        assert result.status == TaskStatus.COMPLETED
        assert len(result.tool_results) == 3
        assert result.tool_results[0]["tool"] == "search_rag"
        assert result.tool_results[1]["tool"] == "analyze"
        assert result.tool_results[2]["tool"] == "verify"

        # Vérifie que chaque outil a son output
        for tr in result.tool_results:
            assert tr["status"] == "success"

    @pytest.mark.asyncio
    async def test_executor_timeout(self):
        """Vérifie la gestion du timeout sur un outil lent."""

        async def slow_tool(**kwargs):
            await asyncio.sleep(10)  # Trop lent
            return "jamais"

        exec_custom = __import__(
            "src.agent.executor", fromlist=["TaskExecutor"]
        ).TaskExecutor(tools={"slow_tool": slow_tool})

        step = TaskStep(
            description="Tester timeout",
            tool_calls=[
                ToolCall(
                    tool_name="slow_tool",
                    timeout_s=1,  # Timeout rapide
                )
            ],
        )
        result = await exec_custom.execute(step)

        assert result.status == TaskStatus.FAILED
        assert "Timeout" in (result.error or "")

    @pytest.mark.asyncio
    async def test_executor_step_result(self, executor):
        """Vérifie la structure complète de StepResult."""
        step = TaskStep(
            description="Tester structure StepResult",
            tool_calls=[ToolCall(tool_name="summarize")],
            step_id="test_step_001",
        )
        result = await executor.execute(step)

        assert isinstance(result, StepResult)
        assert result.step_id == "test_step_001"
        assert result.status == TaskStatus.COMPLETED
        assert result.output is not None
        assert result.error is None
        assert result.duration_s >= 0
        assert isinstance(result.duration_s, float)
        assert len(result.tool_results) == 1
        assert result.is_success is True

    @pytest.mark.asyncio
    async def test_executor_unknown_tool(self, executor):
        """Vérifie qu'un outil inconnu retourne une erreur."""
        step = TaskStep(
            description="Tester outil inconnu",
            tool_calls=[ToolCall(tool_name="nonexistent_tool")],
        )
        result = await executor.execute(step)

        assert result.status == TaskStatus.FAILED
        assert "inconnu" in (result.error or "").lower() or "nonexistent" in (result.error or "")

    @pytest.mark.asyncio
    async def test_executor_custom_tool_exception(self):
        """Vérifie qu'une exception dans un outil est bien capturée."""

        async def broken_tool(**kwargs):
            raise ValueError("Erreur interne volontaire")

        exec_custom = __import__(
            "src.agent.executor", fromlist=["TaskExecutor"]
        ).TaskExecutor(tools={"broken": broken_tool})

        step = TaskStep(
            description="Tester exception outil",
            tool_calls=[ToolCall(tool_name="broken")],
        )
        result = await exec_custom.execute(step)

        assert result.status == TaskStatus.FAILED
        assert "Exception" in (result.error or "")
        assert "Erreur interne volontaire" in (result.error or "")

    @pytest.mark.asyncio
    async def test_executor_get_mock_response(self, executor):
        """Vérifie _get_mock_response pour les outils connus et inconnus."""
        assert executor._get_mock_response("search_rag") == "Résultats de recherche simulés"
        assert executor._get_mock_response("verify") == "Vérification OK simulée"

        # Outil inconnu
        fallback = executor._get_mock_response("unknown_tool")
        assert "Réponse simulée pour" in fallback
        assert "unknown_tool" in fallback

    @pytest.mark.asyncio
    async def test_executor_via_init(self):
        """Vérifie que TaskExecutor est accessible via __init__.py."""
        from src.agent import TaskExecutor

        instance = TaskExecutor()
        step = TaskStep(
            description="test init",
            tool_calls=[ToolCall(tool_name="read_file")],
        )
        result = await instance.execute(step)
        assert result.status == TaskStatus.COMPLETED
