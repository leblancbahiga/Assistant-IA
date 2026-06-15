#!/usr/bin/env python3
"""
NURU V2.1 — Réparation DB + Re-indexation.
Démarche :
  1. Supprimer/recréer les tables d'index corrompues
  2. Vider indexed_files
  3. Re-indexer tous les documents avec le chunker corrigé
"""
import sys, os, gc, asyncio, time, logging, gc
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def repair_db():
    """Supprime et recrée les tables d'index via RAGEngine (extensions chargées)."""
    # On importe tardivement pour éviter les side effects
    from src.rag_engine import RAGEngine
    engine = RAGEngine()
    conn = engine._get_conn()
    
    # 1. Supprimer les anciennes tables d'index
    for table in ["chunks_fts", "chunk_rowids"]:
        try:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
            logger.info(f"  ✓ DROP TABLE {table}")
        except Exception as e:
            logger.warning(f"  ⚠ DROP {table}: {e}")
    
    # 2. Vider chunks (vec0 — DROP peut échouer si l'extension n'est pas chargée)
    try:
        conn.execute("DROP TABLE IF EXISTS chunks")
        logger.info("  ✓ DROP TABLE chunks")
    except Exception as e:
        logger.warning(f"  ⚠ DROP chunks impossible, vidage via DELETE: {e}")
        try:
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM chunks_fts")
            logger.info("  ✓ vidé chunks via DELETE")
        except Exception as e2:
            logger.error(f"  ❌ DELETE chunks: {e2}")
    
    # 3. Vider indexed_files
    try:
        conn.execute("DELETE FROM indexed_files")
        logger.info("  ✓ vidé indexed_files")
    except Exception as e:
        pass
    
    conn.commit()
    
    # 4. Recréer les tables (IF NOT EXISTS dans _init_db)
    engine._init_db()
    logger.info("  ✓ Tables recréées via _init_db()")
    
    # 5. Vérification
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    present = [t[0] for t in tables]
    for required in ["chunks", "chunks_fts", "indexed_files", "chunk_rowids"]:
        if required in present:
            logger.info(f"  ✓ {required} présente")
        else:
            logger.warning(f"  ✗ {required} MANQUANTE !")
    
    conn.close()
    return engine

async def reindex_one(engine, filepath):
    """Indexe un fichier via IngestionEngine (gère extraction, chunking, embedding)."""
    from src.ingestion import IngestionEngine
    ing = IngestionEngine()
    ing.rag = engine  # réutiliser le engine existant
    await ing.index_file(filepath)

async def main():
    logger.info("=" * 50)
    logger.info("NURU V2.1 — RÉPARATION + RE-INDEXATION")
    logger.info("=" * 50)
    
    # Phase 1 : Réparer la DB
    logger.info("\n📦 Phase 1: Réparation DB...")
    engine = repair_db()
    
    # Vérification rapide
    import sqlite3
    conn2 = engine._get_conn()
    ok = conn2.execute("PRAGMA integrity_check").fetchone()[0]
    conn2.close()
    logger.info(f"  integrity_check: {ok}")
    
    if ok != "ok":
        logger.error("❌ DB toujours corrompue après réparation !")
        return
    
    # Phase 2 : Scanner les fichiers
    from src.ingestion import SUPPORTED_EXTENSIONS
    from pathlib import Path
    
    dirs = [
        Path.home() / "Documents",
        Path.home() / "Desktop",
        Path.home() / "Downloads",
    ]
    
    all_files = []
    for base_dir in dirs:
        if not base_dir.exists():
            continue
        for root, _, files in os.walk(base_dir):
            for f in files:
                if any(f.lower().endswith(e) for e in SUPPORTED_EXTENSIONS):
                    all_files.append(os.path.join(root, f))
    
    logger.info(f"\n📁 Phase 2: {len(all_files)} fichiers à (ré)indexer")
    
    total = errors = 0
    t0 = time.time()
    
    for i, filepath in enumerate(all_files):
        try:
            await reindex_one(engine, filepath)
            total += 1
        except Exception as e:
            logger.error(f"  ❌ {os.path.basename(filepath)}: {e}")
            errors += 1
        
        # GC + MLX cache clear périodique
        if i % 10 == 0:
            try:
                import mlx.core as mx
                mx.clear_cache()
            except:
                pass
            gc.collect()
        
        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (len(all_files) - i - 1) / rate if rate > 0 else 0
            logger.info(f"  [{i+1}/{len(all_files)}] {total} OK, {errors} err, "
                        f"{elapsed:.0f}s ({rate:.1f}/s), ETA {eta:.0f}s")
        
        await asyncio.sleep(0.05)
    
    elapsed = time.time() - t0
    conn3 = engine._get_conn()
    n_chunks = conn3.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
    n_files_idx = conn3.execute("SELECT COUNT(*) FROM indexed_files").fetchone()[0]
    
    # Stats de taille de chunks
    sizes = conn3.execute("SELECT LENGTH(content) FROM chunks_fts").fetchall()
    if sizes:
        avg_sz = sum(s[0] for s in sizes) / len(sizes)
        max_sz = max(s[0] for s in sizes)
        big = sum(1 for s in sizes if s[0] > 5000)
        logger.info(f"\n  Taille moyenne chunks: {avg_sz:.0f} chars")
        logger.info(f"  Max chunk: {max_sz} chars")
        logger.info(f"  Chunks > 5000: {big}")
    
    conn3.close()
    
    logger.info(f"\n✅ TERMINÉ")
    logger.info(f"   Fichiers: {total}, Erreurs: {errors}")
    logger.info(f"   Chunks: {n_chunks}, Fichiers indexés: {n_files_idx}")
    logger.info(f"   Temps: {elapsed:.0f}s")
    
    # Flag de succès
    with open("/tmp/nuru_reindex_ok", "w") as f:
        f.write(f"ok={ok}\ntotal={total}\nerrors={errors}\nchunks={n_chunks}\nfiles={n_files_idx}\n")

if __name__ == "__main__":
    asyncio.run(main())
