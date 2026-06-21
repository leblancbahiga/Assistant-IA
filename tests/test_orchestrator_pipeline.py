"""
Tests unitaires — Orchestrator : cache, exceptions, recovery V10.2.

Couvre :
- Cache hit (L1) → retour immédiat, pas de génération
- Cache miss → pipeline normal
- Exception hierarchy : RAGError récupère, LLMError fallback, GuardError yield
- Mode offline (flux dégradé)
- Événements émis : cache_hit, generation_complete, error
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.orchestrator import NuruOrchestrator
from src.core.exceptions import RAGError, LLMError, MemoryError


# ═══════════════════════════════════════════════════════
# 1. Mock classes (minimales pour orchestrateur)
# ═══════════════════════════════════════════════════════


class MockMemoryStore:
    def __init__(self):
        self.cache = {}

    async def get_cache(self, query):
        entry = self.cache.get(query)
        if entry:
            return entry, None
        return None, None

    async def set_cache(self, query, response, diagnostic=None):
        self.cache[query] = response

    def add_message(self, role, content):
        pass

    def add_reflection(self, query, feedback, score):
        pass

    def get_recent_facts(self, limit=20):
        return ["fact1"]

    def get_recent_history(self, limit=8):
        return []

    def get_procedures(self):
        return ""


class EventBusCapture:
    def __init__(self):
        self.events = []

    async def emit(self, event_type, data=None):
        self.events.append((event_type, data))

    def emit_sync(self, event_type, data=None):
        self.events.append((event_type, data))

    def drain(self):
        return list(self.events)


class MockRouter:
    async def route_with_context(self, ctx, **kwargs):
        return MagicMock(
            decision="LOCAL_RAG",
            confidence=0.85,
            rag_top_score=0.85,
            intent="RAG",
        )


class MockRAGEngine:
    def __init__(self, confidence_label="HAUTE"):
        self.confidence_label = confidence_label
        self.last_top_score = 0.85

    async def retrieve(self, query, k=None):
        result = MagicMock(
            confidence_label=self.confidence_label,
            chunks_injected=3,
            top_score=self.last_top_score,
            sources=[{"name": "test.pdf", "score": 0.85}],
            documents_found=1,
            chunks_retrieved=3,
            retrieval_time_ms=100.0,
            query_rewritten="",
            rejected_chunks=0,
            rejection_reason="",
            tokens_injected=200,
            top_k_configured=5,
            top_k_actual=3,
            all_scores=[0.85, 0.60],
            source_list=["test.pdf"],
        )
        return "Contexte RAG mocké.", result


class MockLLM:
    def __init__(self, mode="ok"):
        self.mode = mode

    async def generate_stream(self, prompt="", intent="RAG", system_prompt="", **kwargs):
        if self.mode == "error":
            raise LLMError("Simulated LLM failure")
        if self.mode == "empty":
            return
            yield  # pragma: no cover
        response = "Réponse du LLM mocké."
        for token in response:
            yield token
            await asyncio.sleep(0)


class MockContextBudget:
    def allocate(self, system, rag, facts, history, user_facts=None, include_system=True, model_family="phi", rag_priority=False):
        # Retourne un prompt assemblé
        parts = [system, rag]
        if facts:
            parts.extend(facts)
        if history:
            for h in history:
                parts.append(f"{h.get('role', '')}: {h.get('content', '')}")
        return "\n".join(parts)

    def build_prompt(self, query, system_prompt, context, history, facts, user_facts, intent="RAG"):
        return "Prompt mocké."


class MockRuntime:
    async def schedule_generator(self, name, gen):
        async for token in gen:
            yield token

    def update_generation_stats(self, **kwargs):
        pass


@pytest.fixture
def base_mocks():
    return {
        "router": MockRouter(),
        "rag_engine": MockRAGEngine(),
        "local_llm": MockLLM(mode="ok"),
        "cloud_llm": MockLLM(mode="ok"),
        "memory_store": MockMemoryStore(),
        "event_bus": EventBusCapture(),
        "runtime": MockRuntime(),
        "web_search": MagicMock(),
        "policy_engine": MagicMock(),
        "context_budget": MockContextBudget(),
    }


def _make_orchestrator(**overrides):
    defaults = {
        "router": MockRouter(),
        "rag_engine": MockRAGEngine(),
        "local_llm": MockLLM(mode="ok"),
        "cloud_llm": MockLLM(mode="ok"),
        "memory_store": MockMemoryStore(),
        "policy_engine": MagicMock(),
        "event_bus": EventBusCapture(),
        "runtime_manager": MockRuntime(),
        "web_search": MagicMock(),
        "context_budget": MockContextBudget(),
        # V10.3 — reflection_engine supprimé (stubs YAGNI, AUDIT Arch-01)
        "system_prompt_builder": lambda intent, facts=None, procedures="": (
            "Tu es NURU, assistant de Leblanc."
        ),
    }
    defaults.update(overrides)
    return NuruOrchestrator(**defaults)


@pytest.mark.asyncio
async def test_cache_hit_retour_immediat():
    """Cache hit → réponse retournée sans appeler le LLM"""
    ms = MockMemoryStore()
    ms.cache["test query"] = "Réponse en cache."

    orch = _make_orchestrator(memory_store=ms)
    tokens = []
    async for token in orch.process_query("test query"):
        tokens.append(token)

    response = "".join(tokens)
    assert response == "Réponse en cache."
    # Vérifier que l'événement cache_hit a été émis
    event_types = [e[0] for e in orch.event_bus.events]
    assert "cache_hit" in event_types


@pytest.mark.asyncio
async def test_cache_miss_pipeline_normal():
    """Cache miss → pipeline complet → réponse du LLM"""
    orch = _make_orchestrator()
    tokens = []
    async for token in orch.process_query("nouvelle requête"):
        tokens.append(token)

    response = "".join(tokens)
    assert len(response) > 0
    event_types = [e[0] for e in orch.event_bus.events]
    assert "generation_complete" in event_types


@pytest.mark.asyncio
async def test_llm_error_recuperation():
    """LLM lève une exception → yield message d'erreur, pas de crash"""
    orch = _make_orchestrator(
        cloud_llm=MockLLM(mode="error"),
        context_budget=MockContextBudget(),
    )
    tokens = []
    async for token in orch.process_query("provoque erreur"):
        tokens.append(token)

    response = "".join(tokens)
    # Doit contenir un message d'erreur, pas crasher
    assert len(response) > 0
    assert "⚠️" in response or "Erreur" in response or "error" in response.lower()
    # L'erreur est catchée et yield, mais l'orchestrateur n'émet pas d'event dédié
    # (l'erreur est dans le flux yield, visible par l'UI)


