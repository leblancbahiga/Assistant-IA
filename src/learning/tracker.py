"""
NURU V9 — PerformanceTracker : mesure en continu les performances du système.

Métriques trackées par catégorie :
- RAG : recall@5, avg_score, empty_rate, hyde_trigger_rate
- Réponse : avg_response_time, avg_tokens, hallucination_rate, citation_rate
- Agent : task_success_rate, avg_steps_per_task, error_recovery_rate
- Feedback : thumbs_up_rate, thumbs_down_rate, correction_rate

Stocke dans SQLite (performance_metrics) avec horodatage pour
agrégation temporelle et analyse de tendances.
"""

import json
import logging
import os
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PERFORMANCE_DB = os.path.expanduser("~/.nuru/performance.db")


class PerformanceTracker:
    """Mesure en continu les performances du système.

    Chaque métrique est enregistrée avec un timestamp, une catégorie
    et des tags optionnels (JSON) pour un filtrage granulaire.

    Attributes:
        db_path: Chemin vers la base SQLite
    """

    def __init__(self, db_path: str = PERFORMANCE_DB):
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self):
        """Crée la base et la table si nécessaire."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    category TEXT NOT NULL DEFAULT 'general',
                    tags TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_metric_name
                ON performance_metrics(metric_name)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_metric_timestamp
                ON performance_metrics(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_metric_category
                ON performance_metrics(category)
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

    # ── Enregistrement ─────────────────────────────────────────────

    def record(self, metric_name: str, value: float,
               category: str = "general", tags: dict = None) -> str:
        """Enregistre une métrique ponctuelle.

        Args:
            metric_name: Nom de la métrique (ex: 'rag_recall@5')
            value: Valeur numérique de la métrique
            category: Catégorie ('rag', 'response', 'agent', 'feedback', 'general')
            tags: Dict optionnel de métadonnées (ex: {"model": "qwen2.5"})

        Returns:
            ID de la métrique enregistrée
        """
        metric_id = str(uuid.uuid4())
        now = time.time()
        tags_json = json.dumps(tags or {}, ensure_ascii=False)
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO performance_metrics
                   (id, timestamp, metric_name, metric_value, category, tags)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (metric_id, now, metric_name, value, category, tags_json),
            )
            conn.commit()
        finally:
            conn.close()
        return metric_id

    # ── Helpers spécialisés ────────────────────────────────────────

    def record_rag_result(self, query: str, recall5: float, avg_score: float,
                          empty: bool):
        """Helper pratique pour enregistrer les métriques d'un résultat RAG.

        Enregistre 4 métriques en une seule fois :
          - rag_recall@5
          - rag_avg_score
          - rag_empty (1.0 si vide, 0.0 sinon)
          - rag_hyde_trigger (0.0, à mettre à jour séparément si besoin)

        Args:
            query: Requête associée (passée en tag)
            recall5: Recall@5 (0.0 - 1.0)
            avg_score: Score moyen des résultats (0.0 - 1.0)
            empty: True si aucun résultat trouvé
        """
        tags = {"query": query[:200]}
        empty_val = 1.0 if empty else 0.0
        self.record("rag_recall@5", recall5, category="rag", tags=tags)
        self.record("rag_avg_score", avg_score, category="rag", tags=tags)
        self.record("rag_empty", empty_val, category="rag", tags=tags)
        self.record("rag_hyde_trigger", 0.0, category="rag", tags=tags)

    def record_response_metrics(self, response_time_ms: float, tokens: int,
                                hallucination: bool, has_citation: bool,
                                tags: dict = None):
        """Helper pour enregistrer les métriques de réponse.

        Args:
            response_time_ms: Temps de réponse en ms
            tokens: Nombre de tokens générés
            hallucination: True si une hallucination a été détectée
            has_citation: True si des citations sont incluses
            tags: Dict optionnel de métadonnées
        """
        tags = tags or {}
        self.record("response_time_ms", response_time_ms,
                     category="response", tags=tags)
        self.record("response_tokens", float(tokens),
                     category="response", tags=tags)
        self.record("response_hallucination", 1.0 if hallucination else 0.0,
                     category="response", tags=tags)
        self.record("response_citation", 1.0 if has_citation else 0.0,
                     category="response", tags=tags)

    def record_agent_result(self, success: bool, steps: int,
                            recovery: bool):
        """Helper pratique pour enregistrer les métriques d'une tâche agent.

        Enregistre 3 métriques :
          - agent_task_success (1.0 si succès, 0.0 sinon)
          - agent_steps
          - agent_recovery (1.0 si recovery utilisé, 0.0 sinon)

        Args:
            success: True si la tâche a réussi
            steps: Nombre d'étapes exécutées
            recovery: True si la récupération d'erreur a été utilisée
        """
        self.record("agent_task_success", 1.0 if success else 0.0,
                     category="agent")
        self.record("agent_steps", float(steps), category="agent")
        self.record("agent_recovery", 1.0 if recovery else 0.0,
                     category="agent")

    def record_feedback_metrics(self, thumbs_up: bool = False,
                                 thumbs_down: bool = False,
                                 correction: bool = False,
                                 rating: int = 0):
        """Helper pour enregistrer les métriques de feedback.

        Args:
            thumbs_up: True si thumbs up reçu
            thumbs_down: True si thumbs down reçu
            correction: True si correction reçue
            rating: Rating 1-5 (0 si pas de rating)
        """
        self.record("feedback_thumbs_up", 1.0 if thumbs_up else 0.0,
                     category="feedback")
        self.record("feedback_thumbs_down", 1.0 if thumbs_down else 0.0,
                     category="feedback")
        self.record("feedback_correction", 1.0 if correction else 0.0,
                     category="feedback")
        if rating > 0:
            self.record("feedback_rating", float(rating), category="feedback")

    # ── Agrégations et requêtes ────────────────────────────────────

    def get_averages(self, category: str = None,
                     since_hours: int = 24) -> dict:
        """Retourne les moyennes des métriques sur une période.

        Args:
            category: Filtrer par catégorie (None = toutes)
            since_hours: Période en heures (défaut: 24h)

        Returns:
            dict {metric_name: avg_value}
        """
        since_ts = time.time() - (since_hours * 3600)
        conn = self._get_conn()
        try:
            if category:
                rows = conn.execute(
                    """SELECT metric_name, AVG(metric_value) as avg_val
                       FROM performance_metrics
                       WHERE category = ? AND timestamp >= ?
                       GROUP BY metric_name
                       ORDER BY metric_name""",
                    (category, since_ts),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT metric_name, AVG(metric_value) as avg_val
                       FROM performance_metrics
                       WHERE timestamp >= ?
                       GROUP BY metric_name
                       ORDER BY metric_name""",
                    (since_ts,),
                ).fetchall()
            return {row["metric_name"]: round(float(row["avg_val"]), 4)
                    for row in rows}
        finally:
            conn.close()

    def get_trend(self, metric_name: str, days: int = 7) -> list[dict]:
        """Retourne l'évolution d'une métrique sur N jours.

        Agrège par jour (moyenne) pour visualiser la tendance.

        Args:
            metric_name: Nom de la métrique
            days: Nombre de jours à remonter

        Returns:
            Liste de dicts : {date, avg_value, count} triés par date
        """
        since_ts = time.time() - (days * 86400)
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT
                       DATE(timestamp, 'unixepoch') as day,
                       AVG(metric_value) as avg_value,
                       COUNT(*) as count
                   FROM performance_metrics
                   WHERE metric_name = ? AND timestamp >= ?
                   GROUP BY day
                   ORDER BY day ASC""",
                (metric_name, since_ts),
            ).fetchall()
            return [
                {
                    "date": row["day"],
                    "avg_value": round(float(row["avg_value"]), 4),
                    "count": row["count"],
                }
                for row in rows
            ]
        finally:
            conn.close()

    # ── Rapports synthétiques ──────────────────────────────────────

    def get_summary(self) -> dict:
        """Rapport synthétique de toutes les métriques.

        Calcule les moyennes des dernières 24h pour chaque catégorie
        et retourne un dict structuré.

        Returns:
            dict avec :
            - rag: métriques RAG moyennes
            - response: métriques Réponse moyennes
            - agent: métriques Agent moyennes
            - feedback: métriques Feedback moyennes
            - total_points: nombre total de points de données
            - period_hours: 24
        """
        rag_avgs = self.get_averages(category="rag", since_hours=24)
        response_avgs = self.get_averages(category="response", since_hours=24)
        agent_avgs = self.get_averages(category="agent", since_hours=24)
        feedback_avgs = self.get_averages(category="feedback", since_hours=24)

        conn = self._get_conn()
        try:
            since_ts = time.time() - 86400  # 24h
            total = conn.execute(
                "SELECT COUNT(*) FROM performance_metrics WHERE timestamp >= ?",
                (since_ts,),
            ).fetchone()[0]
        finally:
            conn.close()

        return {
            "rag": {
                "recall@5": rag_avgs.get("rag_recall@5", 0.0),
                "avg_score": rag_avgs.get("rag_avg_score", 0.0),
                "empty_rate": rag_avgs.get("rag_empty", 0.0),
                "hyde_trigger_rate": rag_avgs.get("rag_hyde_trigger", 0.0),
            },
            "response": {
                "avg_response_time_ms": response_avgs.get("response_time_ms", 0.0),
                "avg_tokens": response_avgs.get("response_tokens", 0.0),
                "hallucination_rate": response_avgs.get("response_hallucination", 0.0),
                "citation_rate": response_avgs.get("response_citation", 0.0),
            },
            "agent": {
                "task_success_rate": agent_avgs.get("agent_task_success", 0.0),
                "avg_steps_per_task": agent_avgs.get("agent_steps", 0.0),
                "error_recovery_rate": agent_avgs.get("agent_recovery", 0.0),
            },
            "feedback": {
                "thumbs_up_rate": feedback_avgs.get("feedback_thumbs_up", 0.0),
                "thumbs_down_rate": feedback_avgs.get("feedback_thumbs_down", 0.0),
                "correction_rate": feedback_avgs.get("feedback_correction", 0.0),
                "avg_rating": feedback_avgs.get("feedback_rating", 0.0),
            },
            "total_points": total,
            "period_hours": 24,
        }

    def get_rag_metrics(self) -> dict:
        """Retourne les métriques RAG moyennes des dernières 24h.

        Returns:
            dict : {recall@5, avg_score, empty_rate, hyde_trigger_rate}
        """
        avgs = self.get_averages(category="rag", since_hours=24)
        return {
            "recall@5": avgs.get("rag_recall@5", 0.0),
            "avg_score": avgs.get("rag_avg_score", 0.0),
            "empty_rate": avgs.get("rag_empty", 0.0),
            "hyde_trigger_rate": avgs.get("rag_hyde_trigger", 0.0),
        }

    def get_response_metrics(self) -> dict:
        """Retourne les métriques Réponse moyennes des dernières 24h.

        Returns:
            dict : {avg_response_time_ms, avg_tokens,
                    hallucination_rate, citation_rate}
        """
        avgs = self.get_averages(category="response", since_hours=24)
        return {
            "avg_response_time_ms": avgs.get("response_time_ms", 0.0),
            "avg_tokens": avgs.get("response_tokens", 0.0),
            "hallucination_rate": avgs.get("response_hallucination", 0.0),
            "citation_rate": avgs.get("response_citation", 0.0),
        }

    def get_agent_metrics(self) -> dict:
        """Retourne les métriques Agent moyennes des dernières 24h.

        Returns:
            dict : {task_success_rate, avg_steps_per_task,
                    error_recovery_rate}
        """
        avgs = self.get_averages(category="agent", since_hours=24)
        return {
            "task_success_rate": avgs.get("agent_task_success", 0.0),
            "avg_steps_per_task": avgs.get("agent_steps", 0.0),
            "error_recovery_rate": avgs.get("agent_recovery", 0.0),
        }

    def get_feedback_metrics(self) -> dict:
        """Retourne les métriques Feedback moyennes des dernières 24h.

        Returns:
            dict : {thumbs_up_rate, thumbs_down_rate,
                    correction_rate, avg_rating}
        """
        avgs = self.get_averages(category="feedback", since_hours=24)
        return {
            "thumbs_up_rate": avgs.get("feedback_thumbs_up", 0.0),
            "thumbs_down_rate": avgs.get("feedback_thumbs_down", 0.0),
            "correction_rate": avgs.get("feedback_correction", 0.0),
            "avg_rating": avgs.get("feedback_rating", 0.0),
        }

    def count(self) -> int:
        """Nombre total de métriques enregistrées.

        Returns:
            Nombre d'entrées dans la table performance_metrics
        """
        conn = self._get_conn()
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM performance_metrics"
            ).fetchone()[0]
            return count
        finally:
            conn.close()
