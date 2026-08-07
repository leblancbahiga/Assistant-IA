"""
NURU V10 — SessionStore : gestion de sessions conversationnelles persistantes.

Stocke l'historique des échanges par session_id et fournit un contexte
formaté pour injection dans le prompt LLM.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_DIR = Path.home() / "Library" / "Application Support" / "nuru"
DB_PATH = DB_DIR / "sessions.db"


@dataclass
class Message:
    role: str          # "user" | "assistant" | "system"
    content: str
    timestamp: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "role": self.role,
            "content": self.content[:120] + "..." if len(self.content) > 120 else self.content,
            "timestamp": self.timestamp,
        }

    def format_for_prompt(self) -> str:
        prefix = "Utilisateur" if self.role == "user" else "NURU"
        return f"[{prefix}] {self.content}"


@dataclass
class Session:
    id: str
    title: str = ""
    messages: list[Message] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "message_count": len(self.messages),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class SessionStore:
    """Stocke et récupère les sessions conversationnelles.

    Chaque session est identifiée par un ``session_id`` (chaîne libre).
    Le constructeur est léger — la base est créée au premier accès.
    """

    def __init__(self, db_path: str = str(DB_PATH)):
        self._db_path = db_path
        self._ensure_db()

    # ── Initialisation ───────────────────────────────────────────────────

    def _ensure_db(self):
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp REAL NOT NULL,
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session
            ON messages(session_id, timestamp)
        """)
        conn.commit()
        conn.close()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── Gestion des sessions ─────────────────────────────────────────────

    def create_session(self, session_id: str, title: str = "") -> None:
        """Crée une nouvelle session si elle n'existe pas."""
        now = time.time()
        conn = self._conn()
        conn.execute(
            "INSERT OR IGNORE INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, title, now, now),
        )
        conn.commit()
        conn.close()

    def get_or_create(self, session_id: str, title: str = "") -> Session:
        """Retourne une session existante ou en crée une nouvelle."""
        conn = self._conn()
        row = conn.execute(
            "SELECT id, title, created_at, updated_at FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

        if row is None:
            now = time.time()
            conn.execute(
                "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, title, now, now),
            )
            conn.commit()
            created = now
            updated = now
            title_actual = title
        else:
            created = row["created_at"]
            updated = row["updated_at"]
            title_actual = row["title"]

        # Charger les messages
        msg_rows = conn.execute(
            "SELECT role, content, timestamp, metadata FROM messages "
            "WHERE session_id = ? ORDER BY timestamp ASC",
            (session_id,),
        ).fetchall()
        conn.close()

        messages = [
            Message(
                role=r["role"],
                content=r["content"],
                timestamp=r["timestamp"],
                metadata=json.loads(r["metadata"]) if r["metadata"] else {},
            )
            for r in msg_rows
        ]

        return Session(
            id=session_id,
            title=title_actual,
            messages=messages,
            created_at=created,
            updated_at=updated,
        )

    # ── Messages ─────────────────────────────────────────────────────────

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """Ajoute un message à une session (la crée si besoin)."""
        now = time.time()
        conn = self._conn()

        # S'assurer que la session existe
        conn.execute(
            "INSERT OR IGNORE INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, "Nouvelle session", now, now),
        )

        conn.execute(
            "INSERT INTO messages (session_id, role, content, timestamp, metadata) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, now, json.dumps(metadata or {})),
        )

        # Mettre à jour le timestamp de la session
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        conn.commit()
        conn.close()

    def clear_session(self, session_id: str) -> None:
        """Supprime tous les messages d'une session."""
        conn = self._conn()
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?",
                     (time.time(), session_id))
        conn.commit()
        conn.close()

    def delete_session(self, session_id: str) -> None:
        """Supprime une session et ses messages."""
        conn = self._conn()
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        conn.close()

    # ── Contexte pour injection prompt ───────────────────────────────────

    def build_context(self, session_id: str, max_messages: int = 10, max_chars: int = 4000) -> str:
        """Construit un bloc de contexte conversationnel pour le prompt.

        Args:
            session_id: Identifiant de la session
            max_messages: Nombre maximum de messages (paires user/assistant)
            max_chars: Taille maximum du bloc (defaut: 4000 chars)

        Returns:
            Chaîne formatée pour injection, ou chaîne vide si pas d'historique
        """
        session = self.get_or_create(session_id)
        if len(session.messages) < 2:
            return ""

        # Prendre les N derniers messages
        recent = session.messages[-max_messages:]
        parts = []
        total = 0
        for m in recent:
            chunk = m.format_for_prompt()
            if total + len(chunk) > max_chars:
                chunk = chunk[: max_chars - total] + "…[tronqué]"
            parts.append(chunk)
            total += len(chunk)
        context = "\n".join(parts)

        return (
            "## Historique de la conversation\n"
            "(échanges récents entre l'utilisateur et NURU)\n\n"
            f"{context}\n\n"
            "---\n"
        )

    # ── Liste des sessions ───────────────────────────────────────────────

    def list_sessions(self, limit: int = 50) -> list[dict]:
        """Liste les sessions avec leur dernier message et comptage."""
        conn = self._conn()
        rows = conn.execute("""
            SELECT
                s.id,
                s.title,
                s.created_at,
                s.updated_at,
                COUNT(m.id) AS message_count
            FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.id
            GROUP BY s.id
            ORDER BY s.updated_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        conn.close()

        return [
            {
                "id": r["id"],
                "title": r["title"] or r["id"][:8],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "message_count": r["message_count"],
            }
            for r in rows
        ]

    def update_title(self, session_id: str, title: str) -> None:
        """Met à jour le titre d'une session."""
        conn = self._conn()
        conn.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))
        conn.commit()
        conn.close()
