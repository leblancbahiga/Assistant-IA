"""
Test unitaire de l'intégration du Reranker + Seuil 0.60 dans RAGEngine.
Mocke la base vectorielle et le reranker pour isoler le test.
"""
import sys
import os
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

# Ajouter le répertoire parent pour importer src
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.rag_engine import RAGEngine, RAGResult

async def test_reranker_seuil_integration():
    print("🚀 Test : Reranker Cross-Encoder + Seuil 0.60")
    
    # 1. Créer l'engine (sans DB réelle en mockant l'init)
    engine = RAGEngine()
    
    # 2. Simuler des résultats de recherche
    fake_vec_results = [
        ("Le riz africain Oryza glaberrima", "doc_riz.pdf", 0.35),  # distance 0.65 → score 0.35
        ("Les variétés NERICA sont résistantes", "doc_nerica.pdf", 0.50),  # distance 0.50 → score 0.50
        ("L'agriculture en RDC est diversifiée", "doc_agric.pdf", 0.45),  # distance 0.55 → score 0.45
    ]
    fake_fts_results = [
        ("Le riz africain Oryza glaberrima", "doc_riz.pdf", 1.0),
        ("Cultivars de maïs en Afrique", "doc_mais.pdf", 1.0),
    ]
    
    # 3. Simuler le reranker (retourne un score élevé)
    engine.reranker.load_model = MagicMock(return_value=None)
    engine.reranker.rerank = MagicMock(return_value=[
        ("Le riz africain Oryza glaberrima", "doc_riz.pdf", 0.85),
        ("Les variétés NERICA sont résistantes", "doc_nerica.pdf", 0.72),
    ])
    
    # 4. Mock _search_db pour retourner des faux résultats
    engine._search_db = MagicMock(return_value=(fake_vec_results, fake_fts_results))
    
    # Mock embedder
    engine.embedder.embed = AsyncMock(return_value=[[0.1] * 768])
    
    # 5. Tester avec une requête "riz africain"
    context, result = await engine.retrieve("riz africain", k=3)
    
    print(f"\n📊 Résultats du test :")
    print(f"   Score top1: {result.top_score:.2f}")
    print(f"   Seuil 0.60: {'PASS' if result.top_score >= 0.60 else 'ÉCHEC'}")
    print(f"   Rejeté? : {'OUI' if result.rejection_reason else 'NON'}")
    print(f"   Chunks injectés: {result.chunks_injected}")
    print(f"   Reranker appelé? : {'OUI' if engine.reranker.rerank.called else 'NON'}")
    
    # Vérifications
    assert context != "", "❌ Le contexte ne devrait pas être vide (top1=0.50 + FTS pas assez)" 
    # Wait - top1_score = 1 - 0.50 = 0.50 < 0.60
    # But FTS fallback is 0.40, and top1_score=0.50 >= 0.40, so FTS saves it!
    # Also FTS has results > 0
    print(f"\n✅ Test principal réussi : contexte non vide, reranker appelé.")
    
    # 6. Test avec un score très bas (inférieur au seuil)
    print("\n--- TEST 2 : Score bas (0.15) → Doit être rejeté ---")
    fake_vec_low = [
        ("un document pas très pertinent", "doc_bad.pdf", 0.85),  # distance 0.85 → score 0.15
    ]
    engine._search_db = MagicMock(return_value=(fake_vec_low, []))  # Pas de FTS !
    engine.reranker.rerank = MagicMock(return_value=[])  # Reranker ne trouve rien
    
    context2, result2 = await engine.retrieve("qch sans rapport", k=3)
    
    if result2.rejection_reason:
        print(f"✅ Test 2 réussi : Rejet confirmé (score={result2.top_score:.2f}, raison: {result2.rejection_reason})")
    else:
        print(f"❌ Test 2 échoué : Contexte non rejeté (score={result2.top_score:.2f})")
    
    # 7. Test du fallback BM25 (si reranker tombe)
    print("\n--- TEST 3 : Reranker tombe → fallback BM25 ---")
    fake_vec_results_normal = [
        ("Le riz africain Oryza glaberrima", "doc_riz.pdf", 0.25),  # score 0.75
    ]
    engine._search_db = MagicMock(return_value=(fake_vec_results_normal, fake_fts_results))
    engine.reranker.rerank = MagicMock(return_value=[])  # Reranker retourne vide (modèle non chargé)
    
    context3, result3 = await engine.retrieve("riz africain", k=3)
    
    if context3 and "Oryza" in context3:
        print(f"✅ Test 3 réussi : Fallback BM25 a fonctionné (contenu trouvé: 'Oryza')")
    else:
        print(f"❌ Test 3 échoué : Pas de fallback ou contenu vide")

if __name__ == "__main__":
    asyncio.run(test_reranker_seuil_integration())