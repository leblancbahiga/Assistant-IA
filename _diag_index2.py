#!/usr/bin/env python3
"""Diagnostic complet de l'indexation RAG NURU - V2."""
import sys, os, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
logging.disable(logging.CRITICAL)

import sqlite3
try:
    import pysqlite3
    sqlite3 = pysqlite3
except:
    pass

db_path = "indexes/nuru.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print("=== ALL TABLES ===")
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
for t in cur.fetchall():
    tname = t[0]
    try:
        cur.execute(f'SELECT COUNT(*) FROM "{tname}"')
        cnt = cur.fetchone()[0]
        print(f"  {tname}: {cnt} rows")
    except Exception as e:
        print(f"  {tname}: ERROR - {e}")

# documents table info  
try:
    cur.execute("PRAGMA table_info(documents)")
    cols = cur.fetchall()
    print("\n=== documents columns ===")
    for c in cols:
        print(f"  {c}")
except:
    print("\ndocuments table doesn't exist")

# Check indexed_files
print("\n=== INDEXED FILES (last 20) ===")
try:
    rows = conn.execute(
        "SELECT path, file_hash, indexed_at, file_size FROM indexed_files ORDER BY indexed_at DESC LIMIT 20"
    ).fetchall()
    # Also get total
    total = conn.execute("SELECT COUNT(*) FROM indexed_files").fetchone()[0]
    print(f"Total: {total}")
    for r in rows:
        path = str(r[0])[:90]
        h = str(r[1])[:12] if r[1] else "N/A"
        print(f"  {path} | {h} | {r[2]} | {r[3]} bytes")
except Exception as e:
    print(f"ERROR: {e}")

# Check doc_structured
print("\n=== DOC STRUCTURED (sources) ===")
try:
    rows = conn.execute("SELECT source, doc_type, SUBSTR(json_data,1,80), extracted_at FROM doc_structured ORDER BY source LIMIT 20").fetchall()
    print(f"Total: {len(rows)}")
    for r in rows:
        print(f"  {str(r[0])[:70]} | type={r[1]} | {r[2]} | {r[3]}")
except Exception as e:
    print(f"ERROR: {e}")

# Check cv_structured
print("\n=== CV STRUCTURED ===")
try:
    rows = conn.execute("SELECT source FROM cv_structured").fetchall()
    print(f"Total: {len(rows)}")
    for r in rows:
        print(f"  {r[0]}")
except Exception as e:
    print(f"ERROR: {e}")

conn.close()

# Now check chunking code for quality issues
print("\n\n=== CHUNKING ANALYSIS ===")
try:
    from src.rag.v2_chunking import HierarchicalChunkerV2
    print(f"HierarchicalChunkerV2 imported OK")
    print(f"Available profiles: {HierarchicalChunkerV2.detect_profile('test.docx')}")
    print(f"CV profile: {HierarchicalChunkerV2.detect_profile('CV_Leblanc_Bahiga.docx')}")
except Exception as e:
    print(f"ERROR: {e}")

# Check semantic router
print("\n\n=== SEMANTIC ROUTER ===")
try:
    from src.semantic_router import SemanticRouter, RAG_KEYWORDS
    print(f"SemanticRouter imported OK")
    print(f"RAG_KEYWORDS: {RAG_KEYWORDS[:20]}... ({len(RAG_KEYWORDS)} total)")
    
    # Check routing of test query
    from src.config import config
    router = SemanticRouter()
    
    # We can't call route directly since it's async and needs other deps
    # But we can check the keywords
    print(f"\nRAG_KEYWORDS sample: {RAG_KEYWORDS[:10]}")
    
    # Check if 'qui est' is handled
    print(f"'qui' in RAG_KEYWORDS: {'qui' in RAG_KEYWORDS}")
    print(f"'Leblanc' in RAG_KEYWORDS: {'Leblanc' in RAG_KEYWORDS}")
    
except ImportError as e:
    print(f"Import error: {e}")
except Exception as e:
    import traceback
    traceback.print_exc()

print("\n\n=== DIAGNOSTIC COMPLETE ===")
