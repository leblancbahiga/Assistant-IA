#!/usr/bin/env python3
"""Test BM25 FTS scoring on existing index, then re-index with fixed chunker."""
import sys, os, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
logging.disable(logging.CRITICAL)
import sqlite3, json

# Use pysqlite3 if available (NURU uses it)
try:
    import pysqlite3
    sqlite3 = pysqlite3
except:
    pass

db = "indexes/nuru.db"
conn = sqlite3.connect(db)

# Test 1: BM25 works?
print("=== TEST BM25 SCORING ===")
try:
    rows = conn.execute(
        "SELECT content, source, bm25(0) as raw FROM chunks_fts "
        "WHERE content MATCH ? ORDER BY raw LIMIT 5",
        ['"agriculture" OR "sustainable" OR "training"']
    ).fetchall()
    print(f"BM25 OK! {len(rows)} results")
    for i, r in enumerate(rows):
        score = 1.0 / (1.0 + float(r[2]))
        print(f"  [{i+1}] bm25={r[2]:.2f} → score={score:.2f} | {r[1][:60]} | {r[0][:80]}...")
except Exception as e:
    print(f"BM25 FAILED: {e}")
    print("Need to rebuild FTS index")

# Test 2: What was the old FTS behavior?
print("\n=== OLD FTS (1.0 score) ===")
rows2 = conn.execute(
    "SELECT content, source, 1.0 as score FROM chunks_fts "
    "WHERE content MATCH ? LIMIT 5",
    ['"agriculture" OR "sustainable"']
).fetchall()
for i, r in enumerate(rows2):
    print(f"  [{i+1}] score={r[2]} | {r[1][:60]}")

conn.close()

# Test 3: Quick retrieval test with fixed code
print("\n\n=== QUICK RETRIEVAL WITH FIXES ===")
from src.rag_engine import RAGEngine
import asyncio

async def test():
    engine = RAGEngine()
    
    queries = [
        "Sustainable agriculture training YARID",
        "BEACCOM riz Walikale",
        "rapport étude base riz",
    ]
    
    for query in queries:
        ctx, res = await engine.retrieve(query)
        print(f"\n--- {query} ---")
        scores = [f"{s:.3f}" for s in (res.all_scores or [])[:5]]
        print(f"  Top score: {res.top_score:.3f}" if hasattr(res, 'top_score') else "  No score")
        print(f"  Confidence: {res.confidence_label}" if hasattr(res, 'confidence_label') else "")
        print(f"  Scores: {scores}")
        if hasattr(res, 'rejection_reason') and res.rejection_reason:
            print(f"  ❌ REJECTED: {res.rejection_reason}")
        print(f"  Context: {len(ctx)} chars")

asyncio.run(test())
