"""
NURU V9 — StrategyOptimizer : ajuste automatiquement les paramètres du système.

Analyse les métriques de performance issues de PerformanceTracker
et produit des ajustements plafonnés pour :
- RAG score threshold
- Cloud-only / routing thresholds
- Suggestions de prompts depuis ErrorMemory

Stocke l'historique des ajustements dans SQLite (adjustment_log).
"""

import json
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

OPTIMIZER_DB = os.path.expanduser("~/.nuru/optimizer.db")


@dataclass
class Adjustment:
    """Un ajustement de paramètre proposé par StrategyOptimizer.

    Attributes:
        param: Nom du paramètre à ajuster
        current: Valeur actuelle
        proposed: Valeur proposée
        reason: Justification textuelle de l'ajustement
        applied: True si l'ajustement a été appliqué
        timestamp: Timestamp Unix de création
    """
    param: str
    current: Any
    proposed: Any
    reason: str = ""
    applied: bool = False
    timestamp: float = 0.0


class StrategyOptimizer:
    """Optimiseur stratégique qui ajuste les paramètres du système.

    Analyser les métriques de performance et produit des ajustements
    plafonnés pour les seuils RAG, de routage, et les suggestions de prompts.

    Règles d'ajustement :
    1. Si rag_empty_rate > 0.30 → baisser rag_score_threshold
    2. Si hallucination_rate > 0.10 → baisser cloud_only_threshold
    3. Si error_memory fourni → suggérer prompt addition
    4. Si task_success_rate < 0.50 → suggérer révision routage
    """

    # Bornes et limites par paramètre
    ADJUSTMENT_LIMITS: dict[str, dict[str, float]] = {
        "rag_score_threshold": {"min": 0.20, "max": 0.60, "delta_max": 0.05},
        "cloud_only_threshold": {"min": 0.30, "max": 0.90, "delta_max": 0.03},
        "routing_confidence": {"min": 0.30, "max": 0.95, "delta_max": 0.03},
    }

    # Métriques critiques analysées
    CRITICAL_METRICS: set[str] = {
        "rag_recall_at_5",
        "hallucination_rate",
        "task_success_rate",
    }

    def __init__(self, db_path: Optional[str] = None, error_memory=None):
        """Initialise l'optimiseur.

        Args:
            db_path: Chemin vers la base SQLite (défaut: ~/.nuru/optimizer.db)
            error_memory: Instance optionnelle de ErrorMemory pour suggestions
        """
        self.db_path = db_path or OPTIMIZER_DB
        self.error_memory = error_memory
        self._ensure_db()

    def _ensure_db(self):
        """Crée la base et la table adjustment_log si nécessaire."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS adjustment_log (
                    id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    param TEXT NOT NULL,
                    old_value TEXT NOT NULL,
                    new_value TEXT NOT NULL,
                    reason TEXT DEFAULT '',
                    applied INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_adjustment_timestamp
                ON adjustment_log(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_adjustment_param
                ON adjustment_log(param)
            """)
            conn.commit()
        finally:
            conn.close()

    def _get_conn(self):
        """Retourne une connexion SQLite avec row_factory activée."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── Analyse ────────────────────────────────────────────────────

    def analyze(self, metrics: dict) -> list[Adjustment]:
        """Analyse les métriques et produit une liste d'ajustements.

        Règles appliquées :
        1. Si rag_empty_rate > 0.30 → baisser rag_score_threshold de delta_max
        2. Si hallucination_rate > 0.10 → baisser cloud_only_threshold de delta_max
        3. Si error_memory fourni → suggérer prompt addition
        4. Si task_success_rate < 0.50 → suggérer révision routage (routing_confidence)

        Args:
            metrics: Dictionnaire de métriques (clés : rag_empty_rate,
                     hallucination_rate, task_success_rate, ...)

        Returns:
            Liste d'objets Adjustment (non appliqués)
        """
        adjustments: list[Adjustment] = []
        now = time.time()

        # Règle 1 : Rag empty rate trop élevé → baisser seuil RAG
        rag_empty_rate = metrics.get("rag_empty_rate", 0.0)
        if rag_empty_rate > 0.30:
            delta = self.ADJUSTMENT_LIMITS["rag_score_threshold"]["delta_max"]
            current = metrics.get("rag_score_threshold", 0.50)
            proposed = max(
                self.ADJUSTMENT_LIMITS["rag_score_threshold"]["min"],
                current - delta,
            )
            adjustments.append(Adjustment(
                param="rag_score_threshold",
                current=current,
                proposed=proposed,
                reason=(
                    f"rag_empty_rate={rag_empty_rate:.2f} > 0.30 : "
                    f"baisse de {current:.2f} à {proposed:.2f}"
                ),
                timestamp=now,
            ))

        # Règle 2 : Hallucination rate trop élevé → baisser cloud_only_threshold
        hallucination_rate = metrics.get("hallucination_rate", 0.0)
        if hallucination_rate > 0.10:
            delta = self.ADJUSTMENT_LIMITS["cloud_only_threshold"]["delta_max"]
            current = metrics.get("cloud_only_threshold", 0.70)
            proposed = max(
                self.ADJUSTMENT_LIMITS["cloud_only_threshold"]["min"],
                current - delta,
            )
            adjustments.append(Adjustment(
                param="cloud_only_threshold",
                current=current,
                proposed=proposed,
                reason=(
                    f"hallucination_rate={hallucination_rate:.2f} > 0.10 : "
                    f"baisse de {current:.2f} à {proposed:.2f}"
                ),
                timestamp=now,
            ))

        # Règle 3 : ErrorMemory disponible → suggérer prompt addition
        if self.error_memory is not None:
            try:
                stats = self.error_memory.get_stats()
                top_types = stats.get("top_types", [])
                if top_types:
                    prompt_suggestion = (
                        f"Attention aux erreurs fréquentes : {', '.join(top_types[:3])}. "
                        "Envisager d'ajuster les prompts pour ces types d'erreur."
                    )
                    adjustments.append(Adjustment(
                        param="prompt_addition",
                        current="",
                        proposed=prompt_suggestion,
                        reason=f"Erreurs fréquentes détectées : {', '.join(top_types[:3])}",
                        timestamp=now,
                    ))
            except Exception as e:
                logger.debug("StrategyOptimizer: erreur consultation ErrorMemory (%s)", e)

        # Règle 4 : Task success rate trop bas → suggérer révision routage
        task_success_rate = metrics.get("task_success_rate", 1.0)
        if task_success_rate < 0.50:
            delta = self.ADJUSTMENT_LIMITS["routing_confidence"]["delta_max"]
            current = metrics.get("routing_confidence", 0.70)
            proposed = max(
                self.ADJUSTMENT_LIMITS["routing_confidence"]["min"],
                current - delta,
            )
            adjustments.append(Adjustment(
                param="routing_confidence",
                current=current,
                proposed=proposed,
                reason=(
                    f"task_success_rate={task_success_rate:.2f} < 0.50 : "
                    f"baisse routage de {current:.2f} à {proposed:.2f}"
                ),
                timestamp=now,
            ))

        return adjustments

    # ── Validation ─────────────────────────────────────────────────

    def validate(self, adjustment: Adjustment) -> bool:
        """Valide qu'un ajustement ne dépasse pas les bornes définies.

        Vérifie :
        - Le paramètre est connu dans ADJUSTMENT_LIMITS
        - La valeur proposée est dans [min, max]
        - Le delta (|proposed - current|) ≤ delta_max

        Pour les paramètres non définis dans ADJUSTMENT_LIMITS
        (comme 'prompt_addition'), la validation passe toujours.

        Args:
            adjustment: L'ajustement à valider

        Returns:
            True si l'ajustement est valide, False sinon
        """
        limits = self.ADJUSTMENT_LIMITS.get(adjustment.param)

        # Paramètre non limité (ex: prompt_addition) → toujours valide
        if limits is None:
            return True

        # Vérifier les bornes
        proposed = adjustment.proposed
        if isinstance(proposed, (int, float)):
            if proposed < limits["min"] or proposed > limits["max"]:
                logger.debug(
                    "Ajustement %s hors bornes [%s, %s] : %s",
                    adjustment.param, limits["min"], limits["max"], proposed,
                )
                return False

            # Vérifier le delta max
            current = adjustment.current
            if isinstance(current, (int, float)):
                delta = abs(proposed - current)
                if delta > limits["delta_max"]:
                    logger.debug(
                        "Delta ajustement %s trop grand : %s > %s",
                        adjustment.param, delta, limits["delta_max"],
                    )
                    return False

        return True

    # ── Application ────────────────────────────────────────────────

    def apply(self, adjustment: Adjustment) -> bool:
        """Applique un ajustement validé et l'enregistre dans l'historique.

        L'ajustement est d'abord validé. S'il est valide, il est marqué
        comme appliqué et enregistré dans la table adjustment_log.

        Args:
            adjustment: L'ajustement à appliquer

        Returns:
            True si l'ajustement a été appliqué avec succès, False sinon
        """
        if not self.validate(adjustment):
            return False

        adjustment.applied = True
        adjustment_id = str(uuid.uuid4())

        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO adjustment_log
                   (id, timestamp, param, old_value, new_value, reason, applied)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    adjustment_id,
                    adjustment.timestamp or time.time(),
                    adjustment.param,
                    str(adjustment.current),
                    str(adjustment.proposed),
                    adjustment.reason,
                    1 if adjustment.applied else 0,
                ),
            )
            conn.commit()
            logger.info(
                "Ajustement appliqué : %s : %s → %s (%s)",
                adjustment.param, adjustment.current, adjustment.proposed,
                adjustment.reason,
            )
            return True
        except Exception as e:
            logger.error("Erreur application ajustement : %s", e)
            return False
        finally:
            conn.close()

    # ── Historique ─────────────────────────────────────────────────

    def get_history(self, limit: int = 20) -> list[dict]:
        """Retourne l'historique des ajustements appliqués.

        Les entrées sont triées par timestamp décroissant.

        Args:
            limit: Nombre maximum d'entrées à retourner

        Returns:
            Liste de dicts avec les clés : id, timestamp, param,
            old_value, new_value, reason, applied
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT id, timestamp, param, old_value, new_value,
                          reason, applied
                   FROM adjustment_log
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "param": row["param"],
                    "old_value": row["old_value"],
                    "new_value": row["new_value"],
                    "reason": row["reason"],
                    "applied": bool(row["applied"]),
                }
                for row in rows
            ]
        finally:
            conn.close()

    # ── Résumé ─────────────────────────────────────────────────────

    def get_summary(self) -> dict:
        """Produit un résumé des ajustements.

        Returns:
            dict avec :
            - total_adjustments: nombre total d'ajustements appliqués
            - params_modified: nombre de paramètres distincts modifiés
            - by_param: dict {param: count}
            - trend: tendance récente (liste des 5 derniers ajustements)
            - recent_week_count: nombre d'ajustements dans la dernière semaine
        """
        conn = self._get_conn()
        try:
            # Total
            total = conn.execute(
                "SELECT COUNT(*) FROM adjustment_log WHERE applied = 1"
            ).fetchone()[0]

            # Par paramètre
            by_param_rows = conn.execute(
                """SELECT param, COUNT(*) as cnt
                   FROM adjustment_log WHERE applied = 1
                   GROUP BY param ORDER BY cnt DESC"""
            ).fetchall()
            by_param = {row["param"]: row["cnt"] for row in by_param_rows}

            # Paramètres distincts
            params_modified = len(by_param)

            # Tendances : 5 derniers
            trend_rows = conn.execute(
                """SELECT param, old_value, new_value, reason, timestamp
                   FROM adjustment_log WHERE applied = 1
                   ORDER BY timestamp DESC LIMIT 5"""
            ).fetchall()
            trend = [
                {
                    "param": row["param"],
                    "from": row["old_value"],
                    "to": row["new_value"],
                    "reason": row["reason"],
                    "timestamp": row["timestamp"],
                }
                for row in trend_rows
            ]

            # Dernière semaine
            week_ago = time.time() - 7 * 24 * 3600
            recent_week_count = conn.execute(
                "SELECT COUNT(*) FROM adjustment_log WHERE applied = 1 AND timestamp >= ?",
                (week_ago,),
            ).fetchone()[0]

        finally:
            conn.close()

        return {
            "total_adjustments": total,
            "params_modified": params_modified,
            "by_param": by_param,
            "trend": trend,
            "recent_week_count": recent_week_count,
        }
