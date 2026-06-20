"""Tests unitaires pour le Router — 20 tests pytest-asyncio.

Couvre : patterns triviaux, connaissances générales, documents,
identité, web, cache, classification LLM, Spotlight, fallback,
HybridStrategy, et escalade RAM via route_with_context.
"""
import pytest

from src.routing.router import HybridStrategy
from src.core.query_context import QueryContext


# ═══════════════════════════════════════════════════════════════════════
# 1-3. Triviaux — regex instantanés (Passe 1)
# ═══════════════════════════════════════════════════════════════════════

class TestTrivialPatterns:
    """Salutations, remerciements, identité → SIMPLE confidence=1.0."""

    @pytest.mark.asyncio
    async def test_trivial_bonjour(self, router_instance):
        """'bonjour' → SIMPLE, confidence=1.0"""
        result = await router_instance.route("bonjour")
        assert result.decision == "SIMPLE"
        assert result.confidence == 1.0
        assert "Trivial" in result.reasoning

    @pytest.mark.asyncio
    async def test_trivial_merci(self, router_instance):
        """'merci' → SIMPLE"""
        result = await router_instance.route("merci")
        assert result.decision == "SIMPLE"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_trivial_qui_es_tu(self, router_instance):
        """'qui es-tu' → SIMPLE"""
        result = await router_instance.route("qui es-tu")
        assert result.decision == "SIMPLE"
        assert result.confidence == 1.0


# ═══════════════════════════════════════════════════════════════════════
# 4-5. Connaissances générales (Passe 1 — §7.1)
# ═══════════════════════════════════════════════════════════════════════

class TestGeneralKnowledgePatterns:
    """Patterns de connaissance générale → GENERAL_KNOWLEDGE."""

    @pytest.mark.asyncio
    async def test_pattern_connaissance_generale(self, router_instance):
        """'explique la photosynthèse' → GENERAL_KNOWLEDGE (confidence 0.9)."""
        result = await router_instance.route("explique la photosynthèse")
        assert result.decision == "GENERAL_KNOWLEDGE"
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_pattern_calcul(self, router_instance):
        """'combien font 2+2' → GENERAL_KNOWLEDGE."""
        result = await router_instance.route("combien font 2+2")
        assert result.decision == "GENERAL_KNOWLEDGE"
        assert result.confidence == 0.9


# ═══════════════════════════════════════════════════════════════════════
# 6-9. Documents / Identité
# ═══════════════════════════════════════════════════════════════════════

class TestDocumentPatterns:
    """Mots-clés documentaires et détection de nom propre → DOCUMENT_KEYWORD."""

    @pytest.mark.asyncio
    async def test_pattern_document_keyword(self, router_instance):
        """'parle de mon cv' → DOCUMENT_KEYWORD."""
        result = await router_instance.route("parle de mon cv")
        assert result.decision == "DOCUMENT_KEYWORD"
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_pattern_document_keyword_cv(self, router_instance):
        """'trouve mon curriculum vitae' → DOCUMENT_KEYWORD."""
        result = await router_instance.route("trouve mon curriculum vitae")
        assert result.decision == "DOCUMENT_KEYWORD"
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_pattern_identity_query(self, router_instance):
        """'Qui est Leblanc' → DOCUMENT_KEYWORD (nom propre détecté via capitalisation)."""
        result = await router_instance.route("Qui est Leblanc")
        assert result.decision == "DOCUMENT_KEYWORD"
        assert result.confidence == 0.9
        assert "identity" in result.reasoning

    @pytest.mark.asyncio
    async def test_pattern_identity_query_lowercase(self, router_instance):
        """'qui est marie' tout en minuscule — le nom n'est pas capitalisé,
        la détection identité ne se déclenche pas. Passe par LLM classification
        (mock retourne 'general') → GENERAL_KNOWLEDGE ou fallback."""
        # Spotlight peut interférer sur macOS → le désactiver
        router_instance._spotlight = None

        result = await router_instance.route("qui est marie")
        # Le nom propre n'étant pas capitalisé, is_identity_query = False.
        # Aucun pattern exact ne matche, on tombe dans LLM classif.
        # Le mock_cloud_llm retourne 'general' → GENERAL_KNOWLEDGE.
        assert result.decision in ("GENERAL_KNOWLEDGE", "CLOUD_GROQ")


# ═══════════════════════════════════════════════════════════════════════
# 10-11. Web (Passe 1 — §7.1)
# ═══════════════════════════════════════════════════════════════════════

