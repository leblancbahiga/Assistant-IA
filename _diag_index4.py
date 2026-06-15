#!/usr/bin/env python3
"""Check which documents are indexed vs missing."""
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

print("=== ALL INDEXED FILES ===")
rows = conn.execute("SELECT filepath FROM indexed_files ORDER BY filepath").fetchall()
total = len(rows)
print(f"Total: {total}")
for r in rows:
    print(f"  {r[0]}")

print("\n=== CHUNK SOURCES (from chunk_rowids) ===")
rows = conn.execute(
    "SELECT source, COUNT(*) as cnt FROM chunk_rowids GROUP BY source ORDER BY source"
).fetchall()
print(f"Unique sources: {len(rows)}")
for r in rows:
    print(f"  {r[0]}: {r[1]} chunks")

# Check what documents are in YARID folder
print("\n=== YARID DOCUMENTS ===")
rows = conn.execute(
    "SELECT filepath FROM indexed_files WHERE filepath LIKE '%YARID%' ORDER BY filepath"
).fetchall()
print(f"Indexed YARID files: {len(rows)}")
for r in rows:
    print(f"  {r[0]}")

# Check what YARID files exist but are NOT indexed
print("\n=== YARID FILES ON DISK vs INDEXED ===")
import glob
yarid_dir = os.path.expanduser("~/Documents/YARID/")
if os.path.exists(yarid_dir):
    for f in sorted(os.listdir(yarid_dir)):
        fpath = os.path.join(yarid_dir, f)
        if os.path.isfile(fpath) and any(f.lower().endswith(e) for e in ['.pdf', '.docx', '.txt', '.md', '.csv', '.json']):
            indexed = conn.execute(
                "SELECT 1 FROM indexed_files WHERE filepath = ?", (fpath,)
            ).fetchone()
            status = "✅ INDEXED" if indexed else "❌ NOT INDEXED"
            print(f"  {status}: {f}")

# Check specific files from recent conversation
print("\n=== SPECIFIC FILES CHECK ===")
checks = [
    "Sustainable -Agriculture Monitoring tool.docx",
    "CV Leblanc",
    "Leblanc Bahiga",
]
for check in checks:
    rows = conn.execute(
        "SELECT filepath FROM indexed_files WHERE filepath LIKE ?", (f"%{check}%",)
    ).fetchall()
    if rows:
        for r in rows:
            print(f"  ✅ FOUND '{check}': {r[0]}")
    else:
        print(f"  ❌ NOT FOUND '{check}' in indexed_files")
    
    # Also check chunk_rowids
    rows2 = conn.execute(
        "SELECT source FROM chunk_rowids WHERE source LIKE ?", (f"%{check}%",)
    ).fetchall()
    if rows2:
        for r in rows2:
            print(f"  ✅ IN CHUNKS: {r[0]}")
    else:
        print(f"  ❌ NOT IN CHUNKS '{check}'")

conn.close()
