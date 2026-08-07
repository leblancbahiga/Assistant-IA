#!/usr/bin/env python3
"""Ré-indexation V17 : Qwen3-0.6B (1024-dim) + Hybride.
Skip extraction cloud, fichiers temp, dossiers système.
"""
import asyncio, logging, os, sys, time, hashlib
from pathlib import Path

os.environ["NURU_GROQ_KEY"] = ""

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Purge PYTHONPATH Hermes (conflit PIL Python 3.11/3.13) ──
_HERMES_MARKERS = ('.hermes/hermes-agent',)
sys.path = [p for p in sys.path if not any(m in p for m in _HERMES_MARKERS)]

# ── V16 FIX : Couper les connexions HuggingFace Hub ──
os.environ["HF_HUB_OFFLINE"] = "1"

from src.ingestion import IngestionEngine, SUPPORTED_EXTENSIONS
from src.rag_engine import RAGEngine

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger('reindex')
logger.setLevel(logging.INFO)

TEMP_PREFIXES = ('~$', '.~lock.')
EXCLUDED_DIRS = {'.venv', 'node_modules', '.git', '__pycache__', '.hermes',
                 'indexes', '.hg', '.svn', '.egg-info', 'dist', 'build',
                 'chromadb', '.nuru', 'dataset', 'backup_*', '.Trash', 'Library'}

def is_usable_dir(d: str) -> bool:
    """Filtre les dossiers exclus."""
    name = os.path.basename(d)
    if name.startswith('.'):
        return False
    if name in EXCLUDED_DIRS:
        return False
    if any(_.startswith('.') for _ in d.split(os.sep)):
        return False
    return True

def is_text_present(parsed_text: str) -> bool:
    """Vérifie que le texte parsé a du contenu significatif."""
    return bool(parsed_text and parsed_text.strip())

async def reindex():
    import numpy as np
    from src.rag.v2_chunking import HierarchicalChunkerV2
    
    ing = IngestionEngine()
    re = RAGEngine()
    
    # Dossiers à indexer (Documents + Desktop pour les CVs personnels)
    dirs = [
        Path("/Users/leblancbahiga/Documents"),
        Path("/Users/leblancbahiga/Desktop"),
    ]
    
    t0 = time.time()
    total = 0
    errors = 0
    skipped = 0
    empty = 0
    
    for base in dirs:
        if not base.exists():
            logger.warning(f"Dossier introuvable: {base}")
            continue
        
        for root, dirnames, files in os.walk(base):
            # Filtrer les dossiers exclus sur place
            dirnames[:] = [d for d in dirnames if is_usable_dir(os.path.join(root, d))]
            
            for fname in sorted(files):
                if fname.startswith(TEMP_PREFIXES):
                    continue
                
                ext = os.path.splitext(fname)[1].lower()
                if ext not in SUPPORTED_EXTENSIONS:
                    continue
                
                fp = os.path.join(root, fname)
                total += 1
                
                try:
                    file_hash = ing.compute_sha256(fp)
                    if re.is_file_up_to_date(fp, 0, file_hash):
                        skipped += 1
                        continue
                    
                    # Parsing avec timeout
                    text = ""
                    try:
                        text = await asyncio.wait_for(
                            asyncio.get_event_loop().run_in_executor(None, ing._parse_file, fp),
                            timeout=25
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"⏱ Timeout: {fname}")
                        errors += 1
                        continue
                    except Exception as e:
                        logger.warning(f"❌ Parse: {fname}: {e}")
                        errors += 1
                        continue
                    
                    if not is_text_present(text):
                        empty += 1
                        continue
                    
                    # Chunking
                    profile = HierarchicalChunkerV2.detect_profile(fname)
                    chunker = HierarchicalChunkerV2(profile=profile)
                    chunks = list(chunker.chunk(text, source=fname, doc_title=fname))
                    
                    if not chunks:
                        empty += 1
                        continue
                    
                    # Embedding en batch
                    batch_size = 32
                    all_emb = []
                    for i in range(0, len(chunks), batch_size):
                        batch = [c.content for c in chunks[i:i+batch_size]]
                        be = await ing.embedder.embed(batch, is_query=False)
                        if be is not None and len(be) > 0:
                            all_emb.append(be)
                        await asyncio.sleep(0.01)
                    
                    if not all_emb:
                        continue
                    
                    all_embeddings = np.concatenate(all_emb) if len(all_emb) > 1 else all_emb[0]
                    
                    # Construction des chunks
                    chunk_dicts = []
                    for i, c in enumerate(chunks):
                        chunk_dicts.append({
                            "content": c.content,
                            "source": fname,
                            "embedding": all_embeddings[i] if i < len(all_embeddings) else None,
                            "date": "",
                            "title": c.section_title or c.doc_title or fname,
                            "level": c.level,
                        })
                    
                    re.add_chunks(chunk_dicts)
                    re.mark_file_indexed(fp, 0, file_hash)
                    
                    # WikiWriter
                    try:
                        from src.nuru_brain import WikiWriter
                        wiki = WikiWriter()
                        for c in chunk_dicts:
                            wiki.write_chunk(
                                content=c["content"], source=fname,
                                chunk_id=hashlib.md5(c["content"].encode()).hexdigest()[:8],
                                date="",
                                tags=[c.get("title", ""), str(c.get("level", ""))],
                            )
                    except Exception:
                        pass
                    
                    if total % 25 == 0:
                        elapsed = time.time() - t0
                        rate = total / elapsed if elapsed > 0 else 0
                        logger.info(f"📊 [{total} scans] {elapsed:.0f}s | {rate:.1f}/s | err:{errors} skip:{skipped}")
                
                except Exception as e:
                    logger.warning(f"❌ Fatal: {fname}: {e}")
                    errors += 1
    
    elapsed = time.time() - t0
    import sqlite3
    db = sqlite3.connect("indexes/nuru.db")
    cnt_files = db.execute("SELECT COUNT(*) FROM indexed_files").fetchone()[0]
    cnt_chunks = db.execute("SELECT COUNT(*) FROM chunk_vectors").fetchone()[0]
    db.close()
    
    print(f"\n{'='*50}")
    print(f"RÉ-INDEXATION TERMINÉE")
    print(f"  Fichiers scannés: {total}")
    print(f"  Fichiers indexés: {cnt_files}")
    print(f"  Chunks (1024-dim): {cnt_chunks}")
    print(f"  Skippés (déjà OK): {skipped}")
    print(f"  Erreurs: {errors}")
    print(f"  Vides: {empty}")
    print(f"  Temps: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"{'='*50}")

if __name__ == "__main__":
    asyncio.run(reindex())
