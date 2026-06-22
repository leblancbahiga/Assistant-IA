#!/usr/bin/env python3
"""NURU V12 — Reset complet des bases de données mémoire.

Usage : python3 reset_nuru_db.py

Supprime et recrée à vide :
  - memory_v9.db       (ancienne mémoire V9 → hallucinations)
  - rag_index.db       (index RAG)
  - nuru_brain.db      (wiki Nuru_Brain)
  - optimizer.db       (stats optimisation)
  - performance.db     (stats performance)
  - feedback.db        (feedback utilisateur)
  - task_states.db     (états tâches)
  - traces.db          (traces pipeline)

Tous les fichiers sont sauvegardés avec un suffixe .bak.<timestamp>
avant suppression pour récupération éventuelle.
"""

import os
import shutil
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DB_DIR = Path.home() / ".nuru"
DB_FILES = [
    "memory_v9.db",
    "rag_index.db",
    "nuru_brain.db",
    "optimizer.db",
    "performance.db",
    "feedback.db",
    "task_states.db",
    "traces.db",
]

def backup_and_remove():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = DB_DIR / f"backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    removed = 0
    for name in DB_FILES:
        path = DB_DIR / name
        if path.exists():
            bak = backup_dir / name
            shutil.copy2(path, bak)
            os.remove(path)
            logger.info(f"🗑️  {name} → backup: {bak}")
            removed += 1
        else:
            logger.info(f"— {name} : introuvable, ignoré")

    logger.info(f"\n✅ {removed} base(s) sauvegardée(s) et supprimée(s)")
    logger.info(f"📦 Backup : {backup_dir}")
    logger.info("♻️  Redémarre NURU pour reconstruire les bases à vide.")

if __name__ == "__main__":
    backup_and_remove()
