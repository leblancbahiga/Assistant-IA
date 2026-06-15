#!/usr/bin/env python3
"""Diagnostic complet temps réel : retrieval + scores + chunks."""
import sys, os, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
logging.disable(logging.CRITICAL)
import asyncio, json

# Check chunk stats
import sqlite3
try:
    import pysqlite3
    sqlite3 = pysqlite3
except:
    pass

db_path = "indexes/nuru.db"
conn = sqlite3.connect(db_path)

# Chunk content stats
print("=== CHUNK STATS ===")
rows = conn.execute("SELECT content FROM chunks_fts LIMIT 1000").fetchall()
lengths = [len(r[0]) for r in rows]
print(f"  Total chunks: {len(rows)}")
print(f"  Avg char length: {sum(lengths)/len(lengths):.0f}" if lengths else "  No chunks")
if lengths:
    print(f"  Min: {min(lengths)} chars, Max: {max(lengths)} chars")
    short = sum(1 for l in lengths if l < 100)
    print(f"  Chunks < 100 chars: {short} ({short/len(lengths)*100:.1f}%)")

# Sample some chunks
print("\n=== SAMPLE CHUNKS (first 5) ===")
for i, r in enumerate(rows[:5]):
    print(f"  [{i+1}] {r[0][:150]}...")
    print(f"      Length: {len(r[0])} chars")
    print()

conn.close()

# Now test actual retrieval
print("\n\n=== LIVE RETRIEVAL TEST ===")
from src.rag_engine import RAGEngine

async def test():
    engine = RAGEngine()
    
    queries = [
        "Sustainable agriculture training YARID",
        "CV Leblanc Bahiga",
        "rapport BEACCOM riz",
        "YARID concept note training",
        "Sustainable Agriculture Monitoring tool",
        "LEAD Achievements",
        "analyse et améliorations curriculum",
        "Palabek agricultural curriculum",
        "smart agriculture training",
        "BEACCOM riz Walikale étude base",
    ]
    
    for query in queries:
        ctx, res = await engine.retrieve(query)
        print(f"\n--- QUERY: {query} ---")
        print(f"  Top score:    {res.top_score:.3f}" if hasattr(res, 'top_score') else "  Top score: N/A")
        print(f"  Confidence:   {res.confidence_label}" if hasattr(res, 'confidence_label') else "  Conf: N/A")
        print(f"  Context len:  {len(ctx)} chars")
        print(f"  Chunks retr:  {res.chunks_retrieved}" if hasattr(res, 'chunks_retrieved') else "")
        if hasattr(res, 'rejection_reason') and res.rejection_reason:
            print(f"  ❌ REJECTED: {res.rejection_reason}")
        if hasattr(res, 'all_scores') and res.all_scores:
            print(f"  Scores:       {[f'{s:.3f}' for s in res.all_scores[:8]]}")
        if not ctx:
            print(f"  ❌ EMPTY CONTEXT")
            if hasattr(res, 'chunks_retrieved') and res.chunks_retrieved == 0:
                print(f"  CAUSE: MultiSearch returned 0 results")
            elif hasattr(res, 'diagnostic') and res.diagnostic:
                print(f"  Diagnostic: {json.dumps(res.diagnostic, indent=2)[:300]}")
        else:
            sources = set()
            for line in ctx.split('\n'):
                if line.startswith('[SOURCE'):
                    s = line.split(']')[0].replace('[SOURCE ', '') if ']' in line else line[:50]
                    sources.add(s)
            print(f"  Sources:      {len(sources)} unique")
            print(f"  Preview:      {ctx[:200]}")

asyncio.run(test())
