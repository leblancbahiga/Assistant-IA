"""
NURU V6 — Dual-Write Mémoire : WikiWriter + WikiObserver.

Chaque chunk inséré dans le vector store est aussi écrit comme fichier .md
dans ~/Nuru_Brain/. Un watchdog écoute les modifications pour sync inverse.

Inspiré d'OpenHuman (Memory Tree + Obsidian vault).
"""
import os
import re
import hashlib
import logging
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

DEFAULT_WIKI_PATH = os.path.expanduser("~/Nuru_Brain")


class WikiWriter:
    """Écrit les chunks RAG comme fichiers Markdown dans ~/Nuru_Brain/.

    Chaque chunk devient un fichier .md avec en-tête YAML :
      - source : nom du document source
      - id : identifiant du chunk
      - date : date d'indexation
      - hash : MD5 du contenu (pour détection de changement)
      - tags : métadonnées catégorielles
    """

    def __init__(self, wiki_path: str = DEFAULT_WIKI_PATH, enabled: bool = True):
        self.wiki_path = Path(wiki_path)
        self.enabled = enabled
        self._sources_dir = self.wiki_path / "sources"
        self._topics_dir = self.wiki_path / "topics"
        self._state_file = self.wiki_path / ".nuru_state.json"

    def ensure_dirs(self):
        """Crée l'arborescence du wiki si nécessaire."""
        self._sources_dir.mkdir(parents=True, exist_ok=True)
        self._topics_dir.mkdir(parents=True, exist_ok=True)

    def write_chunk(
        self,
        content: str,
        source: str,
        chunk_id: str = "",
        date: str = "",
        tags: Optional[list[str]] = None,
    ) -> Optional[str]:
        """Écrit un chunk comme fichier .md.

        Args:
            content: Texte du chunk
            source: Nom du document source
            chunk_id: Identifiant unique du chunk
            date: Date d'indexation (ISO)
            tags: Liste de tags

        Returns:
            Chemin du fichier écrit, ou None si désactivé
        """
        if not self.enabled:
            return None

        self.ensure_dirs()

        # Slug du nom de fichier à partir de la source
        slug = re.sub(r'[^a-z0-9]+', '-', source.lower()).strip('-')[:40]
        if not slug:
            slug = f"chunk-{chunk_id or hash(content) % 10000}"

        path = self._sources_dir / f"{slug}.md"

        content_hash = hashlib.md5(content.encode()).hexdigest()[:12]

        # En-tête YAML
        md = f"""---
source: {source}
id: {chunk_id or ''}
date: {date or ''}
hash: {content_hash}
tags: [{', '.join(tags or [])}]
---

{content}
"""
        # Écriture atomique (tmp puis rename)
        tmp = path.with_suffix(".md.tmp")
        try:
            tmp.write_text(md, encoding="utf-8")
            tmp.rename(path)
            logger.debug(f"📝 Wiki: écrit {path.name}")
            return str(path)
        except Exception as e:
            logger.warning(f"Wiki write error {path.name}: {e}")
            return None

    def read_chunk(self, filepath: str) -> Optional[dict]:
        """Lit un fichier .md et extrait l'en-tête YAML + contenu."""
        path = Path(filepath)
        if not path.exists() or path.suffix not in (".md",):
            return None

        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return None

        # Parser YAML minimal (sans dépendance PyYAML)
        content = text
        metadata = {"source": "", "id": "", "date": "", "hash": "", "tags": []}

        if text.startswith("---"):
            end = text.find("---", 3)
            if end > 0:
                header = text[3:end].strip()
                content = text[end + 3:].strip()
                for line in header.splitlines():
                    if ":" in line:
                        key, _, val = line.partition(":")
                        key = key.strip()
                        val = val.strip()
                        if key == "tags":
                            val = [t.strip() for t in val.strip("[]").split(",") if t.strip()]
                        metadata[key] = val

        return {"metadata": metadata, "content": content, "path": str(path)}

    def get_all_sources(self) -> list[dict]:
        """Liste tous les fichiers sources du wiki."""
        if not self._sources_dir.exists():
            return []
        files = sorted(self._sources_dir.glob("*.md"))
        return [self.read_chunk(str(f)) for f in files if f.exists()]

    def get_stats(self) -> dict:
        """Retourne des statistiques sur le wiki."""
        sources = self.get_all_sources()
        return {
            "enabled": self.enabled,
            "path": str(self.wiki_path),
            "files": len(sources),
            "sources_dir": str(self._sources_dir),
            "topics_dir": str(self._topics_dir),
        }


class WikiObserver:
    """Surveille les modifications dans ~/Nuru_Brain/sources/ pour sync inverse.

    Quand un fichier .md est modifié manuellement, un callback est déclenché
    pour ré-indexer le chunk dans le vector store.
    """

    def __init__(self, callback: Optional[Callable] = None, enabled: bool = False):
        self.callback = callback
        self.enabled = enabled
        self._observer = None

    def start(self):
        """Démarre le watchdog sur ~/Nuru_Brain/sources/."""
        if not self.enabled:
            return
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            path = Path.home() / "Nuru_Brain" / "sources"
            if not path.exists():
                logger.info("WikiObserver: ~/Nuru_Brain/sources/ inexistant, skip")
                return

            class _Handler(FileSystemEventHandler):
                def __init__(self, cb):
                    self.cb = cb

                def on_modified(self, event):
                    if not event.is_directory and event.src_path.endswith(".md"):
                        if self.cb:
                            self.cb(event.src_path)

                def on_created(self, event):
                    if not event.is_directory and event.src_path.endswith(".md"):
                        if self.cb:
                            self.cb(event.src_path)

            self._observer = Observer()
            self._observer.schedule(_Handler(self.callback), str(path), recursive=False)
            self._observer.start()
            logger.info(f"🔍 WikiObserver: surveillance de {path}")
        except ImportError:
            logger.warning("WikiObserver: watchdog non installé. pip install watchdog")
        except Exception as e:
            logger.warning(f"WikiObserver error: {e}")

    def stop(self):
        """Arrête le watchdog."""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
