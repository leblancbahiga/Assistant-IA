"""Tests unitaires pour ArchonRefiner (auto‑correction post‑génération)."""
from __future__ import annotations

import pytest

from src.ai.archon_refiner import ArchonRefiner


@pytest.fixture
def refiner():
    return ArchonRefiner(enabled=True)


class TestShouldRefine:
    """Décision de raffinement."""

    def test_refine_court_circuit_court(self, refiner):
        """Réponse trop courte → pas de raffinement."""
        assert refiner._should_refine("Oui.", "", 0.9, "SIMPLE") is False

    def test_refine_court_circuit_pas_contexte(self, refiner):
        """Pas de contexte RAG → pas de raffinement."""
        assert refiner._should_refine("Réponse longue de plus de cinquante caractères pour ce test...", "", 0.9, "SIMPLE") is False

    def test_refine_rag_toujours(self, refiner):
        """Intent RAG avec score ≥ min → vérifie quand même."""
        assert refiner._should_refine("Réponse longue de plus de cinquante caractères pour ce test...", "contexte", 0.8, "RAG") is True

    def test_refine_complexe_toujours(self, refiner):
        """Intent COMPLEX avec score ≥ min → vérifie quand même."""
        assert refiner._should_refine("Réponse complexe dépassant cinquante caractères pour valider le test...", "contexte web", 0.7, "COMPLEX") is True

    def test_refine_score_bas_declenche(self, refiner):
        """Score RAG bas → vérification même pour RAG."""
        assert refiner._should_refine("Réponse avec contexte de plus de cinquante caractères pour ce test...", "contexte", 0.3, "RAG") is True

    def test_refine_simple_non_rag(self, refiner):
        """Intent SIMPLE, pas de contexte → pas de raffinement."""
        assert refiner._should_refine("Simple question sans document de plus de cinquante caractères...", "", 0.9, "SIMPLE") is False


@pytest.mark.asyncio
async def test_refine_pas_de_llm_retourne_original():
    """Pas de LLM configuré → réponse originale inchangée."""
    r = ArchonRefiner(enabled=True)
    result = await r.refine("Réponse de plus de cinquante caractères pour déclencher le traitement...", "contexte test", 0.7, "RAG")
    assert result == "Réponse de plus de cinquante caractères pour déclencher le traitement..."


@pytest.mark.asyncio
async def test_refine_stats_errors():
    """Pas de LLM → stats à zéro (pas de run réel)."""
    r = ArchonRefiner(enabled=True)
    await r.refine("Réponse de plus de cinquante caractères pour déclencher le traitement...", "ctx", 0.7, "RAG")
    stats = r.stats
    # Stats restent à 0 car aucun LLM disponible pour exécuter le raffinement
    assert stats["runs"] == 0
    assert stats["corrected"] == 0
    assert stats["errors"] == 0


@pytest.mark.asyncio
async def test_stats_compteur():
    """Pas de LLM → compteurs restent à zéro."""
    r = ArchonRefiner(enabled=True)
    await r.refine("Réponse un de plus de cinquante caractères pour déclencher le traitement...", "ctx", 0.8, "RAG")
    await r.refine("Réponse deux de plus de cinquante caractères pour déclencher le traitement...", "ctx", 0.8, "RAG")
    await r.refine("Réponse trois de plus de cinquante caractères pour déclencher le traitement...", "ctx", 0.8, "RAG")
    # 0 runs : pas de LLM disponible pour exécuter le raffinement
    assert r.stats["runs"] == 0
    assert r.stats["corrected"] == 0


@pytest.mark.asyncio
async def test_refine_disabled():
    """Archon désactivé → réponse retournée sans traitement."""
    r = ArchonRefiner(enabled=False)
    result = await r.refine("Test désactivé", "contexte", 0.5, "RAG")
    assert result == "Test désactivé"
    assert r.stats["runs"] == 0
