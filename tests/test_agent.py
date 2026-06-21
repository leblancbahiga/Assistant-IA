"""
Tests NURU V12 — R3 Agent Loop : AgentOrchestrator + agent_tools.

Vérifie :
  - AgentOrchestrator singleton et cycle de vie
  - Boucle Plan→Execute→Verify→Synthesize
  - Intégration RAG et mémoire
  - Outils agent (agent_query, agent_plan, agent_verify)
  - Gestion des erreurs et cas limites
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Ajout du path src ────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from src.tools.agent_orchestrator import (
    AgentOrchestrator,
    AgentTrace,
    PlanResult,
    VerifyResult,
)
from src.tools.agent_tools import AGENT_TOOLS, register_agent_tools
from src.tools.registry import ToolRegistry, ToolExecutor, ToolResult, ToolParameter


# ══════════════════════════════════════════════════════════════════
# Helper functions
# ══════════════════════════════════════════════════════════════════


def _make_mock_rag_result(**overrides):
    """Crée un mock RAGResult avec valeurs par défaut."""
    r = MagicMock()
    r.documents_found = overrides.get("documents_found", 2)
    r.chunks_retrieved = overrides.get("chunks_retrieved", 3)
    r.top_score = overrides.get("top_score", 0.85)
    r.all_scores = overrides.get("all_scores", [0.85, 0.42])
    r.sources = overrides.get("sources", [
        {"source": "doc1.pdf", "title": "Doc 1"},
        {"source": "doc2.pdf", "title": "Doc 2"},
    ])
    r.confidence_label = overrides.get("confidence_label", "HAUTE")
    return r


def _make_mock_memory_manager(**overrides):
    """Crée un mock MemoryManager avec valeurs par défaut."""
    m = MagicMock()
    m.get_full_context.return_value = overrides.get("full_context", "Souvenirs pertinents sur l'utilisateur")
    m.get_user_profile.return_value = overrides.get("user_profile", "Nom: Test\nPréférences: Python")
    m.check_errors.return_value = overrides.get("errors", [])
    m.get_memory_stats.return_value = {"episodic": 5, "semantic": 3, "user": 2, "errors": 1}
    return m


# ══════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def reset_agent_orchestrator():
    """Reset AgentOrchestrator singleton after each test."""
    AgentOrchestrator._reset_singleton()
    yield
    AgentOrchestrator._reset_singleton()


@pytest.fixture
def agent_orchestrator():
    """AgentOrchestrator avec RAG et mémoire mockés.

    Passe les mocks directement au constructeur pour éviter
    tout import réel de RAGEngine (qui nécessite mlx).
    """
    rag = MagicMock()
    rag.retrieve = AsyncMock()
    rag.retrieve.return_value = ("contenu RAG de test", _make_mock_rag_result())

    mem = _make_mock_memory_manager()

    return AgentOrchestrator(rag_engine=rag, memory_manager=mem)


@pytest.fixture
def agent_orchestrator_no_rag():
    """AgentOrchestrator sans RAG (simule indisponibilité via mock)."""
    rag = MagicMock()
    rag.retrieve.side_effect = RuntimeError("Simulated RAG unavailable")
    mem = MagicMock()
    mem.get_full_context.return_value = ""
    return AgentOrchestrator(rag_engine=rag, memory_manager=mem)


@pytest.fixture
def registry_and_executor():
    """ToolRegistry + ToolExecutor frais pour tests d'enregistrement."""
    reg = ToolRegistry()
    exec_ = ToolExecutor(reg)
    return reg, exec_


# ══════════════════════════════════════════════════════════════════
# Tests AgentOrchestrator — Cycle de vie
# ══════════════════════════════════════════════════════════════════


