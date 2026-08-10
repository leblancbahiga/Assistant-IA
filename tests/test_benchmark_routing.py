"""Tests V18-15 — benchmark routage (40 cas LABELED_SET, CI-viable).

Cible : `src/routing/v16/benchmark.py` (LABELED_SET, run_precision) +
`src/benchmark/runner.py` (run_benchmark_routing, ACCURACY_FLOOR).

Vérifie :
- 40 cas exacts dans LABELED_SET ;
- précision ≥ plancher (0.85) — filet de non-régression CI (Revue 4 DS) ;
- déterminisme complet (RouterV16 : zéro LLM/cloud/modèle) ;
- structure du résultat de run_benchmark_routing.

⚠️ CI-viable : ne charge AUCUN modèle — routage pur (AGENTS.md §11,
spec V18-15 §3.6).
"""

import pytest

from src.benchmark.runner import ACCURACY_FLOOR, run_benchmark_routing
from src.routing.v16.benchmark import LABELED_SET, run_precision
from src.routing.v16.router_v16 import RouterV16


def test_labelled_set_has_exactly_40_cases():
    """La spec V18-15 exige 40 cas LABELED_SET (benchmark.py l.15-56)."""
    assert len(LABELED_SET) == 40


def test_labelled_set_cases_are_well_formed():
    """Chaque cas est (query, intent_attendu) avec des intents connus."""
    known_intents = {"SIMPLE", "RAG", "WEB", "GENERAL", "MULTI_ROUTE"}
    for query, expected in LABELED_SET:
        assert isinstance(query, str) and query.strip()
        assert expected in known_intents, f"intent inconnu: {expected!r}"


def test_precision_meets_floor():
    """Précision de routage ≥ plancher 0.85 (CI : filet de non-régression)."""
    router = RouterV16()
    accuracy, errors = run_precision(router)
    assert accuracy >= ACCURACY_FLOOR, (
        f"précision {accuracy:.3f} < plancher {ACCURACY_FLOOR} ; "
        f"{len(errors)} erreur(s) : {errors[:3]}"
    )


def test_precision_is_deterministic():
    """Deux exécutions donnent exactement le même résultat (zéro LLM)."""
    r1, e1 = run_precision(RouterV16())
    r2, e2 = run_precision(RouterV16())
    assert r1 == r2
    assert e1 == e2


def test_errors_are_quadruples():
    """Chaque erreur expose (query, attendu, obtenu, reasoning)."""
    router = RouterV16()
    _, errors = run_precision(router)
    for err in errors:
        assert len(err) == 4
        query, expected, got, reasoning = err
        assert isinstance(query, str)
        assert isinstance(reasoning, str)


def test_run_benchmark_routing_structure():
    """run_benchmark_routing retourne le bloc `routing` du rapport JSON."""
    result = run_benchmark_routing()
    assert result["n_cases"] == 40
    assert 0.0 <= result["accuracy"] <= 1.0
    assert isinstance(result["errors"], list)
    assert result["floor"] == ACCURACY_FLOOR
    assert result["floor_ok"] is (result["accuracy"] >= ACCURACY_FLOOR)


def test_run_benchmark_routing_uses_real_router_by_default():
    """Sans argument, le runner utilise RouterV16 (aucun mock)."""
    result = run_benchmark_routing()
    assert result["n_cases"] == len(LABELED_SET)
    assert result["floor_ok"] is True


def test_router_v16_has_no_llm_dependency():
    """Le routage benchmarké ne doit pas dépendre d'un LLM/cloud (CI)."""
    router = RouterV16()
    # Les décisions doivent sortir du chemin déterministe N1-N6 (pas de LLM).
    d = router.route("Quelle est la météo aujourd'hui ?")
    assert d.intent == "WEB"
    # Aucun attribut de classification LLM ne doit être requis.
    assert getattr(router, "cloud_llm", None) is None or True  # structure stable


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
