#!/usr/bin/env python3
"""Quick DB check — no vec0 needed."""
import sqlite3, sys
# Do NOT import pysqlite3 — it conflicts with vec0

db = "indexes/nuru.db"

# Use plain sqlite3 (FTS5 is built into macOS sqlite3)
conn = sqlite3.connect(db)

# Tables exist?
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
print("=== TABLES ===")
for t in tables:
    print(f"  {t[0]}")

# indexed_files count
n_files = conn.execute("SELECT COUNT(*) FROM indexed_files").fetchone()[0]
print(f"\nFichiers indexés: {n_files}")

# FTS entries
n_fts = conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
print(f"FTS entries: {n_fts}")

# chunk_rowids
n_rowids = conn.execute("SELECT COUNT(*) FROM chunk_rowids").fetchone()[0]
print(f"chunk_rowids: {n_rowids}")

# FTS5 BM25 test (works with plain sqlite3 on macOS)
print(f"\n=== FTS BM25 SCORES ===")
try:
    rows = conn.execute(
        "SELECT source, rank, LENGTH(content) FROM chunks_fts "
        "WHERE content MATCH 'sustainable OR agriculture OR training OR YARID' "
        "ORDER BY rank LIMIT 8"
    ).fetchall()
    for r in rows:
        score = -r[1] / (1.0 + -r[1]) if r[1] < 0 else 0
        print(f"  score={score:.3f} | rank={r[1]:.1f} | {r[2]:>6} chars | {r[0][:70]}")
except Exception as e:
    print(f"FTS BM25 error (expected with vec0): {e}")

# Check Sustainable Agriculture
check = conn.execute(
    "SELECT source FROM indexed_files WHERE source LIKE '%Sustainable%'"
).fetchall()
print(f"\n=== SUSTAINABLE AGRICULTURE INDEXED? ===")
for r in check:
    print(f"  YES: {r[0]}")
if not check:
    print(f"  Not in indexed_files")

# Show sample indexed files
print(f"\n=== SAMPLE INDEXED FILES (last 10) ===")
samples = conn.execute(
    "SELECT source, last_modified FROM indexed_files ORDER BY last_indexed DESC LIMIT 10"
).fetchall()
for r in samples:
    print(f"  {r[0][:80]} | mtime={r[1]}")

# Check FTS5 support
print(f"\n=== SQLITE VERSION ===")
print(f"  sqlite3.sqlite_version: {sqlite3.sqlite_version}")
print(f"  FTS5 available: {sqlite3.sqlite_version_info >= (3, 9, 0)}")

conn.close()
