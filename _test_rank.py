#!/usr/bin/env python3
"""Test FTS5 rank column for BM25 scoring."""
import sqlite3, sys
try:
    import pysqlite3
    sqlite3 = pysqlite3
except:
    pass

db = "indexes/nuru.db"
conn = sqlite3.connect(db)

# Test rank column
print("=== FTS5 RANK COLUMN ===")
try:
    rows = conn.execute(
        "SELECT content, source, rank FROM chunks_fts WHERE content MATCH ? ORDER BY rank LIMIT 5",
        ['"agriculture" OR "sustainable" OR "training"']
    ).fetchall()
    print(f"RANK works! {len(rows)} results")
    for i, r in enumerate(rows):
        score = 1.0 / (1.0 + float(r[2]))
        print(f"  [{i+1}] rank={r[2]:.2f} → score={score:.2f} | {r[1][:60]}")
except Exception as e:
    print(f"RANK failed: {e}")

# Try with ORDER BY rank but without rank in SELECT
print("\n=== ORDER BY rank only ===")
try:
    rows2 = conn.execute(
        "SELECT content, source FROM chunks_fts WHERE content MATCH ? ORDER BY rank LIMIT 5",
        ['"agriculture" OR "sustainable" OR "training"']
    ).fetchall()
    print(f"ORDER BY RANK works! {len(rows2)} results")
    for i, r in enumerate(rows2):
        print(f"  [{i+1}] {r[1][:60]}")
except Exception as e:
    print(f"ORDER BY RANK failed: {e}")

# Try with sqlite3's own RECOVER built-in
print("\n=== bm25 test alternative ===")
try:
    rows3 = conn.execute(
        "SELECT content, source, rank FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT 5",
        ['"agriculture" OR "sustainable"']
    ).fetchall()
    print(f"chunks_fts MATCH works! {len(rows3)} results")
    for i, r in enumerate(rows3):
        score = 1.0 / (1.0 + float(r[2]))
        print(f"  [{i+1}] rank={r[2]:.4f} → score={score:.4f} | {r[1][:60]}")
except Exception as e:
    print(f"chunks_fts MATCH failed: {e}")

# Try simpler query
print("\n=== Simple query test ===")
try:
    rows4 = conn.execute(
        "SELECT content, source, rank FROM chunks_fts WHERE content MATCH 'agriculture OR sustainable' ORDER BY rank LIMIT 5"
    ).fetchall()
    print(f"Simple MATCH works! {len(rows4)} results")
    for i, r in enumerate(rows4):
        score = 1.0 / (1.0 + abs(float(r[2]))) if r[2] else 0
        print(f"  [{i+1}] rank={r[2]:.4f} | {r[1][:60]}")
except Exception as e:
    print(f"Simple MATCH failed: {e}")
    import traceback
    traceback.print_exc()

conn.close()
