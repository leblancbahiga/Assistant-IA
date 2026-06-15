#!/usr/bin/env python3
"""Diagnostic complet de l'indexation RAG NURU."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
logging.disable(logging.CRITICAL)

from src.rag_engine import RAGEngine
from src.config import Config

cfg = Config()
print(f"=== CONFIG RAG ===")
print(f"  rag_score_threshold: {cfg.rag_score_threshold}")
print(f"  rag_score_fallback: {cfg.rag_score_fallback}")
print(f"  rag_min_usable_score: {cfg.rag_min_usable_score}")
print(f"  rag_router_min_score: {cfg.rag_router_min_score}")
print(f"  top_k: {cfg.top_k}")
print(f"  chunk_size: {cfg.chunk_size}")
print(f"  chunk_overlap: {cfg.chunk_overlap}")

# Init RAG engine
engine = RAGEngine(cfg)
print(f"\n=== RAG ENGINE ===")
print(f"  DB path: {cfg.rag_index_path}")
print(f"  index_size: {engine.index_size}")

# Check document count
docs = engine.get_all_documents() if hasattr(engine, 'get_all_documents') else []
if hasattr(engine, 'get_all_documents'):
    docs = engine.get_all_documents()
    print(f"  documents via engine: {len(docs)}")
else:
    # Direct SQLite query
    import sqlite3
    try:
        import pysqlite3
        sqlite3 = pysqlite3
    except:
        pass
    conn = sqlite3.connect(cfg.rag_index_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM documents")
    print(f"  documents (direct): {cur.fetchone()[0]}")
    cur.execute("SELECT id, source, doc_type, title, chunk_count, indexed_at FROM documents ORDER BY id")
    for r in cur.fetchall():
        src = (r[1] or '')[:70]
        title = (str(r[3]) or '')[:50]
        print(f"    doc#{r[0]}: {src} | type={r[2]} | '{title}' | {r[4]} chunks | {r[5]}")
    cur.execute("SELECT COUNT(*) FROM chunks")
    print(f"  chunks: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM indexed_files")
    print(f"  indexed_files: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM doc_structured")
    print(f"  doc_structured entries: {cur.fetchone()[0]}")
    conn.close()

# Test a retrieval
print(f"\n=== TEST RETRIEVAL ===")
test_queries = [
    "Leblanc Bahiga",
    "agriculture",
    "YARID",
    "ingénieur agronome",
]

for q in test_queries:
    try:
        ctx, result = engine.retrieve(q)
        has_content = len(ctx) > 100 if ctx else False
        score = result.get('score', 0) if result else 0
        chunks_n = result.get('chunks', 0) if result else 0
        label = result.get('label', 'N/A') if result else 'N/A'
        print(f"  '{q}': has_ctx={has_content} score={score:.2f} chunks={chunks_n} label={label}")
        if ctx and len(ctx) > 100:
            print(f"    ctx[:150]={ctx[:150]}")
    except Exception as e:
        print(f"  '{q}': ERROR {e}")

# Check Spotlight index 
print(f"\n=== SPOTLIGHT INDEX ===")
try:
    from src.rag.spotlight import SpotlightSearch
    ss = SpotlightSearch()
    for q in test_queries[:2]:
        res = ss.search(q, max_results=3)
        print(f"  '{q}': {len(res)} results")
        for r in res[:2]:
            print(f"    - {r.get('path','')[:60]} score={r.get('score',0):.2f}")
except Exception as e:
    print(f"  Spotlight: {e}")

# Check index health
print(f"\n=== INDEX HEALTH ===")
try:
    from src.rag.index_health import IndexHealth
    health = IndexHealth(engine)
    report = health.check()
    for k, v in report.items():
        print(f"  {k}: {v}")
except Exception as e:
    print(f"  IndexHealth: {e}")
PYEOF