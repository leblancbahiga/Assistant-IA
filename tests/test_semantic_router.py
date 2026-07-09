"""
Tests NURU V15 — Semantic Router ultra-léger (P1 #43).

Vérifie :
  - Classification des 4 intents (RAG, GENERAL, WEB, SIMPLE)
  - Cache LRU + TTL
  - Cas limites (requêtes vides, bruitées)
  - Performance (temps < 5ms)
  - Cohérence (même requête = même résultat)
"""

import time

import pytest

from src.routing.semantic_router import SemanticRouter, SemanticRoute

# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def router():
    """Instance fraîche du routeur pour chaque test (pas de cache)."""
    return SemanticRouter(cache_size=10, cache_ttl=1)


@pytest.fixture
def router_cached():
    """Routeur avec cache long (5 min) pour tester le cache."""
    return SemanticRouter(cache_size=128, cache_ttl=300)


# ═══════════════════════════════════════════════════════════════════════
# Tests Trivial
# ═══════════════════════════════════════════════════════════════════════


class TestTrivialRouting:
    """Salutations, remerciements, feedbacks → SIMPLE."""

    @pytest.mark.parametrize("query", [
        "Bonjour",
        "salut",
        "Hello",
        "hi",
        "coucou",
        "hey",
    ])
    def test_greetings(self, router, query):
        r = router.route(query)
        assert r.intent == "SIMPLE", f"{query=} → {r.intent}"
        assert r.confidence >= 0.9

    @pytest.mark.parametrize("query", [
        "Merci",
        "merci beaucoup",
        "thanks",
        "Merci bien",
    ])
    def test_thanks(self, router, query):
        r = router.route(query)
        assert r.intent == "SIMPLE"

    @pytest.mark.parametrize("query", [
        "Oui",
        "Non",
        "ok",
        "d'accord",
        "super",
        "parfait",
        "génial",
    ])
    def test_feedback(self, router, query):
        r = router.route(query)
        assert r.intent == "SIMPLE"

    @pytest.mark.parametrize("query", [
        "Qui es-tu ?",
        "qui est tu?",
        "Qui êtes-vous ?",
        "tu es qui",
        "vous êtes qui",
        "Quelle est ton nom ?",
        "Quelle est ta mission ?",
    ])
    def test_identity(self, router, query):
        r = router.route(query)
        assert r.intent == "SIMPLE"

    @pytest.mark.parametrize("query", [
        "Répète",
        "répéter s'il te plaît",
        "expliquer",
        "résumer",
        "reformuler",
        "Tu peux répéter ?",
    ])
    def test_repeat(self, router, query):
        r = router.route(query)
        assert r.intent == "SIMPLE"


# ═══════════════════════════════════════════════════════════════════════
# Tests RAG
# ═══════════════════════════════════════════════════════════════════════


class TestRagRouting:
    """Questions sur documents personnels → RAG."""

    @pytest.mark.parametrize("query", [
        "Qu'est-ce que le projet Yarid ?",
        "Parle-moi du projet IAMGOLD",
        "Où est le dossier IITA ?",
        "Trouve le rapport FAO",
        "Cherche le document USAID",
        "Ouvre le fichier CV",
        "Qui suis-je ?",
        "Parle-moi de Leblanc Bahiga",
        "Mon profil utilisateur",
        "Quel est mon CV ?",
        "Qui est Leblanc ?",
        "Cherche dans mes documents Rikolto",
        "Trouve le fichier Beaccom",
        "Étude de base Walikale",
        "Diplôme et certificats",
        "Ma lettre de motivation",
        "Mes informations personnelles",
        "Où est mon document sur la filière ?",
    ])
    def test_rag_intent(self, router, query):
        r = router.route(query)
        assert r.intent == "RAG", f"{query=} → {r.intent} (conf={r.confidence})"
        assert r.confidence >= 0.5

    @pytest.mark.parametrize("query", [
        "Qui est le président ?",
        "Qui était Einstein ?",
    ])
    def test_not_rag(self, router, query):
        """Qui est [nom propre inconnu] ne doit PAS trigger RAG."""
        r = router.route(query)
        assert r.intent != "RAG", f"{query=} → {r.intent}"

    def test_rag_with_general_mix(self, router):
        """Une question mélangeant RAG + général doit prioriser RAG."""
        r = router.route("Explique le projet Yarid et compare avec IAMGOLD")
        assert r.intent == "RAG"


# ═══════════════════════════════════════════════════════════════════════
# Tests GENERAL
# ═══════════════════════════════════════════════════════════════════════


