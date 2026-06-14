"""
Tests d'intégration V10.3 — Orchestrator découplé.

Valide que RAGOrchestrator + LLMGenerator + NuruOrchestrator allégé
fonctionnent ensemble comme prévu.
"""
from __future__ import annotations

import asyncio
import logging
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.rag_engine import RAGResult
from src.orchestration.rag_pipeline import RAGOrchestrator
from src.orchestration.llm_generator import LLMGenerator

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
#  Fixtures
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_rag_engine():
    engine = MagicMock()
    # retrieve() utilisé par retrieve_primary
    engine.retrieve = AsyncMock(return_value=(
        "Document A sur le machine learning. Document B sur les réseaux.",
        MagicMock(confidence_label="HAUTE", rag_score=0.85, last_top_score=0.87,
                  source_list=["doc_a.pdf", "doc_b.pdf"], chunks_retrieved=2),
    ))
    return engine


@pytest.fixture
def mock_guard():
    guard = MagicMock()
    guard.is_active = False
    guard.is_strict = False
    guard.should_block = MagicMock(return_value=False)
    guard.refuse_message = MagicMock(return_value="⛔ Réponse bloquée.")
    return guard


@pytest.fixture
def mock_verifier():
    vr = MagicMock()
    vr.verify = MagicMock(return_value=MagicMock(valid=True, score=0.9))
    return vr


@pytest.fixture
def mock_event_bus():
    bus = MagicMock()
    bus.emit = AsyncMock()
    return bus


@pytest.fixture
def mock_stream_llm():
    llm = MagicMock()
    llm.is_online = True
    llm.model_name = "mock-model"

    async def _stream(*args, **kwargs):
        for token in ["Réponse", " mockée", " découplée", "."]:
            yield token

    llm.generate_stream = _stream
    return llm


@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.is_online = True
    ctx.already_fact_checked = False
    ctx.already_retried = False
    ctx.keywords = None
    ctx.mode = "cloud"
    ctx.ram_free_mb = 4096
    ctx.already_fallback = False
    return ctx


@pytest.fixture
def mock_runtime():
    rt = MagicMock()
    rt.is_online = True
    rt.get_config = MagicMock(return_value={})
    return rt


@pytest.fixture
def mock_policy():
    pe = MagicMock()
    pe.get = MagicMock(return_value=None)
    return pe


# ══════════════════════════════════════════════════════════════════════════
#  RAGOrchestrator factory
# ══════════════════════════════════════════════════════════════════════════

def _make_rag(mock_rag_engine, mock_guard, mock_verifier,
              mock_event_bus, mock_stream_llm):
    web = AsyncMock()
    web.search = AsyncMock(return_value="Résultat web mocké")
    r = RAGOrchestrator(
        rag_engine=mock_rag_engine,
        cloud_llm=mock_stream_llm,
        web_search=web,
        event_bus=mock_event_bus,
        response_guard=mock_guard,
        evidence_verifier=mock_verifier,
    )
    r.fallback_guard = mock_guard
    return r


# ══════════════════════════════════════════════════════════════════════════
#  1. RAGOrchestrator — retrieve_multi
# ══════════════════════════════════════════════════════════════════════════

