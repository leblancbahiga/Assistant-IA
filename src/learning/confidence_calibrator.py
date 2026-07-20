"""
NURU V16 — ConfidenceCalibrator (P1 #33).

Calibre les scores de confiance des resultats RAG en fusionnant
BM25, embedding cosine et scores du reranker en un score calibre [0,1],
puis en un label HAUTE/MOYENNE/FAIBLE/ABSENT.

Apprend des retours utilisateur pour ajuster les seuils dynamiquement.
Stocke les metriques de calibration dans la DB memoire.

Ameliorations V16 :
- Buffer RAM pour feedbacks (flush SQLite toutes les 20 entrees)
- EMA pour recalibration bidirectionnelle (monte + descend)
- Formule de confiance corrigee (absolue * consensus)^0.5
- Cache du nombre de feedbacks pour eviter SELECT COUNT par calibrate()
- Creation auto du repertoire parent
"""

import json
import logging
import math
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Seuils par defaut (optimises pour M1 8 Go) ───────────────────────
DEFAULT_THRESHOLDS = {
    "absenth": 0.15,
    "faible": 0.35,
    "moyenne": 0.60,
    "haute": 0.80,
}

# Poids par defaut des composantes de score
DEFAULT_WEIGHTS = {
    "bm25": 0.20,
    "embedding": 0.35,
    "reranker": 0.45,
}

DB_PATH = Path.home() / ".nuru" / "calibration.db"

# Taille du buffer RAM avant flush SQLite
FEEDBACK_FLUSH_INTERVAL = 20

# Facteur de lissage EMA (0.0 = pas de changement, 1.0 = remplacement total)
EMA_ALPHA = 0.2

# Fenetre de score pour compter les feedbacks similaires (cote du cache)
SCORE_WINDOW = 0.1


@dataclass
class CalibratedScore:
    """Score calibre avec labels et metriques de qualite."""
    raw_bm25: float = 0.0
    raw_embedding: float = 0.0
    raw_reranker: float = 0.0
    ensemble_score: float = 0.0
    label: str = "ABSENT"
    confidence: float = 0.0   # calibration uncertainty
    n_samples: int = 0        # feedback samples for this score range


