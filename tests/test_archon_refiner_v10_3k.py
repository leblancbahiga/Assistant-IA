"""Tests B-Archon : ArchonRefiner doit appeler correctement le LLM.

Bug original V10.3 : ArchonRefiner appelle llm.generate(system=..., prompt=..., ...)
mais CloudLLM.generate(prompt, timeout, model) n'accepte pas ces kwargs.

Le fix doit produire un appel correct vers generate_stream() avec system_prompt.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock


class _FakeStreamingLLM:
    """Mock du LLM qui expose generate_stream avec signature async-iter."""
    def __init__(self, tokens=("Réponse", " corrigée", " OK")):
        self._tokens = list(tokens)
        self.calls = []

    async def generate_stream(self, prompt, intent="SIMPLE",
                              system_prompt=None, temperature=0.7):
        self.calls.append({
            "prompt": prompt,
            "intent": intent,
            "system_prompt": system_prompt,
            "temperature": temperature,
        })
        for t in self._tokens:
            yield t


def _fake_rag_context():
    return "Le projet BEACCOM est situé à Goma. RDC. Agriculture vivrière."


def test_archon_refiner_calls_generate_stream_not_generate():
    from src.ai.archon_refiner import ArchonRefiner

    # Le refiner détecte "[Corrigé]" en début de réponse et retourne
    # la version corrigée (sans préfixe). On mock donc ce protocole.
    fake_llm = _FakeStreamingLLM(tokens=("[Corrigé]", " Le projet est à Goma."))
    refiner = ArchonRefiner(cloud_llm=fake_llm, min_confidence=0.6)

    # Réponse > 50 chars pour passer le court-circuit _should_refine (len < 50)
    response = (
        "Le projet BEACCOM est situé à Kinshasa, en République Démocratique du Congo, "
        "et concerne un programme d'agriculture vivrière durable pour la saison 2024-2025."
    )
    assert len(response) > 50, "Test setup: réponse doit dépasser 50 chars"
    refined = await_with_event_loop(
        refiner.refine(response, _fake_rag_context(),
                       rag_score=0.85, intent="RAG")
    )

    # Le fix doit utiliser generate_stream, pas generate
    assert len(fake_llm.calls) == 1, f"Attendu 1 appel, vu {len(fake_llm.calls)}"
    call = fake_llm.calls[0]
    # system_prompt doit être passé
    assert call["system_prompt"] is not None
    assert "relecteur" in call["system_prompt"].lower() or "vérifier" in call["system_prompt"].lower()
    # prompt doit contenir contexte ET réponse originale
    assert "BEACCOM" in call["prompt"]
    assert "Kinshasa" in call["prompt"]
    # Le résultat doit être la réponse strippée du préfixe
    assert refined == "Le projet est à Goma."
    # BM stats doivent refléter la correction
    assert refiner.stats["corrected"] == 1


def test_archon_refiner_returns_original_if_no_correction_prefix():
    """Le refiner retourne l'original si le LLM ne dit pas '[Corrigé]'."""
    from src.ai.archon_refiner import ArchonRefiner
    fake_llm = _FakeStreamingLLM(tokens=("Pas de correction nécessaire.",))
    refiner = ArchonRefiner(cloud_llm=fake_llm)
    response = (
        "Le projet BEACCOM est situé à Kinshasa, en République Démocratique du Congo, "
        "et concerne un programme d'agriculture vivrière durable pour la saison 2024-2025."
    )
    refined = await_with_event_loop(
        refiner.refine(response, _fake_rag_context(), rag_score=0.85, intent="RAG")
    )
    assert refined == response  # réponse inchangée
    assert refiner.stats["corrected"] == 0


def test_archon_refiner_disabled_returns_original():
    from src.ai.archon_refiner import ArchonRefiner
    fake_llm = _FakeStreamingLLM()
    refiner = ArchonRefiner(cloud_llm=fake_llm, enabled=False)
    response = "Original"
    refined = await_with_event_loop(
        refiner.refine(response, _fake_rag_context(), rag_score=0.9, intent="RAG")
    )
    assert refined == "Original", "Si désactivé, retourne l'original"
    assert fake_llm.calls == [], "Aucun appel LLM ne doit être fait"


def test_archon_refiner_intent_simple_bypasses():
    from src.ai.archon_refiner import ArchonRefiner
    fake_llm = _FakeStreamingLLM()
    refiner = ArchonRefiner(cloud_llm=fake_llm)
    refined = await_with_event_loop(
        refiner.refine("Bonjour", _fake_rag_context(), rag_score=0.9, intent="SIMPLE")
    )
    assert refined == "Bonjour"
    assert fake_llm.calls == [], "intent=SIMPLE doit court-circuiter"


def test_archon_refiner_gracefully_handles_no_llm():
    from src.ai.archon_refiner import ArchonRefiner
    refiner = ArchonRefiner(cloud_llm=None, local_llm=None)
    refined = await_with_event_loop(
        refiner.refine("Texte", _fake_rag_context(), rag_score=0.9, intent="RAG")
    )
    assert refined == "Texte"


def test_archon_refiner_does_not_crash_on_generate_kwargs():
    """Le bug original plantait avec : got an unexpected keyword argument 'system'.

    Avec le fix, le call generate_stream doit passer sans erreur.
    """
    from src.ai.archon_refiner import ArchonRefiner
    fake_llm = _FakeStreamingLLM(tokens=("OK",))
    refiner = ArchonRefiner(cloud_llm=fake_llm)
    long_response = "X" * 200  # > 50 chars pour passer _should_refine
    # Avant le fix : TypeError sur generate(system=...)
    refined = await_with_event_loop(
        refiner.refine(long_response, _fake_rag_context(), rag_score=0.9, intent="RAG")
    )
    # Le LLM a répondu "OK" sans préfixe [Corrigé] → retourne l'original
    assert refined == long_response


# ── Helper pour exécuter async dans les tests ────────────────────────────
import asyncio

def await_with_event_loop(coro):
    """Helper pour pytest-sync : exécute une coroutine via asyncio.run."""
    return asyncio.run(coro)
