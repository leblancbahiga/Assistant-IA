"""
NURU V9 — ResumeManager : sauvegarde et restauration de l'état des tâches.

Stocke l'état dans SQLite (table task_states).
Permet de reprendre une tâche après interruption (crash, timeout utilisateur).
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional


class ResumeManager:
    """
    Sauvegarde et restauration de l'état d'une tâche interrompue.

    Stocke l'état dans SQLite (table task_states).
    Permet de reprendre une tâche après interruption (crash, timeout utilisateur).
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialise le gestionnaire de reprise.

        Args:
            db_path: Chemin vers la base SQLite.
                     Par défaut : ~/.nuru/task_states.db
        """
        self.db_path = db_path or str(Path.home() / ".nuru" / "task_states.db")
        self._init_db()

    # ── Initialisation ──────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Crée la table task_states si elle n'existe pas."""
        conn = self._get_conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_states (
                    task_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'interrupted',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        """
        Retourne une connexion SQLite avec WAL mode et row_factory.

        Returns:
            sqlite3.Connection configurée
        """
        # Créer le répertoire parent si nécessaire
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    # ── Interface publique ──────────────────────────────────────────────

    def save_state(self, task_id: str, state: dict[str, Any]) -> None:
        """
        Sauvegarde ou met à jour l'état d'une tâche.

        Utilise INSERT OR REPLACE pour permettre la mise à jour.

        Args:
            task_id: Identifiant unique de la tâche
            state:   Dictionnaire représentant l'état de la tâche
        """
        now = time.time()
        state_json = json.dumps(state, default=str)
        status = state.get("status", "interrupted")

        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO task_states
                    (task_id, state, status, created_at, updated_at)
                VALUES (?, ?, ?,
                    COALESCE(
                        (SELECT created_at FROM task_states WHERE task_id = ?),
                        ?
                    ),
                    ?
                )
                """,
                (task_id, state_json, status, task_id, now, now),
            )
            conn.commit()
        finally:
            conn.close()

    def load_state(self, task_id: str) -> Optional[dict[str, Any]]:
        """
        Charge l'état sauvegardé d'une tâche.

        Args:
            task_id: Identifiant unique de la tâche

        Returns:
            Dictionnaire représentant l'état, ou None si introuvable
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT state FROM task_states WHERE task_id = ?",
                (task_id,),
            ).fetchone()

            if row is None:
                return None

            return json.loads(row["state"])
        finally:
            conn.close()

    def list_interrupted(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        Liste les tâches interrompues récentes.

        Args:
            limit: Nombre maximum de tâches à retourner

        Returns:
            Liste de dictionnaires avec task_id, status, updated_at
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT task_id, status, created_at, updated_at
                FROM task_states
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            return [
                {
                    "task_id": row["task_id"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]
        finally:
            conn.close()

    def delete_state(self, task_id: str) -> bool:
        """
        Supprime l'état sauvegardé d'une tâche.

        Args:
            task_id: Identifiant unique de la tâche

        Returns:
            True si une ligne a été supprimée, False sinon
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM task_states WHERE task_id = ?",
                (task_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
