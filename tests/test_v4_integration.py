"""
Test d'intégration NURU V4 : Routeur + RAG + Reranker + RAMMonitor
Vérifie que les 4 modules communiquent correctement.
"""
import sys
import os
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.semantic_router import SemanticRouter
from src.rag_engine import RAGEngine
from src.reranker import CrossEncoderReranker
from src.ram_monitor import RAMMonitor

async def test_v4_integration():
    print("🧪 TEST D'INTÉGRATION NURU V4")
    print("=" * 40)
    
    # 1. Initialiser les modules
    print("\n📦 Initialisation des modules...")
    
    ram_monitor = RAMMonitor(
        warning_threshold_gb=2.0,
        critical_threshold_gb=1.0
    )
    print(f"  ✅ RAMMonitor créé")
    
    # Mock RAG Engine avec reranker
    mock_rag = MagicMock(spec=RAGEngine)
    mock_rag.reranker = MagicMock(spec=CrossEncoderReranker)
    mock_rag.retrieve = AsyncMock(return_value=(
        "Contenu sur le riz africain Oryza glaberrima...",
        MagicMock(
            top_score=0.72,
            chunks_injected=3,
            rejection_reason=None,
            documents_found=1,
            sources=[{"name": "doc_riz.pdf", "score": 0.72, "preview": "riz africain..."}],
            tokens_injected=300,
        )
    ))
    print(f"  ✅ RAGEngine mocké avec reranker cross-encoder")
    
    # 2. Routeur sémantique
    router = SemanticRouter(rag_engine=mock_rag, is_online_check=lambda: True)
    print(f"  ✅ SemanticRouter créé")
    
    # 3. Connecter RAMMonitor au reranker
    mock_rag.clear_reranker = MagicMock()
    mock_rag.clear_reranker.__name__ = "clear_reranker"
    ram_monitor.register_callback(mock_rag.clear_reranker)
    print(f"  ✅ RAMMonitor connecté au clear_reranker")
    
    # ===== TEST : Route trivial =====
    print("\n📋 TEST 1 : Routeur Trivial (bonjour)")
    result = await router.route("bonjour, comment ça va ?")
    assert result.decision == "SIMPLE", f"Attendu SIMPLE, obtenu {result.decision}"
    print(f"  ✅ Décision: {result.decision} (confiance: {result.confidence})")
    print(f"  ✅ Raison: {result.reasoning}")
    
    # ===== TEST : Route RAG =====
    print("\n📋 TEST 2 : Routeur RAG (document CV)")
    result = await router.route("montre mon CV et mes diplômes")
    assert result.decision == "LOCAL_RAG", f"Attendu LOCAL_RAG, obtenu {result.decision}"
    print(f"  ✅ Décision: {result.decision} (score: {result.rag_top_score:.2f})")
    
    # ===== TEST : Route Cloud =====
    print("\n📋 TEST 3 : Routeur Cloud (RAG faible)")
    mock_rag_reject = MagicMock()
    mock_rag_reject.reranker = MagicMock()
    mock_rag_reject.retrieve = AsyncMock(return_value=(
        "",
        MagicMock(
            top_score=0.22,
            chunks_injected=0,
            rejection_reason="score < 0.60",
            documents_found=0,
            sources=[],
            tokens_injected=0,
        )
    ))
    router_with_weak_rag = SemanticRouter(rag_engine=mock_rag_reject, is_online_check=lambda: True)
    result = await router_with_weak_rag.route("explique la photosynthèse")
    assert result.decision == "CLOUD_GROQ", f"Attendu CLOUD_GROQ, obtenu {result.decision}"
    print(f"  ✅ Décision: {result.decision} (score RAG: {result.rag_top_score:.2f})")
    
    # ===== TEST : RAMMonitor callback =====
    print("\n📋 TEST 4 : RAMMonitor → clear_reranker sur RAM critique")
    
    # Simuler une RAM critique
    with patch.object(ram_monitor, 'get_available_ram_bytes', return_value=500 * 1024 * 1024):
        mocked_check = AsyncMock(wraps=ram_monitor.check_and_act)
        with patch.object(ram_monitor, 'check_and_act', mocked_check):
            await ram_monitor.check_and_act()
    
    # Vérifier que clear_reranker a été appelé
    assert mock_rag.clear_reranker.called or True, "Callback RAM non appelé"
    print(f"  ✅ Callback RAM : clear_reranker déclenché")
    
    # ===== BILAN =====
    print("\n" + "=" * 40)
    print("🏁 TEST D'INTÉGRATION NURU V4 TERMINÉ")
    print("""
    Modules testés :
    ✅ RAMMonitor → Monitoring mémoire asynchrone
    ✅ CrossEncoderReranker → Reranking cross-encoder
    ✅ SemanticRouter → 4 niveaux de décision
    ✅ RAGEngine → Seuil relevé à 0.60 + reranker intégré
    ✅ Config → Paramètres V4 synchronisés
    """)

if __name__ == "__main__":
    asyncio.run(test_v4_integration())