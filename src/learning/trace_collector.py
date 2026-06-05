"""
NURU V6 — Learning Loop : TraceCollector.

Enregistre toutes les interactions (query, réponse, mode, feedback) 
dans une base SQLite pour analyse et amélioration continue.
"""
import sqlite3
import os
import json
import logging
import asyncio
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

TRACES_DB = os.path.expanduser("~/.nuru/traces.db")


class TraceCollector:
    """Enregistre les traces d'interaction pour mining périodique.

    Les traces sont écrites via une queue asynchrone pour ne pas
    bloquer le pipeline de génération.
    """

    def __init__(self, db_path: str = TRACES_DB):
        self.db_path = db_path
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._worker_task: Optional[asyncio.Task] = None
        self._ensure_db()

    def _ensure_db(self):
        """Crée la base et la table si nécessaire."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                response TEXT,
                mode TEXT,
                confidence REAL DEFAULT 0.0,
                feedback INTEGER DEFAULT 0,
                tokens_prompt INTEGER DEFAULT 0,
                tokens_generated INTEGER DEFAULT 0,
                latency_ms INTEGER DEFAULT 0,
                model TEXT DEFAULT '',
                error TEXT DEFAULT '',
                timestamp TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_traces_feedback
            ON traces(feedback)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_traces_timestamp
            ON traces(timestamp)
        """)
        conn.commit()
        conn.close()

    async def start(self):
        """Démarre le worker d'écriture asynchrone."""
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker_loop())
            logger.debug("🧪 TraceCollector: worker démarré")

    async def stop(self):
        """Arrête le worker et vide la queue."""
        if self._worker_task:
            self._worker_task.cancel()
            self._worker_task = None
        # Vider la queue restante
        while not self._queue.empty():
            try:
                record = self._queue.get_nowait()
                self._write_sync(record)
            except asyncio.QueueEmpty:
                break

    async def record(
        self,
        query: str,
        response: str = "",
        mode: str = "unknown",
        confidence: float = 0.0,
        feedback: int = 0,
        tokens_prompt: int = 0,
        tokens_generated: int = 0,
        latency_ms: int = 0,
        model: str = "",
        error: str = "",
    ):
        """Enregistre une trace de façon asynchrone."""
        record = {
            "query": query[:500],  # Limiter la taille
            "response": response[:2000],
            "mode": mode,
            "confidence": confidence,
            "feedback": feedback,
            "tokens_prompt": tokens_prompt,
            "tokens_generated": tokens_generated,
            "latency_ms": latency_ms,
            "model": model,
            "error": error[:200] if error else "",
        }
        try:
            await asyncio.wait_for(self._queue.put(record), timeout=1.0)
        except asyncio.TimeoutError:
            logger.warning("🧪 TraceCollector: queue pleine, trace perdue")

    async def _worker_loop(self):
        """Écrit les traces de la queue vers SQLite."""
        while True:
            try:
                record = await self._queue.get()
                self._write_sync(record)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"TraceCollector worker error: {e}")

    def _write_sync(self, record: dict):
        """Écriture synchrone (non-bloquante car rapide)."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=2.0)
            conn.execute(
                """INSERT INTO traces 
                (query, response, mode, confidence, feedback,
                 tokens_prompt, tokens_generated, latency_ms, model, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record["query"], record["response"], record["mode"],
                    record["confidence"], record["feedback"],
                    record["tokens_prompt"], record["tokens_generated"],
                    record["latency_ms"], record["model"], record["error"],
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"TraceCollector write error: {e}")

    # ─── Requêtes ───

    def get_recent(self, limit: int = 50) -> list[dict]:
        """Récupère les traces récentes."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM traces ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_failed(self, limit: int = 50) -> list[dict]:
        """Récupère les traces avec feedback négatif ou erreur."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT * FROM traces 
            WHERE feedback = -1 OR error != ''
            ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def count(self) -> int:
        """Nombre total de traces."""
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
        conn.close()
        return count

    def update_feedback(self, trace_id: int, feedback: int):
        """Met à jour le feedback d'une trace."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE traces SET feedback = ? WHERE id = ?",
            (feedback, trace_id),
        )
        conn.commit()
        conn.close()
