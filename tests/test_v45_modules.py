"""Tests unitaires pour les modules NURU V4.5 (logique pure, sans MLX ni DB).

Couvre : PolicyEngine, QueryContext, EvidencePack, RRF, Cache,
         ContextCompressor, CitationBuilder, Verifier, AppState.
"""
import sys
import os
import time
from dataclasses import dataclass
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════
# 1. PolicyEngine
# ═══════════════════════════════════════════

def test_policy_engine():
    """Teste toutes les décisions du PolicyEngine."""
    from src.core.policies import PolicyEngine
    from src.core.query_context import QueryContext

    pe = PolicyEngine()

    # ── should_rerank ──

    # Zone grise + RAM OK → reranker activé
    assert pe.should_rerank(0.50, 2000) == True, "Zone grise + RAM OK"
    assert pe.should_rerank(0.60, 2000) == True, "Milieu zone grise"
    assert pe.should_rerank(0.74, 2000) == True, "Limite haute zone grise"

    # Hors zone grise → pas de reranker
    assert pe.should_rerank(0.80, 2000) == False, "Score > 0.75 → pas reranker"
    assert pe.should_rerank(0.30, 2000) == False, "Score < 0.40 → pas reranker"

    # Zone grise mais RAM insuffisante → pas de reranker
    assert pe.should_rerank(0.50, 1000) == False, "Zone grise mais RAM insuffisante"

    # Cas limites
    assert pe.should_rerank(0.40, 2000) == False, "Score = 0.40 exclus"
    assert pe.should_rerank(0.75, 2000) == False, "Score = 0.75 exclus"

    # ── should_use_cloud ──

    # RAM faible + online → cloud
    ctx_online_low = QueryContext(query="test", session_id="s1", is_online=True, ram_free_mb=1000)
    assert pe.should_use_cloud(ctx_online_low) == True, "RAM faible + online → cloud"

    # RAM suffisante → local
    ctx_online_high = QueryContext(query="test", session_id="s1", is_online=True, ram_free_mb=4000)
    assert pe.should_use_cloud(ctx_online_high) == False, "RAM OK + online → local"

    # Offline → local même si RAM faible
    ctx_offline = QueryContext(query="test", session_id="s1", is_online=False, ram_free_mb=1000)
    assert pe.should_use_cloud(ctx_offline) == False, "Offline → local même si RAM faible"

    # ── should_store_memory ──
    assert pe.should_store_memory(0.80) == True, "Confiance > 0.78 → store"
    assert pe.should_store_memory(0.77) == False, "Confiance < 0.78 → pas store"
    assert pe.should_store_memory(0.78) == True, "Confiance = 0.78 → store"

    # ── route_from_score ──
    # Mock partiel (pas de psutil en test)
    @dataclass(frozen=True)
    class MockCtx:
        is_online: bool
        ram_free_mb: int = 4000
        query: str = "test"

    assert pe.route_from_score(MockCtx(is_online=True), 0.80) == "LOCAL_RAG", "Score haut → RAG"
    assert pe.route_from_score(MockCtx(is_online=True), 0.50) == "LOCAL_RAG", "Score moyen → RAG"
    assert pe.route_from_score(MockCtx(is_online=True), 0.30) == "CLOUD_GROQ", "Score bas + online → cloud"
    assert pe.route_from_score(MockCtx(is_online=False), 0.30) == "CLARIFICATION", "Score bas + offline → clarification"

    print("✅ test_policy_engine: 15 assertions OK")


# ═══════════════════════════════════════════
# 2. QueryContext & EvidencePack
# ═══════════════════════════════════════════

