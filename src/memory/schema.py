"""
NURU V9 — Schéma de la base de mémoire unifiée.

Gère la création et la migration de `memory.db`.
Toutes les tables mémoire partagent une seule base SQLite.

Tables :
- episodic_memory   : Événements vécus avec contexte temporel
- semantic_memory   : Faits consolidés avec confidence score
- procedural_memory : Workflows appris (JSON)
- user_memory       : Profil utilisateur (key-value)
- error_memory      : Erreurs passées et corrections
- working_memory    : Contexte de session (TTL)
- memory_schema_version : Version du schéma
"""

import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Version actuelle du schéma
SCHEMA_VERSION = 1

# Base de données par défaut
DEFAULT_DB_DIR = Path.home() / ".nuru"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "memory_v9.db"


def get_db_path(override: Optional[str] = None) -> str:
    """Retourne le chemin de la base mémoire, crée le répertoire si nécessaire."""
    if override:
        path = Path(override)
    else:
        path = DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


class MemorySchema:
    """Gestion du schéma de la base de mémoire unifiée."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = get_db_path(db_path)

    def _get_conn(self) -> sqlite3.Connection:
        """Ouvre une connexion thread-safe avec WAL mode."""
        conn = sqlite3.connect(self.db_path, timeout=20, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Crée toutes les tables si elles n'existent pas (idempotent)."""
        conn = self._get_conn()
        try:
            self._create_tables(conn)
            self._ensure_version(conn)
        finally:
            conn.close()
        logger.info("Base mémoire V9 initialisée : %s", self.db_path)

    def _create_tables(self, conn: sqlite3.Connection):
        """CREATE TABLE IF NOT EXISTS pour chaque type de mémoire."""

        # ── Mémoire épisodique ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS episodic_memory (
                id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                event_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                context TEXT,
                embedding BLOB,
                importance REAL DEFAULT 0.5,
                access_count INTEGER DEFAULT 0,
                last_accessed REAL,
                consolidated INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_episodic_timestamp
            ON episodic_memory (timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_episodic_event_type
            ON episodic_memory (event_type)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_episodic_consolidated
            ON episodic_memory (consolidated)
        """)

        # ── Mémoire sémantique ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS semantic_memory (
                id TEXT PRIMARY KEY,
                fact TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                confidence REAL DEFAULT 0.8,
                source_episodes TEXT,
                embedding BLOB,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                access_count INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_semantic_category
            ON semantic_memory (category)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_semantic_confidence
            ON semantic_memory (confidence)
        """)

        # ── Mémoire procédurale ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS procedural_memory (
                id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                steps TEXT NOT NULL,
                tools_required TEXT,
                success_rate REAL DEFAULT 0.0,
                avg_duration_ms REAL DEFAULT 0.0,
                last_used REAL,
                embedding BLOB
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_procedural_task_type
            ON procedural_memory (task_type)
        """)

        # ── Mémoire utilisateur ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_memory (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                confidence REAL DEFAULT 0.8,
                updated_at REAL NOT NULL,
                source TEXT DEFAULT 'conversation'
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_category
            ON user_memory (category)
        """)

        # ── Mémoire des erreurs ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS error_memory (
                id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                error_type TEXT NOT NULL,
                description TEXT NOT NULL,
                root_cause TEXT,
                correction TEXT,
                related_query TEXT,
                embedding BLOB,
                resolved INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_error_type
            ON error_memory (error_type)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_error_resolved
            ON error_memory (resolved)
        """)

        # ── Working Memory (session) ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS working_memory (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                ttl REAL,
                created_at REAL NOT NULL
            )
        """)

    def _ensure_version(self, conn: sqlite3.Connection):
        """Vérifie/met à jour la version du schéma."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_schema_version (
                version INTEGER PRIMARY KEY,
                updated_at REAL NOT NULL
            )
        """)
        conn.commit()  # DDL auto-commit

        row = conn.execute("SELECT version FROM memory_schema_version").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO memory_schema_version (version, updated_at) VALUES (?, ?)",
                (SCHEMA_VERSION, time.time()),
            )
            conn.commit()  # Force l'écriture DML
            logger.info("Schéma mémoire V%s initialisé", SCHEMA_VERSION)
        elif row[0] < SCHEMA_VERSION:
            # Placeholder pour futures migrations
            conn.execute(
                "UPDATE memory_schema_version SET version=?, updated_at=? WHERE version=?",
                (SCHEMA_VERSION, time.time(), row[0]),
            )
            logger.info("Schéma mémoire migré V%s → V%s", row[0], SCHEMA_VERSION)

    def clear_db(self):
        """Supprime toute la base (⚠️ usage test uniquement)."""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
            logger.warning("Base mémoire supprimée : %s", self.db_path)
