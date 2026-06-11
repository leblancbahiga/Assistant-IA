"""
NURU V10 Sprint 5 — ReflexionEngine.

Boucle d'auto-critique avec 2 passes max :
une réponse initiale est évaluée, puis si le score est bas,
le système reformule et améliore.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ReflexionResult:
    """Résultat complet d'une boucle de réflexion."""
    initial_answer: str
    critique: str
    improved_answer: str
    score_initial: float   # 0.0 à 1.0
    score_final: float
    passes: int
    improvement: float     # score_final - score_initial


class ReflexionEngine:
    """Moteur d'auto-critique itératif (max 2 passes)."""

    def __init__(self, max_passes: int = 2, min_score: float = 0.6):
        self.max_passes = max_passes
        self.min_score = min_score

    # ── Scoring helpers ────────────────────────────────────────────

    @staticmethod
    def _score(answer: str, context: str) -> float:
        """Score heuristique 0.0‑1.0 basé sur longueur et mots‑clés."""
        if not answer or not answer.strip():
            return 0.0

        score = 0.0
        words = answer.split()
        word_count = len(words)

        # Critère longueur (max 0.4)
        if word_count < 5:
            score += 0.1
        elif word_count < 20:
            score += 0.2
        elif word_count < 50:
            score += 0.3
        else:
            score += 0.4

        # Critère mots‑clés du contexte (max 0.6)
        context_words = set(re.findall(r'\w+', context.lower()))
        answer_lower = answer.lower()
        if context_words:
            hits = sum(1 for w in context_words if w in answer_lower)
            score += 0.6 * (hits / len(context_words))
        else:
            score += 0.4  # pas de contexte → bonus modéré

        return min(score, 1.0)

    # ── Critique ───────────────────────────────────────────────────

    def critique(self, answer: str, context: str) -> str:
        """Évalue la réponse et retourne une critique textuelle."""
        if not answer or not answer.strip():
            return "Réponse vide. Il faut fournir une réponse non vide."

        words = answer.split()
        if len(words) < 20:
            return "Réponse trop courte. Il faut ajouter plus de détails."

        context_words = set(re.findall(r'\w+', context.lower()))
        answer_lower = answer.lower()
        missing = [w for w in context_words if w not in answer_lower]
        if missing:
            return (
                "Mots-clés du contexte absents : "
                + ", ".join(sorted(missing))
            )

        return "Réponse acceptable."

    # ── Amélioration ───────────────────────────────────────────────

    def improve(self, answer: str, critique: str, context: str) -> str:
        """Améliore la réponse en fonction de la critique."""
        if "trop courte" in critique:
            # Ajoute du détail contextuel
            context_words = set(re.findall(r'\w+', context))
            extras = " ".join(sorted(context_words)[:5])
            return (
                f"{answer} Détails supplémentaires issus du contexte : {extras}."
            )

        if "absent" in critique:
            # Extrait les mots manquants depuis la critique
            match = re.search(r'absents\s*:\s*(.*)', critique)
            if match:
                missing_str = match.group(1).strip()
                return (
                    f"{answer} Il convient également d'aborder : {missing_str}."
                )

        return answer

    # ── Boucle complète ────────────────────────────────────────────

    def reflect(self, answer: str, context: str) -> ReflexionResult:
        """Boucle complète : critique + amélioration jusqu'à max_passes."""
        initial = answer
        current = answer
        first_critique = ""
        passes_done = 0
        score_initial = 0.0
        score_final = 0.0

        for i in range(self.max_passes):
            score = self._score(current, context)
            if i == 0:
                score_initial = score

            critique_text = self.critique(current, context)

            if i == 0:
                first_critique = critique_text

            # Si le score est déjà suffisant → on arrête
            if score >= self.min_score and i > 0:
                score_final = score
                passes_done = i + 1
                break

            improved = self.improve(current, critique_text, context)
            current = improved
            score_final = self._score(current, context)
            passes_done = i + 1

            if score_final >= self.min_score:
                break

        return ReflexionResult(
            initial_answer=initial,
            critique=first_critique,
            improved_answer=current,
            score_initial=score_initial,
            score_final=score_final,
            passes=passes_done,
            improvement=score_final - score_initial,
        )