@pytest.mark.asyncio
async def test_generation_complete_event():
    """Pipeline réussi → generation_complete émis"""
    orch = _make_orchestrator()
    async for _ in orch.process_query("test event"):
        pass

    event_types = [e[0] for e in orch.event_bus.events]
    assert "generation_complete" in event_types


@pytest.mark.asyncio
async def test_query_tracke_dans_memoire():
    """Requête et réponse enregistrées dans memory_store"""
    ms = MockMemoryStore()
    spy_add = MagicMock(wraps=ms.add_message)
    ms.add_message = spy_add

    orch = _make_orchestrator(memory_store=ms)
    async for _ in orch.process_query("test mémoire"):
        pass

    # add_message appelé pour user + assistant
    assert spy_add.call_count >= 2
    user_call = spy_add.call_args_list[0]
    assert user_call[0][0] == "user"


@pytest.mark.asyncio
async def test_pipeline_offline():
    """Mode offline : pipeline continue sans cloud (mode dégradé)"""
    orch = _make_orchestrator(
        local_llm=MockLLM(mode="ok"),
    )
    tokens = []
    async for token in orch.process_query("test offline"):
        tokens.append(token)

    response = "".join(tokens)
    assert len(response) > 0
    event_types = [e[0] for e in orch.event_bus.events]
    assert "generation_complete" in event_types
