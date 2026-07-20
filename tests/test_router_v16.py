"""Tests unitaires — Router V16.

Couvre : fast rules, scoring, overrides (temporel, possessif, identité),
contexte, multi-routing, cache, non-régression sur les bugs signalés.
"""
import os
import sys

# Ajouter le projet au path pour les imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.routing.v16.router_v16 import RouterV16


def fresh_router():
    return RouterV16()


def test_fao_temporal_bug_fixed():
    """LE bug signalé : mot-clé RAG + marqueur temporel → doit gagner WEB."""
    r = fresh_router()
    d = r.route("Que fait actuellement la FAO ?")
    assert d.intent == "WEB", d.reasoning


def test_fao_without_temporal_stays_rag():
    r = fresh_router()
    d = r.route("Parle-moi de mon expérience à la FAO")
    assert d.intent == "RAG", d.reasoning


def test_photosynthese_general_without_possessive():
    r = fresh_router()
    d = r.route("Explique la photosynthèse")
    assert d.intent == "GENERAL", d.reasoning


def test_photosynthese_rag_with_possessive():
    r = fresh_router()
    d = r.route("Explique la photosynthèse dans mon rapport")
    assert d.intent == "RAG", d.reasoning


def test_trivial_greeting():
    r = fresh_router()
    d = r.route("Bonjour !")
    assert d.intent == "SIMPLE"


def test_identity_of_bot_is_simple():
    r = fresh_router()
    d = r.route("Qui es-tu ?")
    assert d.intent == "SIMPLE"


def test_identity_of_user_is_rag():
    r = fresh_router()
    d = r.route("Qui suis-je ?")
    assert d.intent == "RAG", d.reasoning


def test_identity_proper_noun_is_rag():
    r = fresh_router()
    d = r.route("Qui est Leblanc ?")
    assert d.intent == "RAG", d.reasoning


def test_web_meteo():
    r = fresh_router()
    d = r.route("Quelle est la météo aujourd'hui ?")
    assert d.intent == "WEB"


def test_web_president_actuel():
    r = fresh_router()
    d = r.route("Qui est l'actuel président des États-Unis ?")
    assert d.intent == "WEB", d.reasoning


def test_context_anaphora_inherits_rag():
    r = fresh_router()
    d1 = r.route("Ouvre mon rapport annuel")
    assert d1.intent == "RAG"
    d2 = r.route("Résume-le.")
    assert d2.intent == "RAG", d2.reasoning


def test_multi_route_cv_vs_offer():
    r = fresh_router()
    d = r.route("Compare mon CV avec cette offre d'emploi.")
    assert d.plan is not None, d.reasoning
    assert set(d.plan.steps[:2]) == {"RAG", "WEB"}


def test_cache_hit_is_fast_and_consistent():
    r = fresh_router()
    d1 = r.route("Quel est le prix du riz aujourd'hui ?")
    d2 = r.route("Quel est le prix du riz aujourd'hui ?")
    assert d2.from_cache is True
    assert d1.intent == d2.intent == "WEB"


def test_cache_respects_context_change():
    """Même texte, contexte documentaire différent → ne doit PAS halluciner
    un hit de cache erroné (protection contre le bug latent identifié)."""
    r = fresh_router()
    r.route("Ouvre mon rapport annuel")
    d1 = r.route("Résume-le.")
    # Simule un changement de document ouvert
    r._conversation.last_document_ref = "cv"
    r._conversation.turns_since_document = 0
    d2 = r.route("Résume-le.")
    assert d1.intent == "RAG" and d2.intent == "RAG"


def test_simple_calculation_is_general():
    r = fresh_router()
    d = r.route("Combien font 12 fois 7 ?")
    assert d.intent == "GENERAL", d.reasoning


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