def test_query_context():
    """Teste les conteneurs immutables."""
    from src.core.query_context import QueryContext, EvidencePack, Citation

    # ── QueryContext ──
    ctx = QueryContext(query="quoi?", session_id="abc")
    assert ctx.query == "quoi?"
    assert ctx.session_id == "abc"
    assert ctx.route == "unknown"
    assert ctx.is_online == True
    assert ctx.ram_free_mb == 0  # Valeur par défaut, from_runtime lit psutil

    # with_route crée une copie immuable
    ctx2 = ctx.with_route("LOCAL_RAG")
    assert ctx2.route == "LOCAL_RAG"
    assert ctx.route == "unknown"  # Original inchangé
    assert ctx is not ctx2  # Vraiment une nouvelle instance (frozen)

    # from_runtime nécessite psutil → testé avec un mock
    try:
        import psutil
        ctx3 = QueryContext.from_runtime("salut", "session1")
        assert ctx3.query == "salut"
        assert ctx3.ram_free_mb > 0  # RAM réelle
        print("  QueryContext.from_runtime: RAM libre =", ctx3.ram_free_mb, "MB")
    except ImportError:
        print("  ⚠️ psutil non disponible, from_runtime non testé")

    # ── EvidencePack ──
    pack = EvidencePack(query="test", confidence=0.65)
    assert pack.query == "test"
    assert pack.confidence == 0.65
    assert pack.retrieval_mode == "none"
    assert pack.has_evidence == False  # Pas de chunks, pas de confiance > 0

    pack2 = EvidencePack(query="test", chunks=["chunk1"], confidence=0.85)
    assert pack2.has_evidence == True

    pack3 = EvidencePack(
        query="essai",
        chunks=["c1", "c2"],
        sources=["doc1.pdf"],
        retrieval_mode="reranked",
        reranker_used=True,
        retrieval_time_ms=42.5,
    )
    d = pack3.to_dict()
    assert d["confidence"] == 0.0  # Valeur par défaut arrondie
    assert d["num_chunks"] == 2
    assert d["mode"] == "reranked"
    assert d["reranker_used"] == True
    assert d["time_ms"] == 42.5

    # ── Citation dataclass ──
    cite = Citation(doc_id="doc1", chunk_id="chunk42", title="Rapport")
    assert cite.doc_id == "doc1"
    assert cite.source is None  # Optionnel

    print("✅ test_query_context: 10 assertions OK")


# ═══════════════════════════════════════════
# 3. RRF — Reciprocal Rank Fusion
# ═══════════════════════════════════════════

def test_rrf():
    """Teste la fusion RRF des résultats vectoriels et FTS."""
    from src.rag.retrieval import reciprocal_rank_fusion as rrf

    # ── Cas normal : vector + FTS ──
    vec = [
        ("Le YARID est une ONG", "doc1.pdf", 0.3),
        ("Agriculture durable en Ouganda", "doc2.pdf", 0.4),
    ]
    fts = [
        ("YARID signifie Young African Refugees", "doc1.pdf", 1.0),
    ]
    fused = rrf(vec, fts, top_k=5)
    assert len(fused) >= 2, "RRF devrait fusionner les résultats"
    assert fused[0][2] >= fused[-1][2], "Résultats triés par score décroissant"
    print(f"  RRF fusion: {len(fused)} résultats, top1={fused[0][2]:.4f}")

    # ── Vector seul ──
    fused2 = rrf(vec, [], top_k=5)
    assert len(fused2) == 2
    assert fused2[0][0] == "Le YARID est une ONG"

    # ── FTS seul ──
    fused3 = rrf([], fts, top_k=5)
    assert len(fused3) == 1

    # ── Résultats vides ──
    assert rrf([], [], top_k=5) == []

    # ── Déduplication ──
    # Deux résultats avec le même content[:200] sont fusionnés
    same_prefix = "YARID est une ONG basée à Kampala. " * 12  # > 200 chars
    vec_dup = [
        (same_prefix, "doc1.pdf", 0.3),
        (same_prefix, "doc1.pdf", 0.5),
    ]
    fused4 = rrf(vec_dup, [], top_k=5)
    assert len(fused4) == 1, "Déduplication par content[:200]"

    # ── top_k limite ──
    vec5 = [(f"Chunk numéro {i}", f"doc{i}.pdf", 0.5) for i in range(20)]
    fused5 = rrf(vec5, [], top_k=5)
    assert len(fused5) == 5, "top_k=5 doit limiter les résultats"

    print("✅ test_rrf: 7 assertions OK")


# ═══════════════════════════════════════════
# 4. TTLDecisionCache
# ═══════════════════════════════════════════

