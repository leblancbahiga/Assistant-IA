#!/usr/bin/env python3
"""Diagnostic V3 — check indexed files and document metadata."""
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

# indexed_files
print("=== INDEXED FILES ===")
cur.execute("PRAGMA table_info(indexed_files)")
print("Columns:", [(c[1], c[2]) for c in cur.fetchall()])

rows = conn.execute("SELECT * FROM indexed_files ORDER BY mtime DESC LIMIT 30").fetchall()
total = conn.execute("SELECT COUNT(*) FROM indexed_files").fetchone()[0]
print(f"Total: {total}")
for r in rows:
    fp = str(r[0])[:90]
    print(f"  {fp} | mtime={r[1]} | hash={str(r[2])[:12] if r[2] else 'N/A'}")

# Check doc_structured
print("\n=== DOC STRUCTURED ===")
try:
    cur.execute("PRAGMA table_info(doc_structured)")
    print("Columns:", [(c[1], c[2]) for c in cur.fetchall()])
    rows = conn.execute("SELECT * FROM doc_structured").fetchall()
    print(f"Rows: {len(rows)}")
    for r in rows:
        print(f"  {r}")
except Exception as e:
    print(f"ERROR: {e}")

# Check cv_structured
print("\n=== CV STRUCTURED ===")
try:
    cur.execute("PRAGMA table_info(cv_structured)")
    print("Columns:", [(c[1], c[2]) for c in cur.fetchall()])
    rows = conn.execute("SELECT * FROM cv_structured").fetchall()
    print(f"Rows: {len(rows)}")
    for r in rows:
        print(f"  {r}")
except Exception as e:
    print(f"ERROR: {e}")

# Check chunk_rowids for source analysis
print("\n=== CHUNK SOURCES (top 15) ===")
try:
    rows = conn.execute(
        "SELECT source, COUNT(*) as cnt FROM chunk_rowids GROUP BY source ORDER BY cnt DESC LIMIT 15"
    ).fetchall()
    print(f"Distinct sources: {len(rows)}")
    for r in rows:
        print(f"  {r[0][:70]}: {r[1]} chunks")
except Exception as e:
    print(f"ERROR: {e}")

# Check sqlite_sequence for metadata about which table has what
print("\n=== SQLITE SEQUENCE ===")
try:
    rows = conn.execute("SELECT * FROM sqlite_sequence").fetchall()
    for r in rows:
        print(f"  {r[0]}: seq={r[1]}")
except Exception as e:
    print(f"ERROR: {e}")

conn.close()

# Check spot light implementation
print("\n=== SPOTLIGHT SEARCH ===")
try:
    from src.rag.spotlight import SpotlightSearch
    ss = SpotlightSearch()
    print(f"SpotlightSearch: type={type(ss).__name__}")
    # Check what search returns for a simple query
    res = ss.search("Leblanc Bahiga", max_results=5)
    if res:
        print(f"  Found {len(res)} results")
        for r in res[:3]:
            print(f"  {r}")
    else:
        print("  No results")
except Exception as e:
    print(f"ERROR: {e}")

# Check the startup flow
print("\n=== STARTUP FLOW ===")
# Check main.py or nuru_core.py for how auto_index_loop starts
src_main = None
for candidate in ["main.py", "nuru_core.py", "__main__.py"]:
    p = os.path.join("src", candidate) if os.path.exists(os.path.join("src", candidate)) else candidate
    if os.path.exists(p):
        src_main = p
        print(f"Found: {p}")
        break

if src_main:
    with open(src_main) as f:
        content = f.read()
    # Find auto_index_loop references
    for i, line in enumerate(content.split('\n'), 1):
        if 'auto_index' in line.lower() or 'ingestion' in line.lower():
            print(f"  L{i}: {line.strip()}")

# Check retrieval quality by simulating a search
print("\n=== RETRIEVAL QUALITY CHECK ===")
try:
    from src.rag_engine import RAGEngine, RAGResult
    from src.config import config
    
    engine = RAGEngine()
    
    # Check if documents table exists
    conn2 = sqlite3.connect(db_path)
    tables = conn2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents'").fetchall()
    print(f"'documents' table exists: {len(tables) > 0}")
    conn2.close()
except Exception as e:
    print(f"ERROR: {e}")

print("\n=== DIAGNOSTIC COMPLETE ===")