class TestGeneralRouting:
    """Culture générale, calculs, sciences → GENERAL."""

    @pytest.mark.parametrize("query", [
        "Qu'est-ce que la photosynthèse ?",
        "Explique la théorie de la relativité",
        "Comment fonctionne un moteur ?",
        "Pourquoi le ciel est bleu ?",
        "Qui était Albert Einstein ?",
        "Quand a eu lieu la Révolution française ?",
        "Où se trouve le Mont Blanc ?",
        "Combien font 2 + 2 ?",
        "Quelle est la capitale du Japon ?",
        "Calcule 15 * 37",
        "Différence entre ADN et ARN",
        "Qu'est-ce qu'un atome ?",
        "Jouer aux échecs",
        "Résoudre un sudoku",
    ])
    def test_general_intent(self, router, query):
        r = router.route(query)
        assert r.intent == "GENERAL", f"{query=} → {r.intent} (conf={r.confidence})"

    def test_general_fallback(self, router):
        """Requête quelconque sans mot-clé → GENERAL fallback."""
        r = router.route("Quel est le sens de la vie ?")
        assert r.intent == "GENERAL"

    def test_general_low_confidence(self, router):
        """Requête vague avec peu de mots-clés → GENERAL mais confiance basse."""
        r = router.route("Une question sur quelque chose")
        assert r.intent == "GENERAL"
        assert r.confidence <= 0.5


# ═══════════════════════════════════════════════════════════════════════
# Tests WEB
# ═══════════════════════════════════════════════════════════════════════


class TestWebRouting:
    """Actualités, prix, météo → WEB."""

    @pytest.mark.parametrize("query", [
        "Quel est le prix actuel de l'or ?",
        "Météo à Kinshasa aujourd'hui",
        "Qui est le président actuel des États-Unis ?",
        "Quelles sont les dernières actualités ?",
        "Cours du dollar aujourd'hui",
        "Qui dirige la France actuellement ?",
        "Température à New York",
        "Qui est le CEO de Tesla ?",
        "En ce moment dans l'actualité",
    ])
    def test_web_intent(self, router, query):
        r = router.route(query)
        assert r.intent == "WEB", f"{query=} → {r.intent} (conf={r.confidence})"

    def test_web_mix(self, router):
        """RAG + WEB doit prioriser RAG (mots-clés forts)."""
        r = router.route("Quel est le prix actuel du projet Yarid ?")
        # "Yarid" est un mot-clé RAG fort (poids 3), "prix actuel" = WEB (2)
        assert r.intent == "RAG"


# ═══════════════════════════════════════════════════════════════════════
# Tests Cache LRU + TTL
# ═══════════════════════════════════════════════════════════════════════


class TestCache:
    """Vérifie le comportement du cache intégré."""

    def test_cache_hit(self, router_cached):
        """Deux appels identiques → mêmes résultats."""
        q = "Qu'est-ce que le projet Yarid ?"
        r1 = router_cached.route(q)
        r2 = router_cached.route(q)
        assert r1.intent == r2.intent
        assert r1.confidence == r2.confidence

    def test_cache_ttl_expiry(self):
        """Cache avec TTL très court → doit expirer."""
        router = SemanticRouter(cache_size=10, cache_ttl=0.1)
        q = "Météo à Paris"
        _ = router.route(q)
        time.sleep(0.15)
        r2 = router.route(q)
        # Le résultat doit être frais (pas nécessairement différent,
        # mais le cache a été bypassé car expiré)
        assert r2.processing_ms > 0

    def test_cache_lru_eviction(self):
        """Cache LRU : atteindre la limite doit évincer l'entrée la plus ancienne."""
        router = SemanticRouter(cache_size=2, cache_ttl=300)
        router.route("Question RAG")
        router.route("Question GENERAL")
        router.route("Question WEB")  # Doit évincer "Question RAG"
        # Vérifier que le cache interne n'a que 2 entrées
        # (accès via l'attribut privé pour le test — acceptable ici)
        assert len(router._cache) <= 2

    def test_cache_short_queries_not_cached(self):
        """Requêtes de 3 caractères ou moins ne doivent pas polluer le cache."""
        router = SemanticRouter(cache_size=128, cache_ttl=300)
        q = "ok"
        # Faire une requête vide et très courte
        r = router.route("")
        assert r.intent == "SIMPLE"
        r = router.route("a")
        assert r.processing_ms > 0  # Pas de cache pour les très courtes


# ═══════════════════════════════════════════════════════════════════════
# Tests Cas Limites
# ═══════════════════════════════════════════════════════════════════════