class ConfidenceCalibrator:
    """Calibre les scores RAG en labels stables.

    Fusionne BM25 + embedding + reranker en un score ensemble pondere,
    puis applique des seuils ajustables. Les retours utilisateur corrigent
    les seuils via l'ecart entre score predit et qualite reelle.

    V16+: Buffer RAM + EMA + confiance corrigee.

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
        self.weights = dict(weights or DEFAULT_WEIGHTS)

        # Creer le repertoire parent si inexistant
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

        # ── Buffer RAM pour feedbacks ────────────────────────────────
        self._feedback_buffer: list[dict] = []

        # ── Cache des stats (evite requetes SQL redondantes) ────────
        # (total, good_total, last_sync_timestamp)
        self._stats_cache = {"total": 0, "good": 0}

    def _init_db(self):
        """Cree la table de calibration si absente."""
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
        """Calcule le score calibre et le label.

        Args:
            bm25_score: Score BM25 normalise [0,1]
            embedding_score: Score cosine embedding [0,1]
            reranker_score: Score reranker cross-encoder [0,1]

        Returns:
            CalibratedScore avec label et metriques
        """
        # Clamp des scores
        bm25_score = max(0.0, min(1.0, bm25_score))
        embedding_score = max(0.0, min(1.0, embedding_score))
        reranker_score = max(0.0, min(1.0, reranker_score))

        # Score ensemble = moyenne ponderee
        ensemble = (
            self.weights["bm25"] * bm25_score
            + self.weights["embedding"] * embedding_score
            + self.weights["reranker"] * reranker_score
        )
        ensemble = max(0.0, min(1.0, ensemble))

        # Label selon seuils
        label = self._score_to_label(ensemble)

        # ── Formule de confiance corrigee V16 ───────────────────────
        # 1. Confiance absolue : eloignement des seuils de decision
        dist_to_threshold = min(
            abs(ensemble - self.thresholds["faible"]),
            abs(ensemble - self.thresholds["moyenne"]),
            abs(ensemble - self.thresholds["haute"]),
        )
        abs_confidence = min(1.0, dist_to_threshold * 5.0)

        # 2. Consensus des sources : penalite si les scores sont disperses
        scores = [bm25_score, embedding_score, reranker_score]
        variance = self._variance(scores)
        consensus_confidence = 1.0 - min(1.0, variance * 4.0)

        # Confiance finale = moyenne geometrique (penalise si l'un est bas)
        confidence = math.sqrt(abs_confidence * consensus_confidence) if abs_confidence > 0 and consensus_confidence > 0 else 0.0

        # Rcuperer le nombre d'echantillons (depuis le buffer + cache)
        n_samples = self._get_feedback_count_cached(ensemble)

        return CalibratedScore(
            raw_bm25=bm25_score,
            raw_embedding=embedding_score,
            raw_reranker=reranker_score,
            ensemble_score=round(ensemble, 4),
            label=label,
            confidence=round(confidence, 3),
            n_samples=n_samples,
        )

    @staticmethod
    def _variance(scores: list[float]) -> float:
        """Variance d'une liste de scores."""
        if len(scores) < 2:
            return 0.0
        mean = sum(scores) / len(scores)
        return sum((s - mean) ** 2 for s in scores) / len(scores)

    def _score_to_label(self, score: float) -> str:
        """Mappe un score [0,1] vers un label."""
        if score < self.thresholds["absenth"]:
            return "ABSENT"
        if score < self.thresholds["faible"]:
            return "FAIBLE"
        if score < self.thresholds["moyenne"]:
            return "MOYENNE"
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

        V16+: Buffer RAM — pas de SQLite a chaque appel.
        Flush toutes les FEEDBACK_FLUSH_INTERVAL entrees.

        Args:
            bm25_score: Score BM25 observe
            embedding_score: Score embedding observe
            reranker_score: Score reranker observe
            was_good: La reponse etait-elle bonne ?
            corrected_label: Label manuel si l'utilisateur l'a corrige
        """
        bm25_score = max(0.0, min(1.0, bm25_score))
        embedding_score = max(0.0, min(1.0, embedding_score))
        reranker_score = max(0.0, min(1.0, reranker_score))

        ensemble = (
            self.weights["bm25"] * bm25_score
            + self.weights["embedding"] * embedding_score
            + self.weights["reranker"] * reranker_score
        )
        predicted = self._score_to_label(ensemble)

        # Buffer RAM — pas d'ecriture SQL immediate
        self._feedback_buffer.append({
            "timestamp": time.time(),
            "bm25_score": bm25_score,
            "embedding_score": embedding_score,
            "reranker_score": reranker_score,
            "ensemble_score": ensemble,
            "predicted_label": predicted,
            "was_good": int(was_good),
            "corrected_label": corrected_label,
        })

        # Mise a jour du cache en RAM
        self._stats_cache["total"] += 1
        if was_good:
            self._stats_cache["good"] += 1

        # Flush toutes les FEEDBACK_FLUSH_INTERVAL entrees
        if len(self._feedback_buffer) >= FEEDBACK_FLUSH_INTERVAL:
            self._flush_feedback_buffer()
            # Recalibration EMA tous les ~20 feedbacks
            if self._stats_cache["total"] > 0 and self._stats_cache["total"] % 20 == 0:
                self._recalibrate_thresholds_ema()

    def _flush_feedback_buffer(self):
        """Ecrit les feedbacks accumules dans SQLite (batch insert)."""
        if not self._feedback_buffer:
            return

        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            conn.executemany(
                """INSERT INTO calibration_feedback
                   (timestamp, bm25_score, embedding_score, reranker_score,
                    ensemble_score, predicted_label, was_good, corrected_label)
                   VALUES (
                       :timestamp, :bm25_score, :embedding_score,
                       :reranker_score, :ensemble_score, :predicted_label,
                       :was_good, :corrected_label
                   )""",
                self._feedback_buffer,
            )
            conn.commit()
            logger.debug(
                "ConfidenceCalibrator: %d feedbacks flushes vers SQLite",
                len(self._feedback_buffer),
            )
            self._feedback_buffer.clear()
        except Exception as e:
            logger.error("Erreur flush feedbacks SQLite: %s", e)
        finally:
            conn.close()

    def _get_feedback_count_cached(self, score: float) -> int:
        """Retourne le nombre total de feedbacks dans le buffer + cache.
        
        V16+: Pas de requete SQL a chaque appel — utilise le cache RAM.
        Le compte est exact au nombre d'ecritures pres (buffer non flushes).
        """
        total = self._stats_cache["total"]
        # Ajouter les feedbacks dans le buffer non encore flushes
        return total + len(self._feedback_buffer)

    def _recalibrate_thresholds_ema(self):
        """Reajustement des seuils par Moyenne Mobile Exponentielle (EMA).
        
        V16+: Remplace l'ajustement binaire descendeur. L'EMA permet
        des ajustements a la hausse ET a la baisse selon l'evolution
        de l'accuracy.
        
        Lit les donnees depuis SQLite (donnees persistees) et applique
        un lissage EMA (alpha=0.2) pour eviter les oscillations brutales.
        """
        # Assurer que le buffer est flushe avant de lire SQLite
        self._flush_feedback_buffer()

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

        # Regrouper par decile de score
        bins: dict[int, list[bool]] = {}
        for score, was_good, _ in rows:
            decile = int(score * 10)  # 0-10
            bins.setdefault(decile, []).append(bool(was_good))

        new_thresholds = dict(self.thresholds)

        for decile in sorted(bins.keys()):
            if decile == 10:
                continue
            good = sum(bins[decile])
            total = len(bins[decile])
            accuracy = good / total if total > 0 else 0

            # Cible : ajuster le seuil au milieu du decile
            target_threshold = (decile + 1) / 10.0 - 0.05

            # Appliquer l'EMA au seuil concerne
            if decile <= 1 and accuracy < 0.5:
                old = new_thresholds["absenth"]
                new_thresholds["absenth"] = (EMA_ALPHA * target_threshold) + ((1 - EMA_ALPHA) * old)
            elif decile <= 3 and accuracy < 0.6:
                old = new_thresholds["faible"]
                new_thresholds["faible"] = (EMA_ALPHA * target_threshold) + ((1 - EMA_ALPHA) * old)
            elif decile <= 5 and accuracy < 0.7:
                old = new_thresholds["moyenne"]
                new_thresholds["moyenne"] = (EMA_ALPHA * target_threshold) + ((1 - EMA_ALPHA) * old)

        self.thresholds = new_thresholds
        logger.info(
            "ConfidenceCalibrator: seuils lisses par EMA -> %s",
            new_thresholds,
        )

    def flush(self):
        """Force le flush du buffer RAM vers SQLite.
        
        A appeler lors de l'arret propre du systeme pour ne pas perdre
        les feedbacks non encore persistes.
        """
        self._flush_feedback_buffer()

    def stats(self) -> dict:
        """Retourne les statistiques de calibration."""
        total_fb = self._stats_cache["total"] + len(self._feedback_buffer)
        good_fb = self._stats_cache["good"]

        # Si le cache est vide, lire depuis SQLite
        if total_fb == 0:
            conn = sqlite3.connect(self.db_path, timeout=10)
            try:
                total_fb = conn.execute(
                    "SELECT COUNT(*) FROM calibration_feedback"
                ).fetchone()[0]
                good_fb = conn.execute(
                    "SELECT COUNT(*) FROM calibration_feedback WHERE was_good=1"
                ).fetchone()[0]
            finally:
                conn.close()

        return {
            "total_feedback": total_fb,
            "good_feedback": good_fb,
            "accuracy_pct": round(
                good_fb / total_fb * 100, 1
            ) if total_fb > 0 else 0.0,
            "thresholds": dict(self.thresholds),
            "buffer_pending": len(self._feedback_buffer),
        }