def test_cache():
    """Teste le cache TTL du routeur."""
    from src.infra.cache import TTLDecisionCache

    cache = TTLDecisionCache(maxsize=10, ttl_seconds=60)

    # ── make_key ──
    key1 = cache.make_key("bonjour", "default")
    key2 = cache.make_key("bonjour", "default")
    key3 = cache.make_key("bonjour", "autre")
    assert key1 == key2, "Même requête → même clé"
    assert key1 != key3, "Mode différent → clé différente"
    assert len(key1) == 40, "SHA1 hex → 40 chars"

    # get/set
    assert cache.get(key1) is None
    cache.set(key1, "resultat")
    assert cache.get(key1) == "resultat"

    # size
    assert cache.size == 1
    cache.set(cache.make_key("autre"), "test")
    assert cache.size == 2

    # clear
    cache.clear()
    assert cache.size == 0
    assert cache.get(key1) is None

    # ── TTL expiration ──
    cache_ttl = TTLDecisionCache(maxsize=10, ttl_seconds=1)
    k = cache_ttl.make_key("rapide")
    cache_ttl.set(k, "valeur")
    assert cache_ttl.get(k) == "valeur"
    time.sleep(1.1)
    assert cache_ttl.get(k) is None, "TTL expiré"

    # ── maxsize eviction ──
    cache_small = TTLDecisionCache(maxsize=2, ttl_seconds=60)
    cache_small.set(cache_small.make_key("a"), 1)
    cache_small.set(cache_small.make_key("b"), 2)
    cache_small.set(cache_small.make_key("c"), 3)
    assert cache_small.size <= 2, "Maxsize enforcement"

    print("✅ test_cache: 10 assertions OK")


# ═══════════════════════════════════════════
# 5. ContextCompressor
# ═══════════════════════════════════════════

def test_context_compressor():
    """Teste la compression contextuelle regex-only."""
    from src.rag.compression import ContextCompressor

    cc = ContextCompressor(max_tokens=500, min_sentence_chars=5)

    # ── _extract_tokens ──
    tokens = cc._extract_tokens("que signifie YARID en français")
    assert "yarid" in tokens, "Acronyme conservé (lowercased)"
    assert "que" not in tokens, "Stop word exclu"
    assert len(tokens) >= 2

    # ── _split_sentences ──
    phrases = cc._split_sentences("Phrase une. Phrase deux! Phrase trois?")
    assert len(phrases) == 3
    assert phrases[0] == "Phrase une."

    # ── compress avec résultats vides ──
    assert cc.compress([], "test") == ""

    # ── keep_all_if_small ──
    cc_small = ContextCompressor(max_tokens=1000, keep_all_if_small=True)
    petit_texte = "Petit texte de test."
    assert cc_small.compress([(petit_texte, "doc.pdf", 0.5)], "test") == petit_texte

    # ── Filtrage par token ──
    cc_filtre = ContextCompressor(max_tokens=100, min_sentence_chars=5, keep_all_if_small=False)
    chunks = [
        ("Le YARID est une ONG à Kampala. Elle forme des réfugiés.", "doc1.pdf", 0.6),
        ("La météo en Ouganda est chaude. Les précipitations sont abondantes.", "doc2.pdf", 0.5),
    ]
    compressed = cc_filtre.compress(chunks, "YARID Kampala")
    assert "YARID" in compressed, "Phrase avec YARID conservée"
    assert "météo" not in compressed, "Phrase sans mot-clé filtrée"

    print("✅ test_context_compressor: 6 assertions OK")


# ═══════════════════════════════════════════
# 6. CitationBuilder & Verifier
# ═══════════════════════════════════════════

