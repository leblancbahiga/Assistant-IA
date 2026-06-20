"""Document watcher pour auto-indexation temps réel.

Utilise watchdog pour surveiller les dossiers de documents et indexer
automatiquement les nouveaux fichiers et les modifications.
"""
import asyncio
import logging
import os
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False
    logger.warning("watchdog non installé. pip install watchdog pour l'auto-indexation temps réel.")


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv", ".json"}


if HAS_WATCHDOG:

    class _DocHandler(FileSystemEventHandler):
        """Handler watchdog qui déclenche l'indexation différée."""

        def __init__(self, index_callback: Callable, debounce_seconds: float = 3.0):
            self.index_callback = index_callback
            self.debounce = debounce_seconds
            self._pending: set[str] = set()

        def on_created(self, event):
            if not event.is_directory and self._is_supported(event.src_path):
                self._schedule(event.src_path)

        def on_modified(self, event):
            if not event.is_directory and self._is_supported(event.src_path):
                self._schedule(event.src_path)

        def _is_supported(self, path: str) -> bool:
            return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS

        def _schedule(self, path: str):
            self._pending.add(path)
            asyncio.create_task(self._debounced_index(path))

        async def _debounced_index(self, path: str):
            await asyncio.sleep(self.debounce)
            if path in self._pending:
                self._pending.discard(path)
                try:
                    await self.index_callback(path)
                except Exception as e:
                    logger.error(f"[DocWatcher] Indexation échouée: {path} — {e}")


class DocumentWatcher:
    """Surveille les dossiers et indexe automatiquement les documents.

    Usage:
        watcher = DocumentWatcher(index_callback=engine.index_file)
        watcher.start()        # Démarre la surveillance
        watcher.stop()         # Arrête la surveillance
    """

    def __init__(self, index_callback: Callable, watch_dirs: list[Path] = None):
        logger.setLevel(logging.INFO)  # V6.2 : réduit le bruit DEBUG des événements fichier
        self.index_callback = index_callback
        self.watch_dirs = watch_dirs or [
            Path.home() / "Documents",
            Path.home() / "Desktop",
            Path.home() / "Downloads",
        ]
        self._observer: Optional[Observer] = None
        self._handler: Optional[_DocHandler] = None

    def start(self):
        """Démarre la surveillance des dossiers."""
        if not HAS_WATCHDOG:
            logger.warning("watchdog non installé, watcher désactivé")
            return

        if self._observer is not None:
            logger.info("[DocWatcher] Déjà en cours d'exécution")
            return

        self._handler = _DocHandler(self.index_callback)
        self._observer = Observer()

        for d in self.watch_dirs:
            if d.exists():
                self._observer.schedule(self._handler, str(d), recursive=True)
                logger.info(f"[DocWatcher] Surveillance: {d}")
            else:
                logger.debug(f"[DocWatcher] Dossier introuvable: {d}")

        self._observer.start()
        logger.info(f"[DocWatcher] ✅ Surveillance active sur {len([d for d in self.watch_dirs if d.exists()])} dossiers")

    def stop(self):
        """Arrête la surveillance."""
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            logger.info("[DocWatcher] Surveillance arrêtée")

    @property
    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()
