#!/usr/bin/env python3
"""Quick DB check + retrieval test (no embedder needed)."""
import sqlite3, sys, os
try:
    import pysqlite3
    sqlite3 = pysqlite3
except:
    pass

db = "indexes/nuru.db"
conn = sqlite3.connect(db)

# Stats
n_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
n_fts = conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
n_files = conn.execute("SELECT COUNT(*) FROM indexed_files").fetchone()[0]
avg = conn.execute("SELECT AVG(LENGTH(content)) FROM chunks").fetchone()[0] or 0
big = conn.execute("SELECT COUNT(*) FROM chunks WHERE LENGTH(content) > 5000").fetchone()[0]
max_c = conn.execute("SELECT MAX(LENGTH(content)) FROM chunks").fetchone()[0] or 0
short = conn.execute("SELECT COUNT(*) FROM chunks WHERE LENGTH(content) < 100").fetchone()[0]

print(f"=== INDEX STATS ===")
print(f"Fichiers indexés: {n_files}")
print(f"Total chunks: {n_chunks}")
print(f"Taille moyenne: {avg:.0f} chars")
print(f"Max chunk: {max_c} chars")
print(f"Chunks > 5000: {big}")
print(f"Chunks < 100: {short}")

# Check if Sustainable Agriculture is now indexed
check = conn.execute(
    "SELECT source FROM indexed_files WHERE source LIKE '%Sustainable%'"
).fetchall()
print(f"\n=== SUSTAINABLE AGRICULTURE INDEXED? ===")
for r in check:
    print(f"  YES: {r[0]}")
if not check:
    print("  Not found in indexed_files")
    # Check if at least chunks exist for this file
    check2 = conn.execute(
        "SELECT source FROM chunks WHERE source LIKE '%Sustainable%' LIMIT 3"
    ).fetchall()
    if check2:
        print(f"  Found in chunks: {[r[0] for r in check2]}")

# Show FTS scores for a query
print(f"\n=== FTS BM25 SCORES ===")
rows = conn.execute(
    "SELECT source, rank, LENGTH(content) FROM chunks_fts "
    "WHERE content MATCH 'sustainable OR agriculture OR training OR YARID' "
    "ORDER BY rank LIMIT 8"
).fetchall()
for r in rows:
    score = -r[1] / (1.0 + -r[1]) if r[1] < 0 else 0
    print(f"  score={score:.3f} | rank={r[1]:.1f} | {r[2]:>6} chars | {r[0][:70]}")
if not rows:
    print("  (no results)")

# Show chunk size distribution
print(f"\n=== CHUNK SIZE DISTRIBUTION ===")
dist = conn.execute("""
    SELECT 
        CASE 
            WHEN LENGTH(content) < 200 THEN '0-200'
            WHEN LENGTH(content) < 500 THEN '200-500'
            WHEN LENGTH(content) < 1000 THEN '500-1k'
            WHEN LENGTH(content) < 2000 THEN '1k-2k'
            WHEN LENGTH(content) < 4000 THEN '2k-4k'
            WHEN LENGTH(content) < 10000 THEN '4k-10k'
            ELSE '10k+'
        END as bucket,
        COUNT(*) as count
    FROM chunks 
    GROUP BY bucket
    ORDER BY MIN(LENGTH(content))
""").fetchall()
for r in dist:
    print(f"  {r[0]}: {r[1]}")

conn.close()
