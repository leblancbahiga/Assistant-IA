"""Test configuration et fixtures pour NURU V12.

Pytest 9.0+ / asyncio.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Rajouter src au path si pas déjà fait ──────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(PROJECT_ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


# ── Fixtures globales ──────────────────────────────────────────────────

@pytest.fixture(scope="session")
def anyio_backend():
    """Backend asyncio pour les tests async."""
    return "asyncio"


@pytest.fixture
def mock_config():
    """Mock de src.config.config avec les valeurs de test."""
    with patch("src.config.config") as cfg:
        cfg.rag_router_min_score = 0.15
        cfg.rag_max_context_tokens = 1024
        cfg.hybrid_mode = "local_only"
        cfg.cloud_primary = "groq"
        cfg.cloud_fallback_order = ["openrouter", "deepseek"]
        yield cfg


@pytest.fixture
def mock_rag_engine():
    """Mock de RAGEngine retournant des résultats contrôlés."""
    from src.rag_engine import RAGResult

    engine = MagicMock()
    engine.retrieve = AsyncMock()
    result = RAGResult(
        documents_found=2,
        chunks_retrieved=5,
        top_score=0.85,
        all_scores=[0.85, 0.42],
        sources=[{"source": "cv.pdf", "title": "Expérience chez IITA"},
                 {"source": "cv.pdf", "title": "Formation"}],
        confidence_label="HAUTE",
    )
    engine.retrieve.return_value = ("contenu RAG de test", result)
    return engine


@pytest.fixture
def mock_cloud_llm():
    """Mock de CloudLLM avec generate_stream contrôlé.

    Utilise une vraie fonction génératrice asynchrone (pas AsyncMock)
    pour que 'async for' dans Router._classify_with_llm fonctionne.
    """
    llm = MagicMock()

    async def _default_stream(*args, **kwargs):
        yield "general"

    llm.generate_stream = _default_stream
    return llm


@pytest.fixture
def mock_memory_store():
    """Mock de MemoryStore avec faits contrôlés."""
    store = MagicMock()
    store.get_recent_facts.return_value = [
        {"fact_type": "preference", "content": "L'utilisateur aime le café", "confidence": 0.9}
    ]
    store.get_procedures.return_value = [
        {"name": "formater_date", "content": "Formater les dates en JJ/MM/AAAA"}
    ]
    store.get_recent_history.return_value = []
    store.format_facts_for_prompt.return_value = "- L'utilisateur aime le café"
    store.extract_facts = AsyncMock()
    store.extract_facts.return_value = []
    store.store_fact = MagicMock()
    return store


@pytest.fixture
def mock_session_store():
    """Mock de SessionStore."""
    store = MagicMock()
    store.build_context.return_value = "Messages récents..."
    return store


@pytest.fixture
def mock_context_budget():
    """Mock de ContextBudget avec allocate contrôlé."""
    budget = MagicMock()
    budget.allocate.return_value = "system prompt\n\ncontexte documentaire"
    return budget


@pytest.fixture
def router_instance(mock_rag_engine, mock_cloud_llm):
    """Instance réelle du Router avec dépendances mockées."""
    from src.routing import Router

    r = Router(
        rag_engine=mock_rag_engine,
        is_online_check=lambda: True,
        cloud_llm=mock_cloud_llm,
    )
    return r


@pytest.fixture
def router_instance_offline(mock_rag_engine, mock_cloud_llm):
    """Router en mode hors-ligne."""
    from src.routing import Router

    r = Router(
        rag_engine=mock_rag_engine,
        is_online_check=lambda: False,
        cloud_llm=mock_cloud_llm,
    )
    return r


@pytest.fixture
def router_instance_no_llm(mock_rag_engine):
    """Router sans cloud LLM (pas de classification)."""
    from src.routing import Router

    r = Router(
        rag_engine=mock_rag_engine,
        is_online_check=lambda: True,
        cloud_llm=None,
    )
    return r


@pytest.fixture
def prompt_builder_instance(mock_memory_store, mock_session_store, mock_context_budget):
    """Instance du DynamicPromptBuilder avec dépendances mockées."""
    from src.routing import DynamicPromptBuilder

    builder = DynamicPromptBuilder()
    return builder