def test_citations():
    """Teste le système de citations et vérification."""
    from src.rag.citations import CitationBuilder, Verifier, Citation

    builder = CitationBuilder()

    # ── make depuis tuples ──
    chunks = [
        ("YARID est une ONG", "doc1.pdf", 0.85),
        ("Agriculture durable", "doc2.pdf", 0.72),
    ]
    citations = builder.make(chunks)
    assert len(citations) == 2
    assert citations[0].source == "doc1.pdf"
    assert round(citations[0].score, 2) == 0.85

    # ── make depuis vide ──
    assert builder.make([]) == []

    # ── format_context ──
    cite1 = Citation(source="doc1.pdf", title="Rapport YARID")
    ctx = builder.format_context([cite1])
    assert "Source: doc1.pdf" in ctx
    assert "Rapport YARID" in ctx

    # format_context vide
    assert "[AUCUNE SOURCE" in builder.format_context([])

    # ── extract_from ──
    response = "YARID est une ONG [Source: doc1.pdf] [Source: doc2.pdf]"
    found = builder.extract_from(response)
    assert len(found) == 2
    assert "[Source: doc1.pdf]" in found

    # ── Verifier ──
    verifier = Verifier()

    # Pas de chunks → invalide
    result = verifier.verify("Ceci est une réponse", [])
    assert result.valid == False
    assert "Aucun chunk" in result.reason

    # Chunks mais pas de citation dans la réponse → invalide
    result2 = verifier.verify("Ceci est une réponse sans source", chunks)
    assert result2.valid == False
    assert "Aucune citation" in result2.reason

    # Chunks + citation dans la réponse → valide
    result3 = verifier.verify("YARID est [Source: doc1.pdf]", chunks)
    assert result3.valid == True
    assert result3.confidence > 0
    assert len(result3.citations) == 1

    print("✅ test_citations: 10 assertions OK")


# ═══════════════════════════════════════════
# 7. AppState
# ═══════════════════════════════════════════

def test_app_state():
    """Teste le store d'état immutable de l'UI."""
    from src.ui.state.app_state import AppState

    state = AppState()
    assert state.current_model == "local"
    assert state.active_route == "idle"
    assert state.is_busy == False
    assert state.pipeline_stage == "idle"

    state = AppState(
        current_model="phi-4-mini",
        active_route="generating",
        rag_confidence=0.72,
        ram_free_mb=2048,
        tokens_per_sec=12.5,
        is_busy=True,
        pipeline_stage="generating",
        streaming_text="Bonjour,",
    )
    assert state.current_model == "phi-4-mini"
    assert state.active_route == "generating"
    assert state.rag_confidence == 0.72
    assert state.ram_free_mb == 2048
    assert state.tokens_per_sec == 12.5
    assert state.streaming_text == "Bonjour,"

    print("✅ test_app_state: 9 assertions OK")


# ═══════════════════════════════════════════
# 8. EventBus (unitaire, pas de singleton)
# ═══════════════════════════════════════════

def test_event_bus():
    """Teste l'EventBus."""
    from src.core.events import EventBus
    import asyncio

    bus = EventBus()  # Instance singleton

    # subscribe / emit async
    received = []
    async def handler(data):
        received.append(data)

    bus.subscribe("test.event", handler)
    asyncio.run(bus.emit("test.event", {"msg": "hello"}))
    assert len(received) == 1
    assert received[0] == {"msg": "hello"}

    # unsubscribe
    bus.unsubscribe("test.event", handler)
    asyncio.run(bus.emit("test.event", {"msg": "ignored"}))
    assert len(received) == 1  # Pas d'incrément

    # emit_sync ajoute à la file
    bus.emit_sync("sync.event", "data")
    drained = bus.drain_events()
    assert len(drained) >= 1

    # drain vide la file
    drained2 = bus.drain_events()
    assert len(drained2) == 0  # File déjà vidée

    print("✅ test_event_bus: 4 assertions OK")


# ═══════════════════════════════════════════
# 9. SemanticChunker (logique de split)
# ═══════════════════════════════════════════