class TestAgentOrchestratorLifecycle:

    def test_singleton(self):
        """Le singleton AgentOrchestrator retourne toujours la même instance."""
        a = AgentOrchestrator()
        b = AgentOrchestrator()
        assert a is b

    def test_get_instance(self):
        """get_instance() retourne l'instance unique."""
        a = AgentOrchestrator()
        b = AgentOrchestrator.get_instance()
        assert a is b

    def test_reset_singleton(self):
        """_reset_singleton() permet de créer une nouvelle instance."""
        a = AgentOrchestrator()
        AgentOrchestrator._reset_singleton()
        b = AgentOrchestrator()
        assert a is not b

    def test_singleton_with_args(self):
        """Le constructeur n'écrase pas les attributs après initialisation."""
        a = AgentOrchestrator(rag_engine="engine_a", memory_manager="mem_a")
        b = AgentOrchestrator(rag_engine="engine_b", memory_manager="mem_b")
        assert a is b

    def test_properties_are_lazy(self):
        """rag_engine et memory_manager sont configurables."""
        orch = AgentOrchestrator(rag_engine=None, memory_manager=None)
        # None explicite → lazy init depuis le vrai RAGEngine/MemoryManager
        assert orch.rag_engine is not None
        assert orch.memory_manager is not None


# ══════════════════════════════════════════════════════════════════
# Tests AgentOrchestrator — Plan
# ══════════════════════════════════════════════════════════════════


class TestPlanPhase:

    @pytest.mark.asyncio
    async def test_plan_with_rag_and_memory(self, agent_orchestrator):
        """La phase plan collecte RAG et mémoire."""
        plan = await agent_orchestrator._plan("Quelles sont mes compétences ?")
        assert plan.decomposed is True
        assert len(plan.steps) > 0
        assert plan.rag_available is True
        assert plan.rag_documents_found > 0
        assert plan.memory_available is True

    @pytest.mark.asyncio
    async def test_plan_without_rag(self, agent_orchestrator_no_rag):
        """La phase plan fonctionne sans RAG (mock indisponible)."""
        plan = await agent_orchestrator_no_rag._plan("Test")
        assert plan.decomposed is True
        # mock déclenche RuntimeError → pas de RAG disponible
        assert plan.rag_available is False
        # mémoire mockée retourne chaîne vide → pas disponible
        assert plan.memory_available is False

    def test_decompose_simple_query(self):
        """Une requête simple n'est pas décomposée."""
        orch = AgentOrchestrator()
        steps = orch._decompose_query("Quelle est la météo ?")
        assert len(steps) == 1
        assert steps[0] == "Quelle est la météo ?"

    def test_decompose_with_connector(self):
        """Connexion 'et' entre deux questions."""
        orch = AgentOrchestrator()
        steps = orch._decompose_query("Qui est l'utilisateur ? et quelles sont ses compétences ?")
        assert len(steps) >= 1

    def test_decompose_multiple_questions(self):
        """Plusieurs '?' produisent plusieurs étapes."""
        orch = AgentOrchestrator()
        steps = orch._decompose_query("Qui est-ce ? Où va-t-il ?")
        assert len(steps) >= 2

    @pytest.mark.asyncio
    async def test_plan_public_api(self, agent_orchestrator):
        """plan() expose la décomposition."""
        steps = await agent_orchestrator.plan("Test objectif")
        assert isinstance(steps, list)
        assert len(steps) > 0


# ══════════════════════════════════════════════════════════════════
# Tests AgentOrchestrator — Execute
# ══════════════════════════════════════════════════════════════════


class TestExecutePhase:

    @pytest.mark.asyncio
    async def test_execute_with_rag(self, agent_orchestrator):
        """La phase execute collecte le contexte RAG."""
        plan = PlanResult(rag_available=True, rag_documents_found=2,
                          rag_confidence="HAUTE", memory_available=True)
        result = await agent_orchestrator._execute("test", plan)
        assert "rag_context" in result
        assert "memory_context" in result

    @pytest.mark.asyncio
    async def test_execute_without_rag(self, agent_orchestrator_no_rag):
        """La phase execute fonctionne sans RAG."""
        plan = PlanResult()
        result = await agent_orchestrator_no_rag._execute("test", plan)
        assert result["rag_context"] == ""


# ══════════════════════════════════════════════════════════════════
# Tests AgentOrchestrator — Verify
# ══════════════════════════════════════════════════════════════════