class TestWebPatterns:
    """Patterns web → CLOUD_GROQ confidence 0.8."""

    @pytest.mark.asyncio
    async def test_pattern_web_actualite(self, router_instance):
        """'quelle est l'actualité aujourd'hui' → CLOUD_GROQ."""
        result = await router_instance.route("quelle est l'actualité aujourd'hui")
        assert result.decision == "CLOUD_GROQ"
        assert result.confidence == 0.8

    @pytest.mark.asyncio
    async def test_pattern_web_prix(self, router_instance):
        """'prix actuel du bitcoin' → CLOUD_GROQ.
        (Le pattern attend 'prix actuel' ou 'prix du jour')."""
        result = await router_instance.route("prix actuel du bitcoin")
        assert result.decision == "CLOUD_GROQ"
        assert result.confidence == 0.8


# ═══════════════════════════════════════════════════════════════════════
# 12. Cache hit
# ═══════════════════════════════════════════════════════════════════════

class TestCache:
    """Le cache TTL évite le re-routage complet pour des requêtes identiques."""

    @pytest.mark.asyncio
    async def test_cache_hit(self, router_instance):
        """Deux appels identiques : le second est en cache donc plus rapide
        et ne refait pas la logique de routage."""
        query = "explique la photosynthèse"

        result1 = await router_instance.route(query)
        result2 = await router_instance.route(query)

        assert result1.decision == result2.decision
        # Le cache retourne la MÊME instance (pas une copie)
        # → vérification fiable que le cache a servi le résultat
        assert result1 is result2
        # Le temps de la seconde requête est microscopique (cache hit)
        assert result2.processing_time_ms < 5.0


# ═══════════════════════════════════════════════════════════════════════
# 13-15. Classification LLM (Passe 2 — cas ambigus)
# ═══════════════════════════════════════════════════════════════════════

class TestLlmClassification:
    """Passe 2 — classification LLM pour les requêtes qui n'ont matché
    aucun pattern de la Passe 1."""

    @pytest.mark.asyncio
    async def test_llm_classification(self, router_instance, mock_cloud_llm):
        """Quand cloud_llm est disponible et online, le LLM classifie
        une requête ambiguë. Mock de generate_stream → 'general'."""
        async def _stream_general(*args, **kwargs):
            yield "general"

        mock_cloud_llm.generate_stream = _stream_general

        result = await router_instance.route("dis moi quelque chose")
        # LLM classifie 'general' → GENERAL_KNOWLEDGE
        assert result.decision == "GENERAL_KNOWLEDGE"

    @pytest.mark.asyncio
    async def test_llm_classification_offline(self, router_instance_offline):
        """Sans connexion : is_online() = False → le bloc LLM est sauté.
        Pas de pattern, pas de LLM → clarification."""
        # Spotlight peut interférer sur macOS → le désactiver
        router_instance_offline._spotlight = None

        result = await router_instance_offline.route("parle moi de quelque chose")
        # Aucun pattern, offline → CLARIFICATION
        assert result.decision == "CLARIFICATION"

    @pytest.mark.asyncio
    async def test_llm_classification_no_llm(self, router_instance_no_llm):
        """Sans cloud_llm (cloud_llm=None), pas de classification LLM.
        Online mais pas de LLM → fallback cloud."""
        router_instance_no_llm._spotlight = None

        result = await router_instance_no_llm.route("raconte moi une histoire")
        assert result.decision == "CLOUD_GROQ"


# ═══════════════════════════════════════════════════════════════════════
# 16. Spotlight
# ═══════════════════════════════════════════════════════════════════════

class TestSpotlight:
    """Spotlight (recherche fichiers locaux) → LOCAL_RAG."""

    @pytest.mark.asyncio
    async def test_spotlight(self):
        """Quand Spotlight retourne des fichiers, decision = LOCAL_RAG,
        confidence = 0.7."""
        from unittest.mock import AsyncMock, MagicMock
        from src.routing import Router
        from src.rag.spotlight import SpotlightResult

        mock_rag = MagicMock()
        mock_rag.retrieve = AsyncMock()
        mock_rag.retrieve.return_value = ("", None)

        router = Router(
            rag_engine=mock_rag,
            is_online_check=lambda: True,
            cloud_llm=None,
        )

        # Mocker Spotlight avec un résultat
        mock_result = SpotlightResult(
            path="/Users/test/Documents/notes.txt",
            filename="notes.txt",
            content="Ceci est un document de test avec des notes importantes.",
            relevance=0.85,
            match_count=2,
            content_match=True,
        )
        spotlight_mock = MagicMock()
        spotlight_mock.search.return_value = [mock_result]
        router._spotlight = spotlight_mock

        # Requête qui ne matche AUCUN pattern (mot-clé absent de RAG_KEYWORDS)
        # → passe directement au Spotlight
        result = await router.route("recherche documentaire interne")
        assert result.decision == "LOCAL_RAG"
        assert result.confidence == 0.7
        assert "Spotlight" in result.reasoning
        assert "notes.txt" in result.spotlight_context