class TestRAGOrchestratorRetrieve:

    @pytest.fixture
    def rag(self, mock_rag_engine, mock_guard, mock_verifier,
            mock_event_bus, mock_stream_llm):
        return _make_rag(mock_rag_engine, mock_guard, mock_verifier,
                         mock_event_bus, mock_stream_llm)

    @pytest.mark.asyncio
    async def test_retrieve_multi_rag(self, rag):
        """RAG intent → retrieve multi-sources + merge."""
        # D'abord un retrieve primaire pour avoir du contexte
        primary_ctx, primary_result = await rag.rag_engine.retrieve(
            "machine learning")
        rag_context, web_context, merged = await rag.retrieve_multi(
            query="Parle-moi du machine learning",
            intent="RAG",
            primary_rag_context=primary_ctx,
            primary_rag_result=primary_result,
        )
        assert rag_context.strip(), "RAG context should be non-empty"
        assert merged is not None
        assert merged.confidence_label in ("HAUTE", "MOYENNE", "FAIBLE")

    @pytest.mark.asyncio
    async def test_retrieve_multi_simple(self, rag):
        """SIMPLE intent → pas de retrieve."""
        rag_context, web_context, merged = await rag.retrieve_multi(
            query="Bonjour",
            intent="SIMPLE",
            primary_rag_context="",
            primary_rag_result=None,
        )
        assert rag_context == ""
        assert web_context == ""
        assert merged is None

    @pytest.mark.asyncio
    async def test_retrieve_multi_complex(self, rag):
        """COMPLEX intent → retrieve déclenché."""
        primary_ctx, primary_result = await rag.rag_engine.retrieve(
            "transformers")
        rag_context, web_context, merged = await rag.retrieve_multi(
            query="Explique les transformers et le fine-tuning",
            intent="COMPLEX",
            primary_rag_context=primary_ctx,
            primary_rag_result=primary_result,
        )
        assert rag_context.strip(), "Complex intent should retrieve"
        assert merged is not None


# ══════════════════════════════════════════════════════════════════════════
#  2. RAGOrchestrator — integrate_spotlight
# ══════════════════════════════════════════════════════════════════════════

class TestRAGOrchestratorSpotlight:

    @pytest.fixture
    def rag(self, mock_rag_engine, mock_guard, mock_verifier,
            mock_event_bus, mock_stream_llm):
        return _make_rag(mock_rag_engine, mock_guard, mock_verifier,
                         mock_event_bus, mock_stream_llm)

    def test_integrate_spotlight(self, rag):
        """Spotlight s'intègre sans erreur."""
        result = rag.integrate_spotlight(
            rag_context="Contexte existant.",
            rag_result=RAGResult(),
            spotlight_ctx="",
        )
        assert isinstance(result, str)

    def test_integrate_spotlight_empty(self, rag):
        """Spotlight avec contexte vide."""
        result = rag.integrate_spotlight(
            rag_context="",
            rag_result=RAGResult(),
            spotlight_ctx="",
        )
        assert isinstance(result, str)


# ══════════════════════════════════════════════════════════════════════════
#  3. RAGOrchestrator — check_strict_blocks
# ══════════════════════════════════════════════════════════════════════════

class TestRAGOrchestratorStrictBlocks:

    @pytest.fixture
    def rag(self, mock_rag_engine, mock_guard, mock_verifier,
            mock_event_bus, mock_stream_llm):
        return _make_rag(mock_rag_engine, mock_guard, mock_verifier,
                         mock_event_bus, mock_stream_llm)

    @pytest.mark.asyncio
    async def test_check_strict_blocks_normal(self, rag):
        """check_strict_blocks ne bloque pas en mode normal."""
        blocked = await rag.check_strict_blocks(
            query="question normale",
            intent="RAG",
            rag_context="Contexte valide",
            web_context="",
        )
        assert blocked is None

    @pytest.mark.asyncio
    async def test_check_strict_blocks_strict(self, rag):
        """Mode strict + aucune source + mot-clé RAG → blocage."""
        rag.fallback_guard.is_strict = True
        rag.response_guard.is_strict = True

        blocked = await rag.check_strict_blocks(
            query="trouve le fichier machine learning",
            intent="COMPLEX",
            rag_context="",
            web_context="",
        )
        assert blocked is not None
        assert isinstance(blocked, str)


# ══════════════════════════════════════════════════════════════════════════
#  4. LLMGenerator — generate + check_connectivity
# ══════════════════════════════════════════════════════════════════════════

