"""
NURU V6 — Auto-Fetch : Ingestion asynchrone silencieuse.

Scanne périodiquement les dossiers configurés (workspace, Downloads, etc.)
et n'indexe que les fichiers nouveaux ou modifiés (détection par hash MD5).

Utilise un petit embedder CPU (sentence-transformers) en arrière-plan
pour ne pas monopoliser le GPU MLX.

Inspiré d'OpenHuman (Auto-fetch toutes les 20 min).
"""
import os
import hashlib
import json
import logging
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# Sources par défaut : dossiers de travail + téléchargements
DEFAULT_SOURCES = [
    {
        "name": "workspace",
        "path": "~/workspace",
        "glob": "*.md",
        "interval_min": 30,
        "max_files": 20,
    },
    {
        "name": "nuru_docs",
        "path": "~/Downloads/Assistant IA/data",
        "glob": "*.{md,txt,pdf}",
        "interval_min": 60,
        "max_files": 10,
    },
]

STATE_FILE = os.path.expanduser("~/.nuru/data_hashes.json")


class AutoFetcher:
    """Scanne les dossiers sources et indexe les fichiers nouveaux/modifiés.

    Utilise une détection par hash MD5 pour éviter de ré-indexer
    les fichiers inchangés. Ne bloque pas le GPU : utilise un embedder
    CPU séparé du MLX.
    """

    def __init__(
        self,
        index_callback: Optional[Callable] = None,
        enabled: bool = False,
        sources: Optional[list[dict]] = None,
    ):
        self.index_callback = index_callback
        self.enabled = enabled
        self.sources = sources or DEFAULT_SOURCES
        self._hashes = self._load_hashes()

    def _load_hashes(self) -> dict:
        """Charge le dictionnaire des hash des fichiers déjà indexés."""
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_hashes(self):
        """Sauvegarde les hash sur disque."""
        Path(STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(self._hashes, f, indent=2)
        except Exception as e:
            logger.warning(f"AutoFetch save hashes error: {e}")

    async def scan(self) -> list[str]:
        """Scanne toutes les sources et retourne les chemins des nouveaux fichiers.

        Returns:
            Liste des chemins de fichiers nouveaux ou modifiés
        """
        if not self.enabled:
            return []

        new_files = []

        for source in self.sources:
            try:
                files = await self._scan_source(source)
                new_files.extend(files)
            except Exception as e:
                logger.warning(f"AutoFetch scan {source['name']}: {e}")

        self._save_hashes()
        return new_files

    async def _scan_source(self, config: dict) -> list[str]:
        """Scanne une source et retourne les nouveaux fichiers."""
        base = Path(config["path"]).expanduser()
        if not base.exists():
            return []

        pattern = config.get("glob", "*")
        max_files = config.get("max_files", 50)
        new_files = []

        # Lister les fichiers, triés par date de modification (les plus récents d'abord)
        files = sorted(base.glob(pattern), key=os.path.getmtime, reverse=True)
        files = files[:max_files]

        for fpath in files:
            if not fpath.is_file():
                continue

            try:
                current_hash = hashlib.md5(fpath.read_bytes()).hexdigest()
            except Exception:
                continue

            str_path = str(fpath)
            prev_hash = self._hashes.get(str_path)

            if prev_hash == current_hash:
                continue  # Inchangé

            # Nouveau ou modifié
            self._hashes[str_path] = current_hash
            new_files.append(str_path)

        if new_files:
            logger.info(
                f"📥 AutoFetch [{config['name']}]: {len(new_files)} nouveau(x) fichier(s)"
            )

        return new_files

    async def scan_and_index(self):
        """Scanne et indexe les nouveaux fichiers via le callback."""
        if not self.enabled or not self.index_callback:
            return

        new_files = await self.scan()

        for fpath in new_files:
            try:
                await self.index_callback(fpath)
            except Exception as e:
                logger.warning(f"AutoFetch index {fpath}: {e}")

    def get_stats(self) -> dict:
        """Statistiques sur l'état de l'auto-fetch."""
        return {
            "enabled": self.enabled,
            "sources": len(self.sources),
            "tracked_files": len(self._hashes),
            "state_file": STATE_FILE,
        }

    def reset_state(self):
        """Réinitialise les hash (force re-index au prochain scan)."""
        self._hashes = {}
        self._save_hashes()
        logger.info("🔄 AutoFetch: état réinitialisé")
