#!/usr/bin/env python3
"""
NURU V10.3l — Réindexation massive avec le nouveau chunking V2.1
Corrige : chunks de 12K→6K chars max, BM25 scoring, batch embedding.
"""
import sys, os, logging, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reindex_v21")

import asyncio
import sqlite3
from pathlib import Path
from src.rag_engine import RAGEngine
from src.ingestion import IngestionEngine, SUPPORTED_EXTENSIONS

DB_PATH = Path("indexes/nuru.db")

async def force_reindex():
    # 1. VIDER l'index existant
    logger.info("🧹 Suppression de tous les chunks existants...")
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    
    conn.execute("DELETE FROM chunks")
    conn.execute("DELETE FROM chunks_fts")
    conn.execute("DELETE FROM indexed_files")
    # Réinitialiser les compteurs FTS5
    try:
        conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
    except:
        pass
    conn.commit()
    conn.close()
    logger.info("✅ Index vidé.")
    
    # 2. SCANNER les dossiers
    base_dirs = [
        Path.home() / "Documents",
        Path.home() / "Desktop",
        Path.home() / "Downloads",
    ]
    
    files_to_index = []
    for base_dir in base_dirs:
        if not base_dir.exists():
            continue
        logger.info(f"📂 Scan: {base_dir}")
        for root, _, files in os.walk(base_dir):
            for f in files:
                ext = Path(f).suffix.lower()
                if ext in SUPPORTED_EXTENSIONS:
                    files_to_index.append(os.path.join(root, f))
    
    logger.info(f"📊 {len(files_to_index)} fichiers trouvés.")
    
    # 3. INDEXER avec le nouveau chunking + batch embedding
    engine = IngestionEngine()
    total = len(files_to_index)
    ok, skip, err = 0, 0, 0
    
    for i, fpath in enumerate(files_to_index):
        try:
            await engine.index_file(fpath)
            ok += 1
        except asyncio.TimeoutError:
            logger.warning(f"⏱ Timeout: {fpath}")
            skip += 1
        except Exception as e:
            logger.error(f"❌ Erreur {fpath}: {e}")
            err += 1
        
        if (i+1) % 10 == 0:
            logger.info(f"⏳ Progression: {i+1}/{total} (OK={ok}, skip={skip}, err={err})")
    
    # 4. RAPPORT
    logger.info(f"\n{'='*50}")
    logger.info(f"✅ REINDEXATION TERMINÉE")
    logger.info(f"   Total:      {total}")
    logger.info(f"   Indexés:    {ok}")
    logger.info(f"   Skippés:    {skip}")
    logger.info(f"   Erreurs:    {err}")
    
    # 5. Vérifier le nombre de chunks
    conn = sqlite3.connect(str(DB_PATH))
    count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    fts_count = conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
    file_count = conn.execute("SELECT COUNT(*) FROM indexed_files").fetchone()[0]
    logger.info(f"📊 Chunks: {count}, FTS: {fts_count}, Fichiers: {file_count}")
    conn.close()

if __name__ == "__main__":
    asyncio.run(force_reindex())