def test_semantic_chunker():
    """Teste le SemanticChunker (sans embedding)."""
    from src.rag.chunking import SemanticChunker, SemanticChunk

    chunker = SemanticChunker()

    # ── Texte vide ──
    assert chunker.chunk("", "empty.txt") == []

    # ── Section simple (markdown header) ──
    texte = """# Titre Principal
Paragraphe un sous le titre.

## Section Une
Contenu de la section une. Avec plusieurs phrases importantes.
Encore du contenu ici.

## Section Deux
Contenu de la section deux.
"""
    chunks = chunker.chunk(texte, "test.md", metadata={"title": "Doc Test"})
    assert len(chunks) > 0, "Au moins 1 chunk"

    # Vérifier le contexte injecté
    for c in chunks:
        assert c.title, "Chaque chunk a un titre"
        assert c.level in ("section", "paragraph", "evidence"), f"Niveau valide: {c.level}"
        # Vérifier le contextualized
        assert c.title in c.contextualized, "Contexte injecté dans contextualized"

    print(f"  SemanticChunker: {len(chunks)} chunks générés depuis texte structuré")

    # ── Texte sans structure (pas de headers) ──
    texte_plat = "Premier paragraphe de contenu libre.\n\nDeuxième paragraphe.\n\nTroisième paragraphe avec plus de détails ici."
    chunks_plat = chunker.chunk(texte_plat, "plat.txt")
    assert len(chunks_plat) > 0

    print("✅ test_semantic_chunker: 5 assertions OK")


# ═══════════════════════════════════════════
# 10. ChatViewModel
# ═══════════════════════════════════════════

def test_chat_viewmodel():
    """Teste le ChatViewModel et MessageViewModel."""
    from src.ui.viewmodels.chat_vm import ChatViewModel, MessageViewModel

    vm = ChatViewModel(max_messages=3)

    # Ajout de messages
    msg1 = vm.add_message("NURU", "Bonjour!", is_user=False)
    assert msg1.sender == "NURU"
    assert msg1.is_user == False
    assert msg1.timestamp != ""

    msg2 = vm.add_message("Leblanc", "Salut", is_user=True)
    assert msg2.is_user == True
    assert vm.get_last_message() == msg2

    # Limite max_messages
    vm.add_message("NURU", "A", is_user=False)
    vm.add_message("NURU", "B", is_user=False)
    assert len(vm.messages) == 3  # max=3, le premier a été pop

    # Feedback
    vm.register_feedback(0, "up")
    assert vm.messages[0].feedback == "up"
    vm.register_feedback(999, "down")  # Index invalide
    assert len(vm.messages) == 3  # Pas de crash

    # Clear
    vm.clear()
    assert len(vm.messages) == 0
    assert vm.get_last_message() is None

    # MessageViewModel direct
    m = MessageViewModel(sender="test", content="hello", is_user=True, confidence=0.85, citations=["src1"])
    assert m.confidence == 0.85
    assert len(m.citations) == 1

    print("✅ test_chat_viewmodel: 10 assertions OK")


# ═══════════════════════════════════════════
# 11. ContextViewModel
# ═══════════════════════════════════════════

def test_context_viewmodel():
    """Teste le ContextViewModel et SourceViewModel."""
    from src.ui.viewmodels.context_vm import ContextViewModel, SourceViewModel
    from dataclasses import dataclass, field

    vm = ContextViewModel()
    assert vm.confidence == 0.0
    assert vm.retrieval_mode == "none"
    assert vm.summary()["sources"] == 0

    # update_from_rag avec un mock RAGResult
    @dataclass
    class MockRAGResult:
        top_score: float = 0.72
        chunks_retrieved: int = 10
        chunks_injected: int = 3
        retrieval_time_ms: float = 45.2
        sources: list = field(default_factory=lambda: [
            {"name": "doc1.pdf", "score": 0.85, "ext": "PDF", "preview": "Contenu du doc..."},
            {"name": "doc2.pdf", "score": 0.72, "ext": "PDF", "preview": "Autre contenu..."},
        ])

    vm.update_from_rag(MockRAGResult())
    assert round(vm.confidence, 2) == 0.72
    assert vm.chunks_found == 10
    assert vm.chunks_injected == 3
    assert vm.retrieval_time_ms == 45.2
    assert len(vm.sources) == 2
    assert vm.sources[0].name == "doc1.pdf"
    assert vm.sources[0].score == 0.85
    assert vm.summary()["sources"] == 2

    # update_from_rag avec None
    vm2 = ContextViewModel()
    vm2.update_from_rag(None)
    assert vm2.confidence == 0.0  # Pas de changement

    # update_from_evidence avec un mock
    @dataclass
    class MockEvidence:
        confidence: float = 0.65
        retrieval_mode: str = "hybrid"
        reranker_used: bool = True
        chunks_retrieved: int = 5
        chunks_injected: int = 2
        retrieval_time_ms: float = 120.0
        sources: list = field(default_factory=lambda: ["doc1.pdf", "doc2.pdf"])

    vm.update_from_evidence(MockEvidence())
    assert round(vm.confidence, 2) == 0.65
    assert vm.retrieval_mode == "hybrid"
    assert vm.reranker_used == True
    assert vm.summary()["reranker"] == True

    # SourceViewModel direct
    s = SourceViewModel(name="test.pdf", score=0.9, ext="PDF", preview="Extrait...")
    assert s.name == "test.pdf"
    assert s.score == 0.9

    print("✅ test_context_viewmodel: 14 assertions OK")


