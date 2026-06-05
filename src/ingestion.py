import os
import asyncio
import logging
import hashlib
from pathlib import Path
from typing import List, Optional
import fitz  # PyMuPDF
from docx import Document
from src.config import config
from src.rag_engine import RAGEngine
from src.embedder import Embedder

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv", ".json"}


class IngestionEngine:
    """Moteur d'ingestion de documents pour le RAG V4."""
    
    def __init__(self):
        self.rag = RAGEngine()
        self.embedder = Embedder()

    def _parse_file(self, file_path: str) -> str:
        """Extrait le texte brut d'un fichier selon son extension."""
        path = Path(file_path)
        ext = path.suffix.lower()
        text = ""
        
        try:
            if ext == ".pdf":
                with fitz.open(str(path)) as doc:
                    for page in doc:
                        text += page.get_text()
            elif ext == ".docx":
                doc = Document(str(path))
                text = "\n".join([p.text for p in doc.paragraphs])
            elif ext in [".txt", ".md"]:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
            elif ext == ".csv":
                import csv
                with open(path, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    text = "\n".join(["," .join(row) for row in reader])
            elif ext == ".json":
                with open(path, "r", encoding="utf-8") as f:
                    import json as j
                    data = j.load(f)
                    text = j.dumps(data, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erreur lors du parsing de {file_path} : {e}")
            
        return text

    def compute_sha256(self, filepath: str) -> str:
        """Calcule le hash SHA256 d'un fichier pour détecter les vrais changements."""
        hasher = hashlib.sha256()
        try:
            with open(filepath, 'rb') as f:
                # Lecture par morceaux pour les gros fichiers
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.error(f"Erreur hashage {filepath}: {e}")
            return ""

    async def index_file(self, filepath: str):
        """Parse et indexe un fichier unique avec timeout de sécurité."""
        try:
            # Timeout critique de 30s par document (V4)
            async with asyncio.timeout(30):
                file_hash = self.compute_sha256(filepath)
                if not file_hash:
                    return

                # On vérifie le hash au lieu de mtime
                if self.rag.is_file_up_to_date(filepath, 0, file_hash):
                    return

                logger.info(f"Indexing: {filepath}")
                text = self._parse_file(filepath)
                if not text:
                    return

                # V4.5 Phase 2 : Chunking sémantique contextuel
                from src.rag.chunking import SemanticChunker
                chunker = SemanticChunker()
                metadata = {"title": os.path.basename(filepath), "source": filepath}
                semantic_chunks = chunker.chunk(text, source=os.path.basename(filepath),
                                                metadata=metadata)

                # NURU V6 : Chunking hiérarchique V2 (plus robuste, chunks plus gros)
                from src.rag.v2_chunking import HierarchicalChunkerV2
                v2_chunker = HierarchicalChunkerV2()
                v2_chunks = v2_chunker.chunk(
                    text,
                    source=os.path.basename(filepath),
                    doc_title=os.path.basename(filepath),
                )
                
                # Utiliser V2 comme source principale, V1 comme fallback
                primary_chunks = v2_chunks if v2_chunks else semantic_chunks

                chunks = []
                for c in primary_chunks:
                    # V2 : le contenu inclut déjà le contexte (résumé, section, importance)
                    content = c.to_dict()["content"]
                    # On embed le texte enrichi
                    embedding = await self.embedder.embed(content, is_query=False)
                    chunks.append({
                        "content": content,
                        "source": os.path.basename(filepath),
                        "embedding": embedding[0],
                        "date": "",
                        "title": c.section_title or c.doc_title,
                        "level": c.level,
                    })

                self.rag.add_chunks(chunks)
                self.rag.mark_file_indexed(filepath, 0, file_hash)
                # NURU V6 : Dual-Write — chaque chunk aussi dans ~/Nuru_Brain/
                try:
                    from src.nuru_brain import WikiWriter
                    wiki = WikiWriter()
                    source_name = os.path.basename(filepath)
                    for c in chunks:  # V6 Pas de limite — tous les chunks dans le Wiki
                        wiki.write_chunk(
                            content=c["content"],
                            source=source_name,
                            chunk_id=hashlib.md5(c["content"].encode()).hexdigest()[:8],
                            date="",
                            tags=[c.get("title", ""), c.get("level", "")],
                        )
                except Exception:
                    pass  # WikiWriter est optionnel, ne pas casser l'ingestion
                logger.info(f"✅ Ingestion OK: {os.path.basename(filepath)}")

        except asyncio.TimeoutError:
            logger.error(f"⏱ Timeout sur {filepath} (>30s).")
        except Exception as e:
            logger.error(f"❌ Erreur critique {filepath}: {e}")

    async def auto_index_loop(self):
        """Boucle d'auto-indexation V4 : scan récursif et hachage."""
        dirs_to_index = [
            Path.home() / "Documents",
            Path.home() / "Desktop",
            Path.home() / "Downloads"
        ]
        
        while True:
            logger.info("Scan auto-indexation V4 démarré...")
            for base_dir in dirs_to_index:
                if not base_dir.exists():
                    continue
                
                # Scan récursif
                for root, _, files in os.walk(base_dir):
                    for file in files:
                        if not any(file.lower().endswith(e) for e in SUPPORTED_EXTENSIONS):
                            continue
                        filepath = os.path.join(root, file)
                        await self.index_file(filepath)
                        await asyncio.sleep(0.1) # Petite pause pour laisser respirer le CPU
            
            logger.info("Cycle d'auto-indexation terminé. Prochain scan dans 1h.")
            await asyncio.sleep(3600) # 1 heure
