"""
NURU V10 Sprint 5 — ConfidenceCalibrator.

Calibre le score de confiance et applique le seuil « je ne sais pas ».
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CalibratedResult:
    """Résultat d'un calibrage de confiance."""
    raw_score: float
    calibrated_score: float
    is_confident: bool
    should_answer: bool      # False si score < threshold
    reasoning: str


class ConfidenceCalibrator:
    """Calibrateur de score de confiance avec historique."""

    def __init__(
        self,
        confidence_threshold: float = 0.4,
        high_confidence: float = 0.8,
    ):
        self.confidence_threshold = confidence_threshold
        self.high_confidence = high_confidence
        self.history: list[tuple[float, bool]] = []  # (score, was_correct)

    # ── Calibrage ──────────────────────────────────────────────────

    def calibrate(
        self,
        raw_score: float,
        context_completeness: float = 1.0,
        query_complexity: float = 0.5,
    ) -> CalibratedResult:
        """Calibre le score avec facteurs contexte + complexité."""
        reasons: list[str] = []

        calibrated = raw_score

        # Pénalité contexte incomplet
        if context_completeness < 0.5:
            penalty = (0.5 - context_completeness) * 0.3
            calibrated -= penalty
            reasons.append(
                f"pénalité contexte incomplet ({context_completeness:.2f}): -{penalty:.3f}"
            )

        # Pénalité requête complexe
        if query_complexity > 0.7:
            penalty = (query_complexity - 0.7) * 0.2
            calibrated -= penalty
            reasons.append(
                f"pénalité requête complexe ({query_complexity:.2f}): -{penalty:.3f}"
            )

        # Bornage 0.0 – 1.0
        calibrated = max(0.0, min(1.0, calibrated))

        is_confident = calibrated >= self.high_confidence
        should答_flag = calibrated >= self.confidence_threshold

        if not reasons:
            reasons.append("pas de pénalité")

        return CalibratedResult(
            raw_score=raw_score,
            calibrated_score=calibrated,
            is_confident=is_confident,
            should_answer=should答_flag,
            reasoning="; ".join(reasons),
        )

    # ── Historique ─────────────────────────────────────────────────

    def record_outcome(self, score: float, was_correct: bool):
        """Enregistre un résultat pour calibrage futur."""
        self.history.append((score, was_correct))

    def get_accuracy(self) -> float:
        """Précision historique des scores."""
        if not self.history:
            return 0.0
        correct = sum(1 for _, ok in self.history if ok)
        return correct / len(self.history)

    # ── Décision ───────────────────────────────────────────────────

    def should_answer(self, score: float) -> bool:
        """Décide si NURU doit répondre ou dire « je ne sais pas »."""
        return score >= self.confidence_threshold
