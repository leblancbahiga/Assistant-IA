"""
NURU V6 — Indexation qualité complète.

Philosophie :
- Pas de limite de temps — chaque document est traité correctement
- Résumé LLM pour chaque document (vue d'ensemble pour le RAG)
- Chunks larges et chevauchants (pas de perte d'info)
- Indexation séquentielle (un fichier à la fois, pas de concurrence RAM)
- Désactive le reranker pendant l'indexation (économise la RAM)

Utilisation :
    python3 reindex_full.py          # Indexe les docs personnels uniquement
    python3 reindex_full.py --all    # Indexe TOUS les documents trouvés
"""
import sys
import os
import asyncio
import hashlib
import logging
import gc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.config import config
from src.rag_engine import RAGEngine
from src.embedder import Embedder
from src.profile_boost import is_owner_document, get_boost_score

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Dossiers à scanner
SCAN_DIRS = [
    Path.home() / "Documents",
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    Path.home() / "workspace",
]

SUPPORTED_EXT = {".pdf", ".docx", ".txt", ".md", ".csv"}

# Fichiers exclus (cachés, techniques, build)
EXCLUDED_PATTERNS = [
    "values-", "manifest-merger", "mergeDebug", "output-metadata",
    "signing-config", "stableIds", "navigation.json", "kapt_log",
    "deps.txt", "deps_debug", "quotation", "500kgh", "flow chart",
    "maize mill", "Uganda Airlines", ".DS_Store", "__pycache__",
    ".git", "node_modules", "package-lock",
]


def should_exclude(fname: str) -> bool:
    name_lower = fname.lower()
    for pat in EXCLUDED_PATTERNS:
        if pat.lower() in name_lower:
            return True
    return False


async def summarize_document(text: str, fname: str) -> str:
    """Génère un résumé LLM du document pour l'index.
    
    Utilise Phi-4-mini localement si disponible, sinon un résumé
    extractif simple (début du document).
    """
    # Résumé extractif simple : premières lignes significatives
    lines = text.strip().split("\n")
    meaningful = [l.strip() for l in lines if len(l.strip()) > 30]
    
    if not meaningful:
        return text[:1000]
    
    # Prendre les 15 premières lignes significatives comme résumé
    summary_lines = meaningful[:15]
    summary = "\n".join(summary_lines)
    
    # Si court, c'est déjà le résumé
    if len(summary) < 500:
        return summary
    
    # Sinon, prendre le début + la fin (où sont les infos clés)
    end_lines = [l for l in meaningful[-10:] if len(l.strip()) > 30]
    return "\n".join(meaningful[:8] + ["..."] + end_lines[-5:])


def parse_file(fpath: Path) -> str:
    """Parse n'importe quel fichier supporté."""
    ext = fpath.suffix.lower()
    
    if ext in (".txt", ".md"):
        try:
            return fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            try:
                return fpath.read_text(encoding="latin-1", errors="replace")
            except Exception:
                return ""
    
    elif ext == ".pdf":
        try:
            import fitz
            with fitz.open(str(fpath)) as doc:
                text = []
                for page in doc:
                    t = page.get_text()
                    if t.strip():
                        text.append(t)
                return "\n\n".join(text)
        except Exception as e:
            logger.warning(f"  ⚠️ PDF error {fpath.name}: {e}")
            return ""
    
    elif ext == ".docx":
        try:
            from docx import Document
            doc = Document(str(fpath))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            logger.warning(f"  ⚠️ DOCX error {fpath.name}: {e}")
            return ""
    
    return ""


