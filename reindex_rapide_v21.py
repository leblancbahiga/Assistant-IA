#!/usr/bin/env python3
"""
NURU V2.1 — Re-indexation RAPIDE et ciblée.
Ne scanne QUE les répertoires pertinents pour NURU (Documents/YARID, Documents/LEAD,
Documents/projets, Documents, etc.) avec profondeur limitée pour éviter les déchets.
"""
import sys, os, gc, asyncio, time, logging, gc
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Répertoires à scanner (pairs (base, max_depth)) ──
# Seulement ~/Documents/ — TOUS les fichiers NURU pertinents sont là.
# YARID, BEACCOM, LEAD, rapports, etc. sont sous Documents ou Documents/YARID/.
# Desktop et Downloads évités : fichiers transitoires, PDF lents, timeouts.
TARGETS = [
    (os.path.expanduser("~/Documents"), 2),  # Documents + 1 sous-niveau (YARID/, BEACCOM/)
]

# Extensions supportées
SUPPORTED = {".pdf", ".docx", ".txt", ".md", ".csv", ".json", ".doc", ".xls", ".xlsx"}
# Ignore les fichiers > 10MB (timeout fréquent à l'embedding)
MAX_FILE_SIZE = 10 * 1024 * 1024

def should_skip(dirpath):
    """Ignore les répertoires système et non pertinents."""
    skip_dirs = {".Trash", ".cache", "Library", "Applications", "Music", "Movies",
                 "Pictures", "Public", ".local", ".config", ".npm", ".cargo",
                 "node_modules", "__pycache__", ".git", ".Trashes", ".Spotlight-V100"}
    parts = dirpath.split(os.sep)
    return any(d in skip_dirs for d in parts)

def get_files_to_index():
    """Scanne les répertoires cibles et retourne la liste des fichiers."""
    all_files = []
    for base_dir, max_depth in TARGETS:
        if not os.path.isdir(base_dir):
            logger.info(f"  ✗ {base_dir} (inexistant)")
            continue
        
        base_depth = base_dir.rstrip(os.sep).count(os.sep)
        count = 0
        for root, dirs, files in os.walk(base_dir):
            # Skip dirs in place (évite d'entrer dans les répertoires système)
            dirs[:] = [d for d in dirs if not should_skip(os.path.join(root, d))]
            
            current_depth = root.rstrip(os.sep).count(os.sep) - base_depth
            if current_depth >= max_depth:
                dirs.clear()  # ne pas descendre plus profond
            
            for f in files:
                fp = os.path.join(root, f)
                ext = os.path.splitext(f)[1].lower()
                if ext in SUPPORTED and os.path.getsize(fp) <= MAX_FILE_SIZE:
                    all_files.append(fp)
                    count += 1
        logger.info(f"  ✓ {base_dir} → {count} fichiers (depth ≤ {max_depth})")
    
    all_files.sort()
    logger.info(f"\n📁 Total: {len(all_files)} fichiers à indexer")
    return all_files

async def reindex():
    from src.ingestion import IngestionEngine, SUPPORTED_EXTENSIONS
    from src.rag_engine import RAGEngine
    
    logger.info("=" * 50)
    logger.info("NURU V2.1 — RE-INDEXATION RAPIDE")
    logger.info("=" * 50)
    
    # Réparer DB d'abord
    logger.info("\n📦 Réparation DB...")
    engine = RAGEngine()
    conn = engine._get_conn()
    # Supprimer et recréer les tables d'index
    for table in ["chunks_fts", "chunk_rowids"]:
        try: conn.execute(f"DROP TABLE IF EXISTS {table}")
        except: pass
    try: conn.execute("DELETE FROM indexed_files")
    except: pass
    try: conn.execute("DELETE FROM chunks")
    except: pass
    conn.commit()
    engine._init_db()
    ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.close()
    logger.info(f"   integrity_check: {ok}")
    
    # Scanner les fichiers
    files = get_files_to_index()
    
    # Indexer
    ing = IngestionEngine()
    total = errors = 0
    t0 = time.time()
    
    for i, filepath in enumerate(files):
        try:
            await ing.index_file(filepath)
            total += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                logger.error(f"  ❌ {os.path.basename(filepath)[:70]}: {e}")
        
        if i % 10 == 0:
            try:
                import mlx.core as mx
                mx.clear_cache()
            except: pass
            gc.collect()
        
        if (i + 1) % 30 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (len(files) - i - 1) / rate if rate > 0 else 0
            logger.info(f"  [{i+1}/{len(files)}] {total} OK, {errors} err | "
                        f"{elapsed:.0f}s ({rate:.1f}/s) | ETA {eta:.0f}s")
        
        await asyncio.sleep(0.02)
    
    elapsed = time.time() - t0
    import sqlite3
    conn = engine._get_conn()
    n_chunks = conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
    n_files_idx = conn.execute("SELECT COUNT(*) FROM indexed_files").fetchone()[0]
    sizes = conn.execute("SELECT LENGTH(content) FROM chunks_fts").fetchall()
    if sizes:
        avg = sum(s[0] for s in sizes) / len(sizes)
        big = sum(1 for s in sizes if s[0] > 5000)
        logger.info(f"   Taille moyenne chunks: {avg:.0f} chars")
        logger.info(f"   Chunks > 5000: {big}")
    conn.close()
    
    logger.info(f"\n✅ RE-INDEXATION TERMINÉE")
    logger.info(f"   Temps: {elapsed:.0f}s")
    logger.info(f"   Fichiers: {total}, Erreurs: {errors}")
    logger.info(f"   Index: {n_files_idx} fichiers, {n_chunks} chunks")

if __name__ == "__main__":
    asyncio.run(reindex())