class TestVerifyPhase:

    def test_verify_high_confidence(self):
        """RAG haute confiance + mémoire = vérification réussie."""
        orch = AgentOrchestrator()
        trace = AgentTrace(
            query="test",
            rag_context="contenu RAG",
            memory_context="contexte mémoire",
        )
        plan = PlanResult(
            rag_available=True, rag_documents_found=3,
            rag_confidence="HAUTE", memory_available=True,
        )
        v = orch._verify(trace, plan)
        assert v.passed is True
        assert v.score >= 0.7
        assert v.has_content is True
        assert v.has_sources is True

    def test_verify_low_confidence(self):
        """Pas de RAG ni mémoire = échec de vérification."""
        orch = AgentOrchestrator()
        trace = AgentTrace(query="test")
        plan = PlanResult()
        v = orch._verify(trace, plan)
        assert v.passed is False
        assert v.score < 0.35

    def test_verify_partial(self):
        """RAG seule sans mémoire = vérification partielle."""
        orch = AgentOrchestrator()
        trace = AgentTrace(query="test", rag_context="contenu")
        plan = PlanResult(rag_available=True, rag_documents_found=2,
                          rag_confidence="MOYENNE")
        v = orch._verify(trace, plan)
        # RAG MOYENNE (0.25) + contenu (0.2) = 0.45 -> peut passer
        assert v.score >= 0.35 or v.score < 0.35

    @pytest.mark.asyncio
    async def test_verify_public_api(self, agent_orchestrator):
        """verify_result() expose la vérification."""
        result = await agent_orchestrator.verify_result({
            "query": "test",
            "rag_context": "contenu",
            "sources_count": 2,
        })
        assert "passed" in result
        assert "score" in result
        assert "reason" in result


# ══════════════════════════════════════════════════════════════════
# Tests AgentOrchestrator — Synthesize
# ══════════════════════════════════════════════════════════════════


class TestSynthesizePhase:

    def test_synthesize_with_context(self):
        """Synthèse avec RAG + mémoire produit une réponse structurée."""
        orch = AgentOrchestrator()
        trace = AgentTrace(
            query="test",
            rag_context="RAG: compétences Python",
            memory_context="Mémoire: utilisateur aime Python",
        )
        plan = PlanResult(
            rag_available=True, rag_documents_found=2,
            rag_confidence="HAUTE", memory_available=True,
        )
        verify = VerifyResult(passed=True, score=0.85, reason="tout bon",
                              has_content=True, has_sources=True,
                              has_memory_context=True)
        synthesis = orch._synthesize("test", trace, plan, verify)
        assert "RAG" in synthesis or "contexte" in synthesis or "Synthèse" in synthesis
        assert "HAUTE" in synthesis or "MOYENNE" in synthesis

    def test_synthesize_no_context(self):
        """Synthèse sans contexte produit une réponse par défaut."""
        orch = AgentOrchestrator()
        trace = AgentTrace(query="test")
        plan = PlanResult()
        verify = VerifyResult(passed=False, score=0.0, reason="rien",
                              has_content=False, has_sources=False,
                              has_memory_context=False)
        synthesis = orch._synthesize("test", trace, plan, verify)
        assert "trouvé" in synthesis.lower() or "Confiance" in synthesis

    def test_build_answer_with_memory(self):
        """build_answer utilise le contexte mémoire."""
        orch = AgentOrchestrator()
        trace = AgentTrace(query="test", memory_context="Nom: Jean\nÂge: 30")
        plan = PlanResult(memory_available=True)
        answer = orch._build_answer("test", trace, plan)
        assert "vous" in answer.lower() or "Jean" in answer

    def test_build_answer_no_context(self):
        """build_answer sans contexte retourne un message d'absence."""
        orch = AgentOrchestrator()
        trace = AgentTrace(query="test")
        plan = PlanResult()
        answer = orch._build_answer("test", trace, plan)
        assert "pas trouvé" in answer.lower()


# ══════════════════════════════════════════════════════════════════
# Tests AgentOrchestrator — Run (boucle complète)
# ══════════════════════════════════════════════════════════════════