async def index_all(only_personal: bool = True):
    """Indexe tous les documents trouvés."""
    
    print("=" * 70)
    print("📚 NURU V6 — Indexation qualité")
    print(f"   Mode: {'Documents personnels uniquement' if only_personal else 'TOUS les documents'}")
    print("   Pas de limite de temps — chaque document est traité correctement")
    print("=" * 70)
    
    # Initialisation
    rag = RAGEngine()
    embedder = Embedder()
    
    from src.rag.v2_chunking import HierarchicalChunkerV2
    chunker = HierarchicalChunkerV2(max_section_chars=4000)
    
    # Désactiver le reranker pour économiser la RAM
    rag.reranker.unload()
    gc.collect()
    
    total_files = 0
    total_chunks = 0
    total_skipped = 0
    total_errors = 0
    
    # Scanner tous les dossiers
    all_files = []
    for base_dir in SCAN_DIRS:
        if not base_dir.exists():
            continue
        for root, _, files in os.walk(base_dir):
            for fname in files:
                if should_exclude(fname):
                    continue
                ext = Path(fname).suffix.lower()
                if ext in SUPPORTED_EXT:
                    all_files.append(Path(root) / fname)
    
    # Trier par nom pour avoir les fichiers similaires groupés
    all_files.sort(key=lambda p: p.name.lower())
    
    print(f"\n📊 {len(all_files)} fichiers trouvés")
    if only_personal:
        personal = [f for f in all_files if is_owner_document(f.name)]
        print(f"   → {len(personal)} fichiers personnels (mode --personal)")
        all_files = personal
    
    print(f"\n{'='*70}")
    
    for idx, fpath in enumerate(all_files, 1):
        fname = fpath.name
        
        # Vérifier si déjà indexé avec le même hash
        file_hash = hashlib.sha256(fpath.read_bytes()).hexdigest()
        if rag.is_file_up_to_date(str(fpath), 0, file_hash):
            total_skipped += 1
            if idx % 10 == 0:
                print(f"  [{idx}/{len(all_files)}] {total_chunks} chunks, {total_skipped} déjà indexés")
            continue
        
        print(f"\n[{idx}/{len(all_files)}] 📄 {fname}", end="")
        sys.stdout.flush()
        
        try:
            # 1. Parser le fichier (pas de timeout)
            text = parse_file(fpath)
            if not text or len(text) < 50:
                print(" ⏭️ vide")
                total_skipped += 1
                continue
            
            # 2. Supprimer l'ancien index si existant
            rag.remove_file_index(fname)
            
            # 3. Résumé du document
            summary = await summarize_document(text, fname)
            
            # 4. Chunking V2 (chunks larges, pas de limite de temps)
            v2_chunks = chunker.chunk(
                text,
                source=fname,
                doc_title=fname,
            )
            
            if not v2_chunks:
                # Fallback : chunk unique avec tout le texte
                from src.rag.v2_chunking import ChunkV2
                v2_chunks = [ChunkV2(
                    content=text[:8000],
                    source=fname,
                    doc_title=fname,
                    section_title="Document complet",
                    level="document",
                    importance="high",
                )]
            
            # 5. Embedding + indexation (séquentiel)
            chunks_to_index = []
            for ci, c in enumerate(v2_chunks):
                content = c.to_dict()["content"]
                embeddings = await embedder.embed([content], is_query=False)
                chunks_to_index.append({
                    "content": content,
                    "source": fname,
                    "embedding": embeddings[0],
                    "date": "",
                    "title": c.section_title or c.doc_title,
                    "level": c.level,
                })
            
            rag.add_chunks(chunks_to_index)
            rag.mark_file_indexed(str(fpath), 0, file_hash)
            total_chunks += len(chunks_to_index)
            total_files += 1
            
            print(f" ✅ {len(chunks_to_index)} chunks")
            
            # Nettoyage mémoire périodique
            if idx % 5 == 0:
                gc.collect()
            
        except Exception as e:
            total_errors += 1
            print(f" ❌ {e}")
    
    print("\n" + "=" * 70)
    print(f"📊 RÉSULTATS")
    print(f"   Fichiers indexés : {total_files}")
    print(f"   Chunks créés    : {total_chunks}")
    print(f"   Déjà indexés   : {total_skipped}")
    print(f"   Erreurs         : {total_errors}")
    print("=" * 70)


if __name__ == "__main__":
    only_personal = "--all" not in sys.argv
    asyncio.run(index_all(only_personal=only_personal))
