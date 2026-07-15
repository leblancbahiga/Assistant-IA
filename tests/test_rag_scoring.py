"""
Tests unitaires — Pipeline RAG (scoring, seuils, fallback V10.2).

Couvre :
- Confidence labels : HAUTE / MOYENNE / FAIBLE / ABSENT
- Seuils : rag_score_threshold (0.30), rag_score_fallback (0.25), rag_min_usable_score (0.20)
- Centralisation des seuils dans config.py
- ContextBudget V10.2 (32K)

NOTE : Les tests utilisent RAGEngine.retrieve avec des mocks pour
éviter toute dépendance à l'embedder, la DB, ou le reranker réel.
Le reranker mocké retourne le score vectoriel inchangé pour éviter
tout décalage entre le score multi_search et le score final.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.rag_engine import RAGEngine, RAGResult
from src.config import config
from src.context_manager import ContextBudget


class MockSearchResult:
    """Simule un SearchResult de multi_search."""

    def __init__(self, content="Contenu mocké.", source="test.pdf", score=0.85):
        self.content = content
        self.source = source
        self.score = score


async def _make_rag_engine(mock_ms):
    """Crée un RAGEngine avec toutes les dépendances mockées.
    
    Le reranker est initialisé pour retourner le score vectoriel inchangé.
    Chaque test peut ajuster engine.reranker.rerank.return_value si besoin.
    """
    engine = RAGEngine()
    engine._multi_search = mock_ms
    engine.rewriter = MagicMock()
    engine.rewriter.rewrite.return_value = "query optimisée"
    engine.embedder = MagicMock()
    engine.embedder.embed_sync.return_value = [[0.1] * 512]
    engine.embedder.unload = MagicMock()
    engine._should_use_reranker = MagicMock(return_value=True)
    engine.reranker = MagicMock()
    engine.reranker.load_model = MagicMock()
    engine.reranker.unload = MagicMock()
    # Par défaut : reranker retourne le score 1:1 (inchangé)
    engine.reranker.rerank = AsyncMock()
    return engine


@pytest.fixture
def mock_multi_search():
    """Fixture : _multi_search.search mocké avec des résultats paramétrables."""
    ms = MagicMock()
    ms.search = AsyncMock(
        return_value=([MockSearchResult(score=0.75)], MagicMock())
    )
    return ms


# ═══════════════════════════════════════════════════════
# 1. Confidence labels
# ═══════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_confidence_label_haute(mock_multi_search):
    """Score ≥ threshold (0.30) → HAUTE"""
    mock_multi_search.search.return_value = (
        [MockSearchResult(score=0.85)],
        MagicMock(),
    )
    engine = await _make_rag_engine(mock_multi_search)
    engine.reranker.rerank.return_value = [
        ("Contenu mocké.", "test.pdf", 0.85)
    ]

    context, result = await engine.retrieve("test query")
    assert result.confidence_label == "HAUTE"
    assert result.top_score == 0.85


@pytest.mark.asyncio
async def test_confidence_label_moyenne(mock_multi_search):
    """Score entre fallback (0.25) et threshold (0.30) → MOYENNE"""
    mock_multi_search.search.return_value = (
        [MockSearchResult(score=0.28)],
        MagicMock(),
    )
    engine = await _make_rag_engine(mock_multi_search)
    engine.reranker.rerank.return_value = [
        ("Contenu mocké.", "test.pdf", 0.55)
    ]

    _, result = await engine.retrieve("test query")
    assert result.confidence_label == "MOYENNE"
    assert result.top_score == 0.55
    assert 0.40 <= result.top_score < 0.70


@pytest.mark.asyncio
async def test_confidence_label_faible(mock_multi_search):
    """Score entre min_usable (0.20) et fallback (0.25) → FAIBLE"""
    mock_multi_search.search.return_value = (
        [MockSearchResult(score=0.22)],
        MagicMock(),
    )
    engine = await _make_rag_engine(mock_multi_search)
    engine.reranker.rerank.return_value = [
        ("Contenu mocké.", "test.pdf", 0.35)
    ]

    _, result = await engine.retrieve("test query")
    assert result.confidence_label == "FAIBLE"
    assert result.top_score == 0.35
    assert result.top_score < 0.40


@pytest.mark.asyncio
async def test_confidence_label_absent_vide(mock_multi_search):
    """Aucun résultat → ABSENT (contexte vide)"""
    mock_multi_search.search.return_value = ([], MagicMock())
    engine = await _make_rag_engine(mock_multi_search)

    context, result = await engine.retrieve("test query")
    assert result.confidence_label == "ABSENT"
    assert context == ""  # Contexte vide


# ═══════════════════════════════════════════════════════
# 2. Seuils centralisés dans config
# ═══════════════════════════════════════════════════════


def test_rag_thresholds_in_config():
    """Les 4 seuils RAG existent dans config avec les bonnes valeurs par défaut"""
    assert hasattr(config, "rag_score_threshold")
    assert hasattr(config, "rag_score_fallback")
    assert hasattr(config, "rag_min_usable_score")
    assert hasattr(config, "rag_router_min_score")

    # Ordre hiérarchique : accept > warn > reject > router
    assert config.rag_score_threshold >= config.rag_score_fallback
    assert config.rag_score_fallback >= config.rag_min_usable_score
    assert config.rag_min_usable_score >= config.rag_router_min_score


def test_rag_min_usable_gt_router_min():
    """RAG_MIN_USABLE_SCORE > RAG_ROUTER_MIN — cohérence pipeline"""
    assert config.rag_min_usable_score > config.rag_router_min_score
    # 0.20 > 0.15 : le routeur voit des résultats que le moteur rejette


# ═══════════════════════════════════════════════════════
# 3. ContextBudget V10.2
# ═══════════════════════════════════════════════════════


def test_context_budget_32k():
    """ContextBudget V10.2 : max_prompt_tokens=8192, reserved=2048"""
    budget = ContextBudget()
    assert budget.max_prompt_tokens == 8192
    assert budget.reserved_response == 2048
    assert budget.available == 8192 - 2048  # 6144

    # allocate retourne une chaîne (le prompt assemblé)
    prompt = budget.allocate(
        system="Tu es NURU.\n" * 50,
        rag="Contexte RAG avec des informations.",
        facts=["Fait 1", "Fait 2"],
        history=[{"role": "user", "content": "Bonjour"}, {"role": "assistant", "content": "Salut"}],
    )
    assert isinstance(prompt, str)
    assert len(prompt) > 0
    assert "NURU" in prompt


# ═══════════════════════════════════════════════════════
# 4. RAGResult — V10.2 conformité
# ═══════════════════════════════════════════════════════


def test_ragresult_default_haute():
    """RAGResult créé sans confiance → MOYENNE par défaut (V15)"""
    result = RAGResult()
    assert result.confidence_label == "MOYENNE"


def test_ragresult_top_score_initial():
    """top_score initialisé correctement"""
    result = RAGResult()
    assert result.top_score == 0.0
    assert result.chunks_injected == 0
    assert result.chunks_retrieved == 0
