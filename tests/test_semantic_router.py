"""
Test unitaire du Routeur Sémantique Hybride.
Teste les 4 niveaux de décision : Trivial, RAG, Cloud, Clarification.
"""
import sys
import os
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.semantic_router import SemanticRouter, RouterResult

async def test_semantic_router():
    print("🚀 Test : Routeur Sémantique Hybride (4 niveaux)")
    
    # === TEST 1 : TRIVIAL CHECK ===
    print("\n--- TEST 1 : Trivial Check ---")
    router = SemanticRouter(is_online_check=lambda: True)
    
    trivial_queries = [
        ("bonjour", "SIMPLE"),
        ("merci beaucoup", "SIMPLE"),
        ("oui", "SIMPLE"),
        ("c'est bien", "SIMPLE"),
        ("c'était super", "SIMPLE"),
        ("ok", "SIMPLE"),
        ("bonne nuit", "SIMPLE"),
    ]
    
    for query, expected in trivial_queries:
        result = await router.route(query)
        status = "✅" if result.decision == expected else "❌"
        print(f"  {status} '{query[:20]}' → {result.decision} (attendu: {expected})")
    
    # === TEST 2 : RAG KEYWORDS ===
    print("\n--- TEST 2 : RAG Confidence (mots-clés + RAG trouvé) ---")
    
    # Mock RAG engine qui retourne un contexte non vide
    mock_rag_engine = MagicMock()
    mock_rag_engine.retrieve = AsyncMock(return_value=(
        "Contenu sur le CV de Leblanc...",
        MagicMock(
            top_score=0.82,
            chunks_injected=3,
            rejection_reason=None,
            documents_found=1,
            sources=[{"name": "CV_Leblanc.pdf", "score": 0.82, "preview": "Ingénieur agronome..."}],
            tokens_injected=450,
        )
    ))
    
    router = SemanticRouter(rag_engine=mock_rag_engine, is_online_check=lambda: True)
    
    rag_queries = [
        "trouve le fichier CV de Leblanc",
        "mon cv et mes diplômes",
        "document sur IITA",
        "rapport de projet",
    ]
    
    for query in rag_queries:
        result = await router.route(query)
        status = "✅" if result.decision == "LOCAL_RAG" else "❌"
        print(f"  {status} '{query[:35]}' → {result.decision} (score: {result.rag_top_score:.2f})")
    
    # === TEST 3 : RAG FAIBLE → CLOUD FALLBACK ===
    print("\n--- TEST 3 : RAG faible → Cloud Fallback ---")
    
    # Mock RAG engine qui rejette (score trop bas)
    mock_rag_reject = MagicMock()
    mock_rag_reject.retrieve = AsyncMock(return_value=(
        "",  # Contexte vide
        MagicMock(
            top_score=0.22,
            chunks_injected=0,
            rejection_reason="top_score=0.22 < 0.60",
            documents_found=0,
            sources=[],
            tokens_injected=0,
        )
    ))
    
    router2 = SemanticRouter(rag_engine=mock_rag_reject, is_online_check=lambda: True)
    result = await router2.route("explique les concepts de rotations culturales en Afrique")
    
    status = "✅" if result.decision == "CLOUD_GROQ" else "❌"
    print(f"  {status} RAG faible → {result.decision} (score: {result.rag_top_score:.2f})")
    
    # === TEST 4 : OFFLINE → CLARIFICATION ===
    print("\n--- TEST 4 : Hors ligne → Clarification ---")
    
    router3 = SemanticRouter(
        rag_engine=MagicMock(),  # RAG engine sans RAG (retourne vide)
        is_online_check=lambda: False  # Offline
    )
    router3.rag_engine.retrieve = AsyncMock(return_value=(
        "",  # Aucun contexte
        MagicMock(
            top_score=0.0,
            chunks_injected=0,
            rejection_reason="Pas de documents",
            documents_found=0,
            sources=[],
            tokens_injected=0,
        )
    ))
    
    result = await router3.route("explique la photosynthèse")
    status = "✅" if result.decision == "CLARIFICATION" else "❌"
    print(f"  {status} Offline → {result.decision} (confiance: {result.confidence})")
    
    # === TEST 5 : PERFORMANCE (temps de décision) ===
    print("\n--- TEST 5 : Performance (temps de décision) ---")
    
    import time
    t1 = time.time()
    for _ in range(100):
        await SemanticRouter().route("bonjour")
    avg_trivial_ms = (time.time() - t1) * 10
    
    status = "✅" if avg_trivial_ms < 10 else "❌"
    print(f"  {status} Temps moyen décision Trivial: {avg_trivial_ms:.2f} ms (< 10 ms attendu)")
    
    print("\n🏁 Fin des tests du Routeur Sémantique.")

if __name__ == "__main__":
    asyncio.run(test_semantic_router())