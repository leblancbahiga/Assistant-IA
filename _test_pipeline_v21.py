#!/usr/bin/env python3
"""Test FTS BM25 + fix chunker + retrieval complet."""
import sys, os, logging, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
logging.disable(logging.CRITICAL)

from src.rag_engine import RAGEngine
from src.ingestion import IngestionEngine

async def test():
    # 1. TEST FTS BM25 sur la base existante
    print("=== FTS BM25 SCORE TEST ===")
    engine = RAGEngine()
    results = engine._ms_vector_search("agriculture sustainable training", "fts")
    print(f"FTS results: {len(results)}")
    for i, (c, s, score) in enumerate(results[:5]):
        print(f"  [{i+1}] score={score:.3f} | source={os.path.basename(s)[:50]}")
    
    # 2. Re-index le fichier Sustainable Agriculture
    print("\n=== RE-INDEX SUSTAINABLE AGRICULTURE ===")
    filepath = "/Users/leblancbahiga/Documents/YARID/reports field/Sustainable -Agriculture Monitoring tool.docx"
    ing = IngestionEngine()
    await ing.index_file(filepath)
    
    # 3. Test retrieval avec la requête exacte
    print("\n=== RETRIEVAL: sustainable agriculture monitoring tool ===")
    ctx, res = await engine.retrieve("Sustainable Agriculture Monitoring tool YARID agriculture")
    scores = [f"{s:.3f}" for s in (res.all_scores or [])[:5]]
    print(f"Top score: {res.top_score:.3f}" if hasattr(res, 'top_score') else "")
    print(f"Confidence: {res.confidence_label}" if hasattr(res, 'confidence_label') else "")
    print(f"Scores: {scores}")
    if hasattr(res, 'rejection_reason') and res.rejection_reason:
        print(f"❌ REJECTED: {res.rejection_reason}")
    print(f"Context: {len(ctx)} chars")
    if ctx:
        print(f"Sources: {[l.split(']')[0] for l in ctx.split(chr(10)) if l.startswith('[SOURCE')][:3]}")
    
    # 4. Test concept note training YARID
    print("\n=== RETRIEVAL: concept note training YARID ===")
    ctx2, res2 = await engine.retrieve("concept note YARID training")
    scores2 = [f"{s:.3f}" for s in (res2.all_scores or [])[:5]]
    print(f"Top score: {res2.top_score:.3f}" if hasattr(res2, 'top_score') else "")
    print(f"Confidence: {res2.confidence_label}" if hasattr(res2, 'confidence_label') else "")
    print(f"Scores: {scores2}")
    print(f"Context: {len(ctx2)} chars")
    
    # 5. Stats après re-index
    import sqlite3
    try:
        import pysqlite3
        sqlite3 = pysqlite3
    except:
        pass
    conn = sqlite3.connect("indexes/nuru.db")
    n_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    n_files = conn.execute("SELECT COUNT(*) FROM indexed_files").fetchone()[0]
    avg = conn.execute("SELECT AVG(LENGTH(content)) FROM chunks").fetchone()[0]
    big = conn.execute("SELECT COUNT(*) FROM chunks WHERE LENGTH(content) > 5000").fetchone()[0]
    conn.close()
    
    print(f"\n=== STATS INDEX ===")
    print(f"Fichiers indexés: {n_files}")
    print(f"Total chunks: {n_chunks}")
    print(f"Taille moyenne: {avg:.0f} chars")
    print(f"Chunks > 5000: {big}")

asyncio.run(test())
