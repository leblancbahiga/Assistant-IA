"""NURU V15 Phase 4 — ConfidenceCalibrator (P1 #33).

Calibre les scores de confiance des résultats RAG en fusionnant
BM25, embedding cosine et scores du reranker en un score calibré [0,1],
puis en un label HAUTE/MOYENNE/FAIBLE/ABSENT.

Apprend des retours utilisateur pour ajuster les seuils dynamiquement.
Stocke les métriques de calibration dans la DB mémoire.
"""

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Seuils par défaut (optimisés pour M1 8 Go) ───────────────────────
DEFAULT_THRESHOLDS = {
    "absenth": 0.15,
    "faible": 0.35,
    "moyenne": 0.60,
    "haute": 0.80,
}

DB_PATH = Path.home() / ".nuru" / "calibration.db"


@dataclass
class CalibratedScore:
    """Score calibré avec labels et métriques de qualité."""
    raw_bm25: float = 0.0
    raw_embedding: float = 0.0
    raw_reranker: float = 0.0
    ensemble_score: float = 0.0
    label: str = "ABSENT"
    confidence: float = 0.0  # calibration uncertainty
    n_samples: int = 0       # feedback samples for this score range


class ConfidenceCalibrator:
    """Calibre les scores RAG en labels stables.

    Fusionne BM25 + embedding + reranker en un score ensemble pondéré,
    puis applique des seuils ajustables. Les retours utilisateur corrigent
    les seuils via l'écart entre score prédit et qualité réelle.

    Usage:
        cal = ConfidenceCalibrator()
        result = cal.calibrate(
            bm25_score=0.45,
            embedding_score=0.72,
            reranker_score=0.61,
        )
        # result.label = "MOYENNE", result.ensemble_score = 0.59
        cal.record_feedback(bm25_score=0.45, was_good=True)
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        thresholds: Optional[dict[str, float]] = None,
        weights: Optional[dict[str, float]] = None,
    ):
        self.db_path = db_path or str(DB_PATH)
        self.thresholds = dict(thresholds or DEFAULT_THRESHOLDS)
        self.weights = weights or {
            "bm25": 0.20,
            "embedding": 0.35,
            "reranker": 0.45,
        }
        self._init_db()

    def _init_db(self):
        """Crée la table de calibration si absente."""
        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS calibration_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    bm25_score REAL NOT NULL,
                    embedding_score REAL NOT NULL,
                    reranker_score REAL NOT NULL,
                    ensemble_score REAL NOT NULL,
                    predicted_label TEXT NOT NULL,
                    was_good INTEGER NOT NULL,
                    corrected_label TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS calibration_stats (
                    key TEXT PRIMARY KEY,
                    value REAL NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def calibrate(
        self,
        bm25_score: float = 0.0,
        embedding_score: float = 0.0,
        reranker_score: float = 0.0,
    ) -> CalibratedScore:
        """Calcule le score calibré et le label.

        Args:
            bm25_score: Score BM25 normalisé [0,1]
            embedding_score: Score cosine embedding [0,1]
            reranker_score: Score reranker cross-encoder [0,1]

        Returns:
            CalibratedScore avec label et métriques
        """
        # Score ensemble = moyenne pondérée
        ensemble = (
            self.weights["bm25"] * bm25_score
            + self.weights["embedding"] * embedding_score
            + self.weights["reranker"] * reranker_score
        )
        ensemble = max(0.0, min(1.0, ensemble))

        # Label selon seuils
        label = self._score_to_label(ensemble)

        # Incertitude de calibration basée sur l'écart des scores
        scores = [bm25_score, embedding_score, reranker_score]
        if any(s > 0 for s in scores):
            spread = max(scores) - min(scores)
            confidence = 1.0 - (spread * 0.5)
        else:
            confidence = 0.0

        # Récupérer le nombre d'échantillons similaires
        n_samples = self._get_feedback_count(ensemble)

        return CalibratedScore(
            raw_bm25=bm25_score,
            raw_embedding=embedding_score,
            raw_reranker=reranker_score,
            ensemble_score=round(ensemble, 4),
            label=label,
            confidence=round(confidence, 3),
            n_samples=n_samples,
        )

    def _score_to_label(self, score: float) -> str:
        """Mappe un score [0,1] vers un label."""
        if score < self.thresholds["absenth"]:
            return "ABSENT"
        if score < self.thresholds["faible"]:
            return "FAIBLE"
        if score < self.thresholds["moyenne"]:
            return "MOYENNE"
        if score < self.thresholds["haute"]:
            return "HAUTE"
        return "HAUTE"

    def record_feedback(
        self,
        bm25_score: float,
        embedding_score: float = 0.0,
        reranker_score: float = 0.0,
        was_good: bool = True,
        corrected_label: Optional[str] = None,
    ):
        """Enregistre un feedback utilisateur pour ajuster les seuils.

        Args:
            bm25_score: Score BM25 observé
            embedding_score: Score embedding observé
            reranker_score: Score reranker observé
            was_good: La réponse était-elle bonne ?
            corrected_label: Label manuel si l'utilisateur l'a corrigé
        """
        # Calculer le score ensemble au moment du feedback
        ensemble = (
            self.weights["bm25"] * bm25_score
            + self.weights["embedding"] * embedding_score
            + self.weights["reranker"] * reranker_score
        )
        predicted = self._score_to_label(ensemble)

        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            conn.execute(
                """INSERT INTO calibration_feedback
                   (timestamp, bm25_score, embedding_score, reranker_score,
                    ensemble_score, predicted_label, was_good, corrected_label)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (time.time(), bm25_score, embedding_score, reranker_score,
                 ensemble, predicted, int(was_good), corrected_label),
            )
            conn.commit()
        finally:
            conn.close()

        # Ajustement incrémental des seuils (tous les 10 feedbacks)
        total = self._get_total_feedback()
        if total > 0 and total % 10 == 0:
            self._recalibrate_thresholds()

    def _get_feedback_count(self, score: float, window: float = 0.1) -> int:
        """Compte les feedbacks dans une fenêtre autour du score."""
        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM calibration_feedback "
                "WHERE ensemble_score BETWEEN ? AND ?",
                (score - window, score + window),
            ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def _get_total_feedback(self) -> int:
        """Retourne le nombre total de feedbacks enregistrés."""
        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM calibration_feedback"
            ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def _recalibrate_thresholds(self):
        """Réajuste les seuils à partir de l'historique des feedbacks.

        Calcule, pour chaque niveau de score, la proportion de bons feedbacks
        et ajuste les seuils pour maximiser la précision.
        """
        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            rows = conn.execute(
                "SELECT ensemble_score, was_good, predicted_label "
                "FROM calibration_feedback ORDER BY ensemble_score"
            ).fetchall()
        finally:
            conn.close()

        if not rows or len(rows) < 10:
            return

        # Regrouper par décile de score
        bins: dict[int, list[bool]] = {}
        for score, was_good, _ in rows:
            decile = int(score * 10)  # 0-10
            bins.setdefault(decile, []).append(bool(was_good))

        # Trouver les seuils où la précision baisse en dessous de 70%
        new_thresholds: dict[str, float] = dict(self.thresholds)

        for decile in sorted(bins.keys()):
            if decile == 10:
                continue
            good = sum(bins[decile])
            total = len(bins[decile])
            accuracy = good / total if total > 0 else 0

            if decile <= 1 and accuracy < 0.5:
                new_thresholds["absenth"] = max(
                    0.05, (decile + 1) / 10.0 - 0.05
                )
            elif decile <= 3 and accuracy < 0.6:
                new_thresholds["faible"] = max(
                    0.15, (decile + 1) / 10.0 - 0.05
                )
            elif decile <= 5 and accuracy < 0.7:
                new_thresholds["moyenne"] = max(
                    0.35, (decile + 1) / 10.0 - 0.05
                )

        # Sauvegarder les nouveaux seuils
        self.thresholds = new_thresholds
        logger.info(
            "🎯 ConfidenceCalibrator : seuils recalibrés → %s",
            new_thresholds,
        )

    def stats(self) -> dict:
        """Retourne les statistiques de calibration."""
        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            total_fb = conn.execute(
                "SELECT COUNT(*) FROM calibration_feedback"
            ).fetchone()[0]
            good_fb = conn.execute(
                "SELECT COUNT(*) FROM calibration_feedback WHERE was_good=1"
            ).fetchone()[0]
            return {
                "total_feedback": total_fb,
                "good_feedback": good_fb,
                "accuracy_pct": round(
                    good_fb / total_fb * 100, 1
                ) if total_fb > 0 else 0.0,
                "thresholds": dict(self.thresholds),
            }
        finally:
            conn.close()