# ═══════════════════════════════════════════════════════════════════════
# 17-18. Fallback (N5-N6)
# ═══════════════════════════════════════════════════════════════════════

class TestFallback:
    """Fallback cloud ou clarification selon connectivité."""

    @pytest.mark.asyncio
    async def test_cloud_fallback(self, router_instance_no_llm):
        """Aucune pattern, online → CLOUD_GROQ (confidence 0.5)."""
        router_instance_no_llm._spotlight = None

        result = await router_instance_no_llm.route("parle moi d'un sujet quelconque")
        assert result.decision == "CLOUD_GROQ"
        assert result.confidence == 0.5
        assert "Fallback" in result.reasoning

    @pytest.mark.asyncio
    async def test_clarification_offline(self, router_instance_offline):
        """Aucune pattern, offline → CLARIFICATION (confidence 0.0)."""
        router_instance_offline._spotlight = None

        result = await router_instance_offline.route("parle moi d'un sujet quelconque")
        assert result.decision == "CLARIFICATION"
        assert result.confidence == 0.0
        assert "Hors ligne" in result.reasoning


# ═══════════════════════════════════════════════════════════════════════
# 19. HybridStrategy enum
# ═══════════════════════════════════════════════════════════════════════

class TestHybridStrategy:
    """HybridStrategy.from_config convertit les strings en énumérations."""

    @pytest.mark.parametrize("mode,expected", [
        ("local_only", HybridStrategy.LOCAL_ONLY),
        ("verify",     HybridStrategy.LOCAL_CLOUD_VERIFY),
        ("plan",       HybridStrategy.CLOUD_PLAN_LOCAL),
        ("rag",        HybridStrategy.LOCAL_RAG_CLOUD),
        ("unknown",    HybridStrategy.LOCAL_ONLY),   # fallback inconnu
        ("",           HybridStrategy.LOCAL_ONLY),   # chaîne vide
    ])
    def test_hybrid_strategy_enum(self, mode, expected):
        """HybridStrategy.from_config retourne la bonne stratégie."""
        assert HybridStrategy.from_config(mode) == expected


# ═══════════════════════════════════════════════════════════════════════
# 20. route_with_context — escalade RAM
# ═══════════════════════════════════════════════════════════════════════

class TestRouteWithContext:
    """route_with_context avec QueryContext et escalade cloud si RAM basse."""

    @pytest.mark.asyncio
    async def test_route_with_context_ram_escalation(self):
        """Quand la RAM est inférieure au seuil et que route() retourne
        LOCAL_RAG (via LLM→RAG), route_with_context escalade vers CLOUD_GROQ."""
        from unittest.mock import AsyncMock, MagicMock
        from src.routing import Router
        from src.rag_engine import RAGResult
        from src.core.policies import PolicyEngine

        mock_rag = MagicMock()
        mock_rag.retrieve = AsyncMock()
        mock_rag.retrieve.return_value = (
            "contenu RAG de test",
            RAGResult(
                documents_found=1,
                chunks_retrieved=3,
                top_score=0.85,
                all_scores=[0.85],
                sources=[{"source": "doc.pdf", "title": "Document test"}],
                confidence_label="HAUTE",
            ),
        )

        # Mock LLM qui classifie 'rag' — assigner directement une fonction
        # génératrice asynchrone pour que 'async for' fonctionne
        async def _stream_rag(*args, **kwargs):
            yield "rag"

        mock_llm = MagicMock()
        mock_llm.generate_stream = _stream_rag

        # PolicyEngine avec seuil RAM à 2 Go pour que 500 Mo déclenche
        policy = PolicyEngine()
        policy.CLOUD_FALLBACK_RAM_GB = 2.0

        router = Router(
            rag_engine=mock_rag,
            is_online_check=lambda: True,
            cloud_llm=mock_llm,
            policy_engine=policy,
        )
        # Pas de Spotlight pour éviter interférence
        router._spotlight = None

        # Contexte avec RAM basse
        ctx = QueryContext(
            query="un sujet quelconque",
            session_id="test-session",
            is_online=True,
            ram_free_mb=500,  # 500 Mo < 2 Go → escalation
        )

        result = await router.route_with_context(ctx)

        # Le LLM a classifié 'rag', top_score=0.85 >= 0.15 → LOCAL_RAG
        # Puis RAM basse → escalation vers CLOUD_GROQ
        assert result.decision == "CLOUD_GROQ"
        assert "RAM trop basse" in result.reasoning
        assert result.hybrid_strategy is not None
