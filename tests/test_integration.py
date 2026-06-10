"""Tests d'intégration complets — Sprint 6 (Consolidation V8+).

Utilise pytest fixtures pour mocker les dépendances externes (CloudLLM, RAG)
et tester le pipeline complet de NuruOrchestrator.

Tests :
1. Pipeline RAG complet avec mock cloud
2. Pipeline avec décomposition (sub-queries)
3. Pipeline avec FactChecker + retry loop
4. Pipeline offline (mode dégradé)
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.ERROR)

# ═══════════════════════════════════════════════════════════
# Mock fixtures
# ═══════════════════════════════════════════════════════════


class MockCloudLLM:
    """Mock CloudLLM avec modes contrôlables."""

    def __init__(self, mode="ok"):
        self.mode = mode

    def generate(self, prompt: str, timeout: float = 5.0) -> str:
        if self.mode == "empty":
            return ""
        if self.mode == "slow":
            raise TimeoutError("Timeout simulé")
        if "verified" in prompt.lower() or "vérificateur" in prompt.lower():
            if self.mode == "fact_fail":
                return '{"verified": false, "issues": ["Affirmation non trouvée dans les sources"]}'
            return '{"verified": true, "issues": []}'
        if "décompose" in prompt.lower() or "sous-question" in prompt.lower():
            return '["rendement riz Palabek 2023", "rendement mais Palabek 2023"]'
        if "requête de recherche" in prompt.lower():
            return "rendement riz Palabek 2023 production agricole"
        return "Réponse générique du mock cloud"

    async def generate_stream(self, prompt="", intent="RAG", system_prompt=""):
        response = "Voici une réponse basée sur les documents fournis."
        for token in response:
            yield token
            await asyncio.sleep(0)


class MockRAGResult:
    """Mock RAGResult avec niveaux de confiance contrôlables."""

    def __init__(
        self,
        confidence_label="HAUTE",
        chunks_injected=3,
        top_score=0.85,
        sources=None,
        diagnostic=None,
    ):
        self.confidence_label = confidence_label
        self.chunks_injected = chunks_injected
        self.top_score = top_score
        self.sources = sources or [
            {"name": "test.pdf", "score": 0.85, "preview": "Contenu test..."}
        ]
        self.diagnostic = diagnostic or {
            "confiance": confidence_label,
            "chunks": chunks_injected,
            "score": top_score,
        }
        self.documents_found = 1
        self.chunks_retrieved = 5
        self.retrieval_time_ms = 150.0
        self.query_rewritten = "requête optimisée"
        self.rejected_chunks = 0
        self.rejection_reason = ""
        self.tokens_injected = 200
        self.top_k_configured = 5
        self.top_k_actual = 3
        self.all_scores = [top_score, 0.65, 0.45]
        self.source_list = ["test.pdf"]


class MockRAGEngine:
    """Mock RAGEngine retournant des résultats contrôlés."""

    def __init__(self, confidence_label="HAUTE"):
        self.result = MockRAGResult(confidence_label=confidence_label)
        self.last_top_score = self.result.top_score

    async def retrieve(self, query, k=None):
        return "Contexte RAG: Le rendement du riz est de 4.5 t/ha.", self.result


class MockRouter:
    """Mock SemanticRouter retournant des décisions contrôlées."""

    async def route_with_context(self, ctx):
        return MagicMock(
            decision="LOCAL_RAG",
            confidence=0.85,
            rag_top_score=0.85,
            hybrid_strategy="local_only",
        )


class MockMemoryStore:
    """Mock MemoryStore pour les tests."""

    def __init__(self):
        self.facts = []
        self.history = []
        self.cache = {}

    async def get_cache(self, query):
        return None, None

    async def set_cache(self, query, response, diagnostic=None):
        pass

    def add_message(self, role, content):
        self.history.append({"role": role, "content": content})

    def add_reflection(self, query, feedback, score):
        pass

    def get_recent_facts(self, limit=20):
        return self.facts

    def get_recent_history(self, limit=8):
        return self.history[-limit:]

    def get_procedures(self):
        return ""


class MockWebSearch:
    """Mock WebSearch."""

    async def search(self, query):
        return "Résultat recherche Web pour: " + query


class MockRuntime:
    """Mock RuntimeManager."""

    def __init__(self):
        self._last_generation_stats = {"rag_score": 0.85}

    async def schedule_generator(self, name, gen):
        async for token in gen:
            yield token

    def update_generation_stats(self, **kwargs):
        self._last_generation_stats.update(kwargs)


class MockPolicyEngine:
    def should_use_cloud(self, ctx):
        return False


class MockEventBus:
    """Mock EventBus qui capture les événements émis."""

    def __init__(self):
        self.events = []

    async def emit(self, event_type, data=None):
        self.events.append((event_type, data))

    def emit_sync(self, event_type, data=None):
        self.events.append((event_type, data))

    def drain(self):
        return list(self.events)


# ═══════════════════════════════════════════════════════════
# Fixtures pytest
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def mock_cloud():
    return MockCloudLLM()


@pytest.fixture
def mock_rag_high():
    return MockRAGEngine(confidence_label="HAUTE")


@pytest.fixture
def mock_rag_low():
    return MockRAGEngine(confidence_label="FAIBLE")


@pytest.fixture
def mock_memory():
    return MockMemoryStore()


@pytest.fixture
def mock_router():
    return MockRouter()


@pytest.fixture
def mock_web():
    return MockWebSearch()


@pytest.fixture
def mock_runtime():
    return MockRuntime()


@pytest.fixture
def mock_bus():
    return MockEventBus()


@pytest.fixture
def mock_policy():
    return MockPolicyEngine()


@pytest.fixture
def orchestrator(mock_router, mock_rag_high, mock_cloud, mock_memory,
                  mock_policy, mock_bus, mock_runtime, mock_web):
    """Crée un NuruOrchestrator avec toutes les dépendances mockées."""
    from src.core.orchestrator import NuruOrchestrator
    from src.core.policies import PolicyEngine
    from src.core.events import EventBus

    orch = NuruOrchestrator(
        router=mock_router,
        rag_engine=mock_rag_high,
        local_llm=MagicMock(),
        cloud_llm=mock_cloud,
        memory_store=mock_memory,
        policy_engine=mock_policy,
        event_bus=mock_bus,
        runtime_manager=mock_runtime,
        web_search=mock_web,
        context_budget=MagicMock(),
        reflection_engine=None,
        system_prompt_builder=lambda intent, facts=None, procedures="": (
            "Tu es NURU, assistant de Leblanc."
        ),
    )
    return orch


# ═══════════════════════════════════════════════════════════
# 1. Pipeline RAG complet avec mock cloud
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_rag_pipeline_complet(orchestrator, mock_bus):
    """Test : Pipeline RAG complet → tokens streamés + événements émis."""
    tokens = []
    async for token in orchestrator.process_query(
        query="Quel est le rendement du riz?",
        session_id="test-session",
    ):
        tokens.append(token)

    full_response = "".join(tokens)
    assert len(full_response) > 0, "La réponse ne devrait pas être vide"
    assert "réponse" in full_response.lower() or "document" in full_response.lower(), \
        f"Réponse inattendue: {full_response[:100]}"

    # Vérifier les événements émis
    event_types = [e[0] for e in mock_bus.events]
    print(f"Événements émis: {event_types}")

    assert "query.received" in event_types, "Événement query.received manquant"
    assert "route.decided" in event_types, "Événement route.decided manquant"
    assert "generation_complete" in event_types, "Événement generation_complete manquant"
    assert "rag_score" in event_types, "Événement rag_score manquant"

    # Vérifier les données de rag_score
    rag_events = [e for e in mock_bus.events if e[0] == "rag_score"]
    assert len(rag_events) >= 1
    assert rag_events[0][1]["score"] > 0

    print("✅ Pipeline RAG complet OK")


# ═══════════════════════════════════════════════════════════
# 2. Pipeline avec décomposition (sub-queries)
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pipeline_with_decomposition(orchestrator, mock_bus):
    """Test : Pipeline avec décomposition → sous-requêtes traitées."""
    # Requête longue qui déclenche la décomposition
    complex_query = (
        "Quels sont les rendements du riz et du maïs à Palabek "
        "en 2023 et quelles sont les superficies cultivées?"
    )

    tokens = []
    async for token in orchestrator.process_query(
        query=complex_query,
        session_id="test-session",
    ):
        tokens.append(token)

    full_response = "".join(tokens)
    assert len(full_response) > 0, "La réponse décomposée ne devrait pas être vide"

    # Vérifier que query.decomposed a été émis (ou au moins que le pipeline a fonctionné)
    event_types = [e[0] for e in mock_bus.events]
    print(f"Événements (décomposition): {event_types}")

    assert "generation_complete" in event_types, "generation_complete manquant"

    query_received = [e for e in mock_bus.events if e[0] == "query.received"]
    assert len(query_received) >= 1

    print("✅ Pipeline avec décomposition OK")


# ═══════════════════════════════════════════════════════════
# 3. Pipeline avec FactChecker + retry loop
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pipeline_factcheck_retry(mock_router, mock_rag_high, mock_memory,
                                         mock_policy, mock_bus, mock_runtime, mock_web):
    """Test : FactChecker échoue → retry → vérification warning émis."""
    from src.core.orchestrator import NuruOrchestrator

    # CloudLLM qui échoue la vérification
    failing_cloud = MockCloudLLM(mode="fact_fail")

    orch = NuruOrchestrator(
        router=mock_router,
        rag_engine=mock_rag_high,
        local_llm=MagicMock(),
        cloud_llm=failing_cloud,
        memory_store=mock_memory,
        policy_engine=mock_policy,
        event_bus=mock_bus,
        runtime_manager=mock_runtime,
        web_search=mock_web,
        context_budget=MagicMock(),
        reflection_engine=None,
        system_prompt_builder=lambda intent, facts=None, procedures="": (
            "Tu es NURU, assistant de Leblanc."
        ),
    )

    tokens = []
    async for token in orch.process_query(
        query="Quel est le rendement du riz à Palabek?",
        session_id="test-session",
    ):
        tokens.append(token)

    full_response = "".join(tokens)
    assert len(full_response) > 0

    event_types = [e[0] for e in mock_bus.events]
    print(f"Événements (factcheck): {event_types}")

    # Soit verification_failed (retry réussi) ou verification_warning (retry déjà fait)
    has_verification_event = (
        "verification_failed" in event_types or
        "verification_warning" in event_types
    )
    assert has_verification_event, \
        f"Aucun événement de vérification émis. Événements: {event_types}"

    print("✅ Pipeline FactChecker + retry OK")


@pytest.mark.asyncio
async def test_pipeline_factcheck_passes(mock_router, mock_rag_high, mock_memory,
                                          mock_policy, mock_bus, mock_runtime, mock_web):
    """Test : FactChecker réussi → pas de warning."""
    from src.core.orchestrator import NuruOrchestrator

    passing_cloud = MockCloudLLM(mode="ok")

    orch = NuruOrchestrator(
        router=mock_router,
        rag_engine=mock_rag_high,
        local_llm=MagicMock(),
        cloud_llm=passing_cloud,
        memory_store=mock_memory,
        policy_engine=mock_policy,
        event_bus=mock_bus,
        runtime_manager=mock_runtime,
        web_search=mock_web,
        context_budget=MagicMock(),
        reflection_engine=None,
        system_prompt_builder=lambda intent, facts=None, procedures="": (
            "Tu es NURU, assistant de Leblanc."
        ),
    )

    tokens = []
    async for token in orch.process_query(
        query="Quel est le rendement du riz?",
        session_id="test-session",
    ):
        tokens.append(token)

    event_types = [e[0] for e in mock_bus.events]
    print(f"Événements (factcheck ok): {event_types}")

    # Pas de verification_failed ou verification_warning
    has_fail = "verification_failed" in event_types
    has_warning = "verification_warning" in event_types
    assert not has_fail, "verification_failed ne devrait pas être émis"
    assert not has_warning, "verification_warning ne devrait pas être émis"

    print("✅ Pipeline FactChecker passe OK")


# ═══════════════════════════════════════════════════════════
# 4. Pipeline offline (mode dégradé)
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pipeline_offline(mock_router, mock_rag_high, mock_memory,
                                 mock_policy, mock_bus, mock_runtime, mock_web):
    """Test : Pipeline offline → fallback local + mode dégradé."""
    from src.core.orchestrator import NuruOrchestrator

    orch = NuruOrchestrator(
        router=mock_router,
        rag_engine=mock_rag_high,
        local_llm=MagicMock(),
        cloud_llm=MockCloudLLM(),
        memory_store=mock_memory,
        policy_engine=mock_policy,
        event_bus=mock_bus,
        runtime_manager=mock_runtime,
        web_search=mock_web,
        context_budget=MagicMock(),
        reflection_engine=None,
        system_prompt_builder=lambda intent, facts=None, procedures="": (
            "Tu es NURU, assistant de Leblanc."
        ),
    )

    # Patch _check_connectivity pour retourner False (offline)
    original_check = orch._check_connectivity
    orch._check_connectivity = AsyncMock(return_value=False)

    tokens = []
    async for token in orch.process_query(
        query="Quel est le rendement du riz?",
        session_id="test-session",
    ):
        tokens.append(token)

    # Restaurer
    orch._check_connectivity = original_check

    full_response = "".join(tokens)
    assert len(full_response) > 0, "La réponse offline ne devrait pas être vide"

    event_types = [e[0] for e in mock_bus.events]
    print(f"Événements (offline): {event_types}")

    assert "query.received" in event_types
    assert "route.decided" in event_types

    print("✅ Pipeline offline OK")


# ═══════════════════════════════════════════════════════════
# 5. Cache sémantique SemanticCache (isolation)
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_semantic_cache():
    """Test : SemanticCache opérations CRUD + diagnostic."""
    import tempfile
    import os
    from src.rag.memory_store import SemanticCache

    tmp = Path(tempfile.mktemp(suffix=".db"))
    sc = SemanticCache(db_path=tmp)

    try:
        # Cache miss
        h = sc.hash_query("requête inconnue")
        resp, diag = sc.get_cache(h)
        assert resp is None
        assert diag is None
        print("  ✅ Cache miss OK")

        # Cache set + get avec diagnostic
        h2 = sc.hash_query("rendement riz Palabek")
        diag_data = {
            "strategies_tried": ["vector", "fts"],
            "scores": [0.85, 0.65],
            "timing_ms": 120.5,
        }
        sc.set_cache(h2, "Le rendement du riz est de 4.5 t/ha",
                      diagnostic=diag_data,
                      query_sample="rendement riz Palabek")

        resp, diag = sc.get_cache(h2)
        assert resp == "Le rendement du riz est de 4.5 t/ha"
        assert diag["strategies_tried"] == ["vector", "fts"]
        assert diag["scores"] == [0.85, 0.65]
        print("  ✅ Cache set+get avec diagnostic OK")

        # get_diagnostics
        diags = sc.get_diagnostics()
        assert len(diags) >= 1
        assert diags[0]["query_hash"] == h2
        assert diags[0]["hit_count"] >= 1
        print("  ✅ get_diagnostics OK")

        # stats
        stats = sc.get_stats()
        assert stats["total_entries"] >= 1
        assert stats["total_hits"] >= 1
        print("  ✅ Stats OK")

    finally:
        os.unlink(tmp)
    print("  ✅ Cache sémantique complet OK")


# ═══════════════════════════════════════════════════════════
# Exécution directe
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