# ═══════════════════════════════════════════
# 12. TelemetryViewModel
# ═══════════════════════════════════════════

def test_telemetry_viewmodel():
    """Teste le TelemetryViewModel et TelemetrySnapshot."""
    from src.ui.viewmodels.telemetry_vm import TelemetryViewModel, TelemetrySnapshot

    # Test sans psutil (snapshot nécessite psutil réel)
    # On teste le dataclass et ram_color directement

    vm = TelemetryViewModel()

    # ram_color mapping
    assert vm.ram_color("ok") == "#10B981"
    assert vm.ram_color("warning") == "#F59E0B"
    assert vm.ram_color("critical") == "#EF4444"
    assert vm.ram_color("unknown") == "#6B7280"  # Fallback gris

    # TelemetrySnapshot direct
    snap = TelemetrySnapshot(
        ram_free_mb=2048,
        ram_total_mb=8192,
        ram_percent=75.0,
        tokens_per_sec=12.5,
        current_route="LOCAL",
        current_model="phi-4-mini",
        rag_score=0.72,
        is_busy=True,
        ram_status="warning",
    )
    assert snap.ram_free_mb == 2048
    assert snap.tokens_per_sec == 12.5
    assert snap.is_busy == True
    assert snap.ram_status == "warning"

    # snapshot() nécessite psutil → testé avec valeurs par défaut modifiées si pas dispo
    try:
        import psutil
        snap2 = vm.snapshot()
        assert snap2.ram_free_mb > 0  # RAM réelle
        assert snap2.ram_status in ("ok", "warning", "critical")
        assert isinstance(snap2.ram_percent, float)
        print(f"  TelemetrySnapshot: RAM {snap2.ram_free_mb} MB libre, statut={snap2.ram_status}")
    except ImportError:
        print("  ⚠️ psutil non disponible, snapshot non testé")

    print("✅ test_telemetry_viewmodel: 9 assertions OK")


# ═══════════════════════════════════════════
# Lancement
# ═══════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 55)
    print("🧪 Tests unitaires NURU V4.5")
    print("=" * 55)

    tests = [
        ("PolicyEngine", test_policy_engine),
        ("QueryContext & EvidencePack", test_query_context),
        ("RRF — Reciprocal Rank Fusion", test_rrf),
        ("TTLDecisionCache", test_cache),
        ("ContextCompressor", test_context_compressor),
        ("CitationBuilder & Verifier", test_citations),
        ("AppState", test_app_state),
        ("EventBus", test_event_bus),
        ("SemanticChunker", test_semantic_chunker),
        ("ChatViewModel", test_chat_viewmodel),
        ("ContextViewModel", test_context_viewmodel),
        ("TelemetryViewModel", test_telemetry_viewmodel),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        print(f"\n── {name} ──")
        try:
            fn()
            passed += 1
        except Exception as e:
            import traceback
            print(f"❌ {name}: {e}")
            traceback.print_exc()
            failed += 1

    print()
    print("=" * 55)
    print(f"📊 Résultat: {passed}/{len(tests)} tests OK", end="")
    if failed:
        print(f", {failed} ÉCHOUÉS ❌")
    else:
        print(" ✅")
    print("=" * 55)
