"""
NURU V10 Sprint 5 — SelfConsistency.

Vote majoritaire sur N réponses pour améliorer la fiabilité
par redondance et consensus.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class ConsistencyResult:
    """Résultat d'un vote de cohérence."""
    answers: list[str]
    frequencies: dict[str, int]   # réponse normalisée → nombre d'occurrences
    majority_answer: str
    confidence: float             # ratio de la réponse majoritaire
    is_consistent: bool           # True si > threshold d'accord


class SelfConsistency:
    """Vote majoritaire sur plusieurs générations de réponses."""

    def __init__(self, n_samples: int = 3, consistency_threshold: float = 0.6):
        self.n_samples = n_samples
        self.consistency_threshold = consistency_threshold

    # ── Normalisation ──────────────────────────────────────────────

    @staticmethod
    def normalize_answer(answer: str) -> str:
        """Normalise une réponse pour la comparaison."""
        if not answer:
            return ""
        # Minuscule + suppression ponctuation + espaces multiples
        normalized = answer.lower().strip()
        normalized = re.sub(r'[^\w\s]', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        return normalized

    # ── Vote ───────────────────────────────────────────────────────

    def vote(self, answers: list[str]) -> ConsistencyResult:
        """Compte les fréquences et retourne la réponse majoritaire."""
        if not answers:
            return ConsistencyResult(
                answers=[],
                frequencies={},
                majority_answer="",
                confidence=0.0,
                is_consistent=False,
            )

        normalized = [self.normalize_answer(a) for a in answers]
        counter = Counter(normalized)
        frequencies = dict(counter)

        most_common = counter.most_common(1)[0]
        majority_answer_norm, count = most_common
        confidence = count / len(normalized)

        # Recherche de la réponse originale correspondante à la majoritaire
        majority_original = ""
        for orig, norm in zip(answers, normalized):
            if norm == majority_answer_norm:
                majority_original = orig
                break

        is_consistent = confidence >= self.consistency_threshold

        return ConsistencyResult(
            answers=answers,
            frequencies=frequencies,
            majority_answer=majority_original,
            confidence=confidence,
            is_consistent=is_consistent,
        )

    # ── Fusion ─────────────────────────────────────────────────────

    @staticmethod
    def merge(answers: list[str]) -> str:
        """Fusionne les réponses en gardant la plus complète."""
        if not answers:
            return ""
        if len(answers) == 1:
            return answers[0]

        # Retourne la réponse la plus longue (la plus détaillée)
        return max(answers, key=len)