class TestLLMGenerator:

    @pytest.fixture
    def gen(self, mock_stream_llm, mock_event_bus, mock_policy, mock_runtime):
        return LLMGenerator(
            local_llm=mock_stream_llm,
            cloud_llm=mock_stream_llm,
            policy_engine=mock_policy,
            runtime=mock_runtime,
            event_bus=mock_event_bus,
        )

    @pytest.mark.asyncio
    async def test_generate_streaming(self, gen, mock_ctx):
        """Generate produit des tokens."""
        tokens = []
        async for token in gen.generate(
            system_prompt="System",
            full_prompt="Question?",
            query="test",
            intent="SIMPLE",
            ctx=mock_ctx,
        ):
            tokens.append(token)
        assert len(tokens) > 0
        full = "".join(tokens)
        assert "Réponse" in full

    @pytest.mark.asyncio
    async def test_generate_offline(self, gen):
        """Generate fonctionne en offline."""
        gen.cloud_llm.is_online = False
        gen.policy_engine.get = MagicMock(return_value="local")
        gen.policy_engine.should_use_cloud = MagicMock(return_value=False)
        gen.runtime = None
        local = MagicMock()
        local.is_online = True
        local.model_name = "local-model"

        async def _local_stream(*args, **kwargs):
            for token in ["Réponse", " locale", "."]:
                yield token
        local.generate_stream = _local_stream
        gen.local_llm = local

        ctx = MagicMock()
        ctx.is_online = False
        ctx.ram_free_mb = 4096
        ctx.mode = "local"
        ctx.hybrid_strategy = "local"
        ctx.already_fact_checked = False
        ctx.already_retried = False
        ctx.already_fallback = False
        ctx.keywords = None

        tokens = []
        async for token in gen.generate(
            system_prompt="System",
            full_prompt="Question?",
            query="test",
            intent="SIMPLE",
            ctx=ctx,
        ):
            tokens.append(token)
        full = "".join(tokens)
        assert "locale" in full

    @pytest.mark.asyncio
    async def test_check_connectivity_online(self, gen):
        """Connectivity check retourne booléen."""
        result = await gen.check_connectivity()
        assert isinstance(result, bool)


# ══════════════════════════════════════════════════════════════════════════
#  5. RAGOrchestrator — verify_citations
# ══════════════════════════════════════════════════════════════════════════

class TestRAGOrchestratorCitations:

    @pytest.fixture
    def rag(self, mock_rag_engine, mock_guard, mock_verifier,
            mock_event_bus, mock_stream_llm):
        return _make_rag(mock_rag_engine, mock_guard, mock_verifier,
                         mock_event_bus, mock_stream_llm)

    @pytest.mark.asyncio
    async def test_verify_citations_normal(self, rag):
        """verify_citations ne bloque pas une réponse valide."""
        result = await rag.verify_citations(
            intent="RAG",
            rag_context="Contexte avec sources",
            response_content="Réponse valide avec citation.",
            rag_result=RAGResult(),
            query="question de test",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_verify_citations_simple(self, rag):
        """SIMPLE intent → pas de vérif."""
        result = await rag.verify_citations(
            intent="SIMPLE",
            rag_context="",
            response_content="Bonjour",
            rag_result=None,
            query="bonjour",
        )
        assert result is None


# ══════════════════════════════════════════════════════════════════════════
#  6. RAGOrchestrator — retrieve_primary
# ══════════════════════════════════════════════════════════════════════════

class TestRAGOrchestratorRetrievePrimary:

    @pytest.fixture
    def rag(self, mock_rag_engine, mock_guard, mock_verifier,
            mock_event_bus, mock_stream_llm):
        return _make_rag(mock_rag_engine, mock_guard, mock_verifier,
                         mock_event_bus, mock_stream_llm)

    @pytest.mark.asyncio
    async def test_retrieve_primary_rag(self, rag, mock_ctx):
        """retrieve_primary retourne contexte + résultat."""
        rag_context, rag_result = await rag.retrieve_primary(
            query="machine learning", ctx=mock_ctx)
        assert rag_context.strip()
        assert rag_result is not None
        assert hasattr(rag_result, 'confidence_label')