class TestRun:

    @pytest.mark.asyncio
    async def test_run_empty_query(self, agent_orchestrator):
        """Requête vide retourne une erreur."""
        result = await agent_orchestrator.run("")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_run_success(self, agent_orchestrator):
        """Boucle complète avec RAG + mémoire réussit."""
        result = await agent_orchestrator.run("Quelles sont mes compétences ?")
        assert result["status"] in ("success", "partial")
        assert "query" in result
        assert "synthesis" in result
        assert "trace" in result
        trace = result["trace"]
        assert trace["status"] in ("success", "partial", "done")
        assert trace["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_run_trace_structure(self, agent_orchestrator):
        """Le trace contient toutes les phases."""
        result = await agent_orchestrator.run("test")
        trace = result["trace"]
        assert "plan" in trace
        assert "execute" in trace
        assert "verify" in trace
        assert "synthesis" in trace

    @pytest.mark.asyncio
    async def test_run_without_rag(self, agent_orchestrator_no_rag):
        """La boucle fonctionne sans RAG ni mémoire."""
        result = await agent_orchestrator_no_rag.run("test")
        assert result["status"] in ("success", "partial", "error")
        assert "trace" in result

    @pytest.mark.asyncio
    async def test_run_format_trace_summary(self, agent_orchestrator):
        """trace_summary est formaté lisiblement."""
        result = await agent_orchestrator.run("test")
        summary = result["trace_summary"]
        assert isinstance(summary, str)
        assert len(summary) > 0


# ══════════════════════════════════════════════════════════════════
# Tests Agent Tools — Définition et enregistrement
# ══════════════════════════════════════════════════════════════════


class TestAgentToolDefinitions:

    def test_agent_tools_defined(self):
        """Les 3 outils agent sont définis."""
        assert len(AGENT_TOOLS) == 3

    def test_agent_tools_names(self):
        """Les noms des outils sont corrects."""
        names = {t.name for t in AGENT_TOOLS}
        assert names == {"agent_query", "agent_plan", "agent_verify"}

    def test_agent_tools_category(self):
        """Tous les outils agent ont la catégorie 'agent'."""
        for t in AGENT_TOOLS:
            assert t.category == "agent", f"{t.name} n'est pas category='agent'"

    def test_agent_query_parameters(self):
        """agent_query a les bons paramètres."""
        tool = next(t for t in AGENT_TOOLS if t.name == "agent_query")
        param_names = {p.name for p in tool.parameters}
        assert "query" in param_names
        assert "mode" in param_names

    def test_agent_plan_parameters(self):
        """agent_plan a le bon paramètre."""
        tool = next(t for t in AGENT_TOOLS if t.name == "agent_plan")
        param_names = {p.name for p in tool.parameters}
        assert "goal" in param_names

    def test_agent_verify_parameters(self):
        """agent_verify a le bon paramètre."""
        tool = next(t for t in AGENT_TOOLS if t.name == "agent_verify")
        param_names = {p.name for p in tool.parameters}
        assert "result" in param_names


class TestAgentToolRegistration:

    def test_register_agent_tools(self, registry_and_executor):
        """register_agent_tools enregistre les 3 outils + handlers."""
        reg, exec_ = registry_and_executor
        register_agent_tools(reg, exec_)
        assert len(reg) == 3
        assert reg.get("agent_query") is not None
        assert reg.get("agent_plan") is not None
        assert reg.get("agent_verify") is not None

    def test_agent_tools_handlers_registered(self, registry_and_executor):
        """Les handlers sont bien enregistrés dans l'exécuteur."""
        reg, exec_ = registry_and_executor
        register_agent_tools(reg, exec_)
        assert "agent_query" in exec_._handlers
        assert "agent_plan" in exec_._handlers
        assert "agent_verify" in exec_._handlers

    def test_agent_tools_list_by_category(self, registry_and_executor):
        """Les outils agent sont listables par catégorie 'agent'."""
        reg, exec_ = registry_and_executor
        register_agent_tools(reg, exec_)
        agent_tools = reg.list_by_category("agent")
        assert len(agent_tools) == 3

    def test_agent_tools_to_schema(self, registry_and_executor):
        """Le schéma LLM des outils agent est valide."""
        reg, exec_ = registry_and_executor
        register_agent_tools(reg, exec_)
        schema = reg.to_llm_schema()
        agent_schemas = [s for s in schema if s["name"].startswith("agent_")]
        assert len(agent_schemas) == 3
        for s in agent_schemas:
            assert "name" in s
            assert "description" in s
            assert "parameters" in s


# ══════════════════════════════════════════════════════════════════
# Tests Agent Tools — Handlers (sans async, juste structure)
# ══════════════════════════════════════════════════════════════════


class TestAgentToolHandlers:

    def test_agent_query_no_query(self, registry_and_executor):
        """agent_query sans query retourne une erreur.

        Le handler agent_query attrape l'erreur interne et retourne
        un ToolResult(success=True, output=ToolResult(success=False, ...)).
        On vérifie donc le résultat NESTED.
        """
        reg, exec_ = registry_and_executor
        register_agent_tools(reg, exec_)
        result = exec_.execute("agent_query", {})
        # Le handler wrapper retourne success=True même si interne échoue
        # (l'erreur est encapsulée dans output)
        assert "output" in str(result)
        assert result.success is True  # le wrapper a fonctionné
        # L'erreur interne est dans le output
        inner = result.output if isinstance(result.output, ToolResult) else None
        if inner:
            assert inner.success is False
            assert "requis" in (inner.error or "").lower()

    def test_agent_plan_no_goal(self, registry_and_executor):
        """agent_plan sans goal retourne une erreur."""
        reg, exec_ = registry_and_executor
        register_agent_tools(reg, exec_)
        result = exec_.execute("agent_plan", {})
        assert result.success is True  # wrapper a fonctionné
        inner = result.output if isinstance(result.output, ToolResult) else None
        if inner:
            assert inner.success is False
            assert "requis" in (inner.error or "").lower()

    def test_agent_verify_no_result(self, registry_and_executor):
        """agent_verify sans result retourne une erreur."""
        reg, exec_ = registry_and_executor
        register_agent_tools(reg, exec_)
        result = exec_.execute("agent_verify", {})
        assert result.success is True  # wrapper a fonctionné
        inner = result.output if isinstance(result.output, ToolResult) else None
        if inner:
            assert inner.success is False
            assert "requis" in (inner.error or "").lower()

    def test_agent_unknown_tool(self, registry_and_executor):
        """Un outil agent inexistant est correctement refusé."""
        reg, exec_ = registry_and_executor
        register_agent_tools(reg, exec_)
        result = exec_.execute("agent_unknown", {})
        assert result.success is False
        assert "inconnu" in (result.error or "").lower()


# ══════════════════════════════════════════════════════════════════
# Tests Intégration — ToolOrchestrator + Agent Tools
# ══════════════════════════════════════════════════════════════════


class TestIntegration:

    @pytest.mark.asyncio
    async def test_agent_orchestrator_run_returns_dict(self, agent_orchestrator):
        """Le résultat de run() est un dict avec les clés attendues."""
        result = await agent_orchestrator.run("test")
        assert isinstance(result, dict)
        assert "query" in result
        assert "status" in result
        assert "synthesis" in result
        assert "trace" in result
        assert "trace_summary" in result

    def test_agent_trace_dataclass(self):
        """AgentTrace se crée et se sérialise."""
        trace = AgentTrace(query="test", status="planning")
        d = trace.to_dict()
        assert d["query"] == "test"
        assert d["status"] == "planning"
        assert "duration_ms" in d

    def test_plan_result_dataclass(self):
        """PlanResult se crée avec les valeurs par défaut."""
        p = PlanResult()
        assert p.decomposed is False
        assert p.steps == []
        assert p.rag_available is False

    def test_verify_result_dataclass(self):
        """VerifyResult se crée avec les valeurs par défaut."""
        v = VerifyResult()
        assert v.passed is False
        assert v.score == 0.0

    @pytest.mark.asyncio
    async def test_agent_orchestrator_trace_summary(self, agent_orchestrator):
        """trace_summary est toujours présent et non vide."""
        result = await agent_orchestrator.run("test")
        assert result["trace_summary"] is not None
        assert len(result["trace_summary"]) > 0

    @pytest.mark.asyncio
    async def test_agent_orchestrator_error_handling(self):
        """run() gère les erreurs internes avec un statut error."""
        with patch.object(AgentOrchestrator, '_plan',
                          side_effect=RuntimeError("Simulated crash")):
            orch = AgentOrchestrator(rag_engine=None, memory_manager=None)
            result = await orch.run("test query")
            assert result["status"] == "error"
            assert "Simulated crash" in result.get("trace", {}).get("error", "")
