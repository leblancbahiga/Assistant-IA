"""
NURU V9 — FeedbackCollector : collecte structurée du feedback utilisateur.

Types de feedback :
- thumbs_up/down : évaluation binaire
- correction : correction textuelle explicite
- rating : score 1-5

Stocke dans SQLite (feedback_log) et synchronise avec ErrorMemory
via MemoryManager pour les corrections.
"""

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

FEEDBACK_DB = os.path.expanduser("~/.nuru/feedback.db")


class FeedbackCollector:
    """Collecte le feedback utilisateur structuré.

    Enregistre les évaluations binaires (thumbs), les corrections explicites,
    les ratings 1-5 et se synchronise avec ErrorMemory (via MemoryManager)
    pour les corrections.

    Attributes:
        db_path: Chemin vers la base SQLite
        memory_manager: Instance optionnelle de MemoryManager pour synchronisation
    """

    def __init__(self, db_path: str = FEEDBACK_DB, memory_manager=None):
        self.db_path = db_path
        self.memory_manager = memory_manager
        self._ensure_db()

    def _ensure_db(self):
        """Crée la base et la table si nécessaire."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback_log (
                    id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    session_id TEXT NOT NULL DEFAULT 'default',
                    query TEXT NOT NULL,
                    response TEXT NOT NULL DEFAULT '',
                    feedback_type TEXT NOT NULL,
                    value TEXT NOT NULL DEFAULT '',
                    value_real REAL DEFAULT 0.0,
                    error_id TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_feedback_timestamp
                ON feedback_log(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_feedback_type
                ON feedback_log(feedback_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_feedback_session
                ON feedback_log(session_id)
            """)
            conn.commit()
        finally:
            conn.close()

    def _get_conn(self):
        """Retourne une connexion SQLite avec row_factory activée."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _insert(self, feedback_type: str, query: str, response: str,
                value: str = "", value_real: float = 0.0,
                session_id: str = "default", error_id: str = "") -> str:
        """Insère une entrée de feedback et retourne son ID."""
        feedback_id = str(uuid.uuid4())
        now = time.time()
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO feedback_log
                   (id, timestamp, session_id, query, response,
                    feedback_type, value, value_real, error_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (feedback_id, now, session_id, query, response,
                 feedback_type, value, value_real, error_id),
            )
            conn.commit()
        finally:
            conn.close()
        logger.debug("Feedback enregistré : %s (%s)", feedback_id, feedback_type)
        return feedback_id

    # ── Méthodes publiques ─────────────────────────────────────────

    def record_thumbs(self, query: str, response: str, is_positive: bool,
                      session_id: str = "default") -> str:
        """Enregistre un thumbs up/down.

        Args:
            query: Requête utilisateur
            response: Réponse associée
            is_positive: True pour thumbs up, False pour thumbs down
            session_id: Identifiant de session

        Returns:
            ID du feedback enregistré
        """
        fb_type = "thumbs_up" if is_positive else "thumbs_down"
        value = "1" if is_positive else "-1"
        return self._insert(fb_type, query, response, value=value,
                            session_id=session_id)

    def record_correction(self, query: str, response: str, correction: str,
                          session_id: str = "default") -> str:
        """Enregistre une correction explicite.

        Si un memory_manager est fourni, synchronise aussi avec ErrorMemory
        pour créer une entrée 'user_correction' exploitable par le
        système de détection d'erreurs.

        Args:
            query: Requête utilisateur originale
            response: Réponse qui a été corrigée
            correction: Texte de la correction
            session_id: Identifiant de session

        Returns:
            ID du feedback enregistré
        """
        error_id = ""
        if self.memory_manager is not None:
            try:
                description = f"Correction utilisateur pour : {query[:100]}"
                error_id = self.memory_manager.record_error(
                    error_type="user_correction",
                    description=description,
                    root_correction=correction,
                    correction=correction,
                )
                logger.debug("Correction synchronisée avec ErrorMemory: %s", error_id)
            except Exception as e:
                logger.warning(
                    "Échec synchronisation ErrorMemory pour correction: %s", e
                )

        return self._insert(
            "correction", query, response,
            value=correction, session_id=session_id,
            error_id=error_id or "",
        )

    def record_rating(self, query: str, response: str, rating: int,
                      session_id: str = "default") -> str:
        """Enregistre un rating 1-5.

        Args:
            query: Requête utilisateur
            response: Réponse associée
            rating: Score de 1 à 5
            session_id: Identifiant de session

        Returns:
            ID du feedback enregistré

        Raises:
            ValueError: Si le rating n'est pas entre 1 et 5
        """
        if not (1 <= rating <= 5):
            raise ValueError(f"Le rating doit être entre 1 et 5, reçu: {rating}")
        return self._insert(
            "rating", query, response,
            value=str(rating), value_real=float(rating),
            session_id=session_id,
        )

    def record_clarification(self, query: str, response: str,
                              clarification: str,
                              session_id: str = "default") -> str:
        """Enregistre une reformulation de requête (indice d'insatisfaction).

        Args:
            query: Requête originale
            response: Réponse associée
            clarification: Reformulation proposée par l'utilisateur
            session_id: Identifiant de session

        Returns:
            ID du feedback enregistré
        """
        return self._insert(
            "clarification", query, response,
            value=clarification, session_id=session_id,
        )

    # ── Requêtes ───────────────────────────────────────────────────

    def get_recent(self, limit: int = 20) -> list[dict]:
        """Récupère les feedbacks récents.

        Args:
            limit: Nombre max d'entrées à retourner

        Returns:
            Liste de dicts ordonnée par timestamp décroissant
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM feedback_log ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_stats(self) -> dict:
        """Statistiques globales des feedbacks.

        Returns:
            dict avec :
            - total: nombre total de feedbacks
            - thumbs_up: nombre de thumbs up
            - thumbs_down: nombre de thumbs down
            - corrections: nombre de corrections
            - ratings: nombre de ratings
            - clarifications: nombre de clarifications
            - satisfaction_rate: ratio thumbs_up / (thumbs_up + thumbs_down)
            - avg_rating: moyenne des ratings
        """
        conn = self._get_conn()
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM feedback_log"
            ).fetchone()[0]

            thumbs_up = conn.execute(
                "SELECT COUNT(*) FROM feedback_log WHERE feedback_type='thumbs_up'"
            ).fetchone()[0]

            thumbs_down = conn.execute(
                "SELECT COUNT(*) FROM feedback_log WHERE feedback_type='thumbs_down'"
            ).fetchone()[0]

            corrections = conn.execute(
                "SELECT COUNT(*) FROM feedback_log WHERE feedback_type='correction'"
            ).fetchone()[0]

            ratings_count = conn.execute(
                "SELECT COUNT(*) FROM feedback_log WHERE feedback_type='rating'"
            ).fetchone()[0]

            clarifications = conn.execute(
                "SELECT COUNT(*) FROM feedback_log WHERE feedback_type='clarification'"
            ).fetchone()[0]

            avg_row = conn.execute(
                "SELECT AVG(value_real) FROM feedback_log WHERE feedback_type='rating'"
            ).fetchone()
            avg_rating = round(float(avg_row[0]), 2) if avg_row and avg_row[0] is not None else 0.0

        finally:
            conn.close()

        total_thumbs = thumbs_up + thumbs_down
        satisfaction_rate = round(
            thumbs_up / total_thumbs, 4
        ) if total_thumbs > 0 else 0.0

        return {
            "total": total,
            "thumbs_up": thumbs_up,
            "thumbs_down": thumbs_down,
            "corrections": corrections,
            "ratings": ratings_count,
            "clarifications": clarifications,
            "satisfaction_rate": satisfaction_rate,
            "avg_rating": avg_rating,
        }

    def get_corrections(self, limit: int = 50) -> list[dict]:
        """Récupère les corrections pour analyse.

        Args:
            limit: Nombre max de corrections à retourner

        Returns:
            Liste de dicts des feedbacks de type 'correction'
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT * FROM feedback_log
                   WHERE feedback_type='correction'
                   ORDER BY timestamp DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def count(self) -> int:
        """Nombre total de feedbacks enregistrés.

        Returns:
            Nombre d'entrées dans la table feedback_log
        """
        conn = self._get_conn()
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM feedback_log"
            ).fetchone()[0]
            return count
        finally:
            conn.close()