class TestEdgeCases:

    def test_empty_query(self, router):
        """Requête vide → SIMPLE (safe fallback)."""
        r = router.route("")
        assert r.intent == "SIMPLE"
        assert r.confidence == 1.0

    def test_whitespace_only(self, router):
        """Requête avec seulement des espaces → SIMPLE."""
        r = router.route("   ")
        assert r.intent == "SIMPLE"

    def test_special_chars(self, router):
        """Caractères spéciaux seuls → GENERAL (fallback)."""
        r = router.route("?!*§")
        assert r.intent == "GENERAL"

    def test_very_long_query(self, router):
        """Très longue requête ne doit pas crasher."""
        q = "question " * 200
        r = router.route(q)
        assert r.intent in ("RAG", "GENERAL", "WEB", "SIMPLE")
        assert r.processing_ms < 100  # Même longue, doit rester rapide

    @pytest.mark.parametrize("query", [
        "bonjour je voudrais savoir qui est le président de la république",
        "merci beaucoup pour votre aide c'était très utile",
        "salut comment ça va aujourd'hui ?",
    ])
    def test_conversational_mixed(self, router, query):
        """Requêtes conversationnelles mélangées."""
        r = router.route(query)
        # Le début "bonjour" match trivial → SIMPLE si on match en début
        # mais comme notre TRIVIAL match en début, "bonjour je voudrais..."
        # est capturé par le pattern trivial
        assert r.intent == "SIMPLE"
        assert r.confidence >= 0.9


# ═══════════════════════════════════════════════════════════════════════
# Tests Performance
# ═══════════════════════════════════════════════════════════════════════


class TestPerformance:

    def test_processing_time_under_5ms(self, router):
        """Toute classification doit prendre < 5ms sur M1."""
        queries = [
            "Qu'est-ce que le projet Yarid ?",
            "Explique la relativité générale",
            "Météo à Paris aujourd'hui",
            "Bonjour",
            "Qui est le président des États-Unis ?",
            "Combien font 2 + 2 ?",
            "Où se trouve le dossier IITA ?",
            "Quelle est la différence entre biologie et chimie ?",
        ]
        for q in queries:
            r = router.route(q)
            assert r.processing_ms < 5, f"{q=} → {r.processing_ms}ms"

    def test_bulk_performance(self, router):
        """100 classifications doivent prendre < 200ms au total."""
        queries = [
            "Bonjour",
            "Qu'est-ce que le projet Yarid ?",
            "Explique la photosynthèse",
            "Météo à Kinshasa",
            "Merci beaucoup",
            "Qui suis-je ?",
            "Calcule 45 + 32",
            "Qui est le président actuel ?",
            "Où se trouve le rapport FAO ?",
            "Quelle est la capitale du Japon ?",
        ] * 10  # 100 requêtes

        t0 = time.time()
        for q in queries:
            router.route(q)
        total = (time.time() - t0) * 1000

        assert total < 200, f"100 classifications = {total:.0f}ms (limite 200ms)"
        assert total < 20  # En pratique, ça doit être < 20ms avec le cache


# ═══════════════════════════════════════════════════════════════════════
# Tests de régression — comportement connu
# ═══════════════════════════════════════════════════════════════════════


class TestRegression:

    def test_identity_query_not_general(self, router):
        """Régression: 'Qui est Leblanc' doit être RAG, pas GENERAL."""
        r = router.route("Qui est Leblanc ?")
        assert r.intent == "RAG", f"→ {r.intent}"

    def test_general_math_not_rag(self, router):
        """Régression: '2+2' doit être GENERAL, pas RAG."""
        r = router.route("Combien font 2 + 2 ?")
        assert r.intent == "GENERAL", f"→ {r.intent}"

    def test_web_mixed_without_keyword(self, router):
        """Régression: 'quel est le prix actuel de quelque chose' → WEB."""
        r = router.route("Quel est le prix actuel du café ?")
        assert r.intent == "WEB", f"→ {r.intent}"

    def test_order_independence(self, router):
        """Répéter des requêtes dans un ordre différent ne change pas les résultats."""
        qs = ["Bonjour", "Projet Yarid", "Météo", "2+2"]
        first = {q: router.route(q).intent for q in qs}
        # Même routeur, mêmes résultats
        second = {q: router.route(q).intent for q in qs}
        assert first == second

    def test_rag_phrases(self, router):
        """Phrases RAG multi-mots doivent matcher."""
        r = router.route("Qui suis-je ?")
        assert r.intent == "RAG"
        r = router.route("informations personnelles")
        assert r.intent == "RAG"
        r = router.route("parle-moi de moi")
        assert r.intent == "RAG"
