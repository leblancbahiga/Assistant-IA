"""Explorer la base RAG pour génération dataset LoRA."""
import sqlite3

db = sqlite3.connect("data/nuru_rag.db")
cur = db.cursor()

# Tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [row[0] for row in cur.fetchall()]
print("Tables:", tables)

# Chunks
cur.execute("SELECT COUNT(*) FROM chunks;")
n_chunks = cur.fetchone()[0]
print(f"\nChunks: {n_chunks}")

# Sources uniques
cur.execute("SELECT DISTINCT source FROM chunks ORDER BY source;")
sources = [row[0] for row in cur.fetchall()]
print(f"\nSources distinctes ({len(sources)}):")
for i, s in enumerate(sources, 1):
    print(f"  {i:3d}. {s[:90]}")

# Distribution par source
print("\nDistribution par source:")
cur.execute("SELECT source, COUNT(*) FROM chunks GROUP BY source ORDER BY COUNT(*) DESC LIMIT 20;")
for source, count in cur.fetchall():
    print(f"  {count:4d}x  {source[:80]}")

# Échantillon de contenus
print("\nÉchantillons de contenus (5):")
cur.execute("SELECT id, source, content FROM chunks ORDER BY RANDOM() LIMIT 5;")
for cid, source, content in cur.fetchall():
    print(f"\n--- id={cid}, source={source[:60]} ---")
    print(content[:300])

# Vérifier la longueur moyenne des chunks
cur.execute("SELECT AVG(LENGTH(content)) FROM chunks;")
avg_len = cur.fetchone()[0]
cur.execute("SELECT MIN(LENGTH(content)), MAX(LENGTH(content)) FROM chunks;")
min_len, max_len = cur.fetchone()
print(f"\nLongueur chunks: min={min_len}, max={max_len}, moy={avg_len:.0f} caractères")

# chunk_vectors
cur.execute("SELECT COUNT(*) FROM chunk_vectors;")
n_vectors = cur.fetchone()[0]
print(f"\nVecteurs stockés: {n_vectors}")

db.close()
print("\n✅ Exploration terminée.")
