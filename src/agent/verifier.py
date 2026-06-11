"""
NURU V9 — TaskVerifier : vérification des résultats d'étape de tâche.

Pour V9 MVP, la vérification est basée sur :
- La présence d'output non vide
- Le score de confiance
- La comparaison avec expected_output si fourni
- Des règles simples : pas d'erreur, résultat non None
"""

from __future__ import annotations

from typing import Any

from src.agent.types import StepResult, TaskStatus, TaskStep


class TaskVerifier:
    """
    Vérifie le résultat d'une étape de tâche.

    Pour V9 MVP, la vérification est basée sur :
    - La présence d'output non vide
    - Le score de confiance
    - La comparaison avec expected_output si fourni
    - Des règles simples : pas d'erreur, résultat non None
    """

    VERIFICATION_RULES: dict[str, dict[str, Any]] = {
        "search": {"require_non_empty": True, "min_confidence": 0.5},
        "search_rag": {"require_non_empty": True, "min_confidence": 0.5},
        "analyze": {"require_non_empty": True, "min_confidence": 0.6},
        "generate_report": {"require_non_empty": True, "min_confidence": 0.5},
        "create_slides": {"require_non_empty": True, "min_confidence": 0.5},
        "verify": {"require_non_empty": True, "min_confidence": 0.7},
        "summarize": {"require_non_empty": True, "min_confidence": 0.6},
        "default": {"require_non_empty": True, "min_confidence": 0.4},
    }

    # ── Interface publique ──────────────────────────────────────────────

    def verify(
        self,
        step: TaskStep,
        result: StepResult,
    ) -> tuple[bool, float, str]:
        """
        Vérifie le résultat de l'étape.

        Args:
            step: L'étape exécutée (contient expected_output, tool_calls…)
            result: Le résultat de l'exécution

        Returns:
            (is_ok: bool, score: float, reason: str)
              - is_ok : True si le résultat est valide
              - score  : score de vérification calculé
              - reason : explication courte
        """
        # 1. Erreur présente → échec immédiat
        if result.error:
            return (False, 0.0, f"Erreur présente : {result.error}")

        # 2. Statut non COMPLETED → échec
        if result.status != TaskStatus.COMPLETED:
            return (
                False,
                0.0,
                f"Statut incorrect : {result.status.value}",
            )

        # 3. Vérification output non vide
        rule = self._get_rule(step)
        if rule.get("require_non_empty", True):
            if result.output is None:
                return (False, 0.0, "Output est None")
            if isinstance(result.output, str) and not result.output.strip():
                return (False, 0.0, "Output vide")
            if isinstance(result.output, (list, dict)) and len(result.output) == 0:
                return (False, 0.0, "Output vide (collection vide)")

        # 4. Vérification du score de confiance
        min_confidence = rule.get("min_confidence", 0.4)
        if result.confidence < min_confidence:
            return (
                False,
                result.confidence,
                f"Confiance trop basse : {result.confidence:.2f} < {min_confidence}",
            )

        # 5. Vérification expected_output si présent
        if step.expected_output:
            if not self._match_expected(result.output, step.expected_output):
                return (
                    False,
                    result.confidence,
                    f"Output ne correspond pas à l'attendu : '{step.expected_output}'",
                )

        # 6. Tout est OK
        score = self._compute_score(result)
        return (True, score, "Résultat valide")

    # ── Règles de vérification ──────────────────────────────────────────

    def _get_rule(self, step: TaskStep) -> dict[str, Any]:
        """
        Détermine la règle à appliquer selon les outils du step.

        Cherche dans tool_calls le premier outil connu dans VERIFICATION_RULES,
        sinon retourne la règle 'default'.
        """
        for tc in step.tool_calls:
            if tc.tool_name in self.VERIFICATION_RULES:
                return self.VERIFICATION_RULES[tc.tool_name]

        return dict(self.VERIFICATION_RULES["default"])

    # ── Helpers ─────────────────────────────────────────────────────────

    def _compute_score(self, result: StepResult) -> float:
        """Calcule un score de vérification entre 0 et 1."""
        score = result.confidence

        # Bonus si output non vide
        if result.output is not None and result.output != "":
            score = min(1.0, score + 0.1)

        # Bonus si pas d'error
        if result.error is None:
            score = min(1.0, score + 0.05)

        return round(score, 2)

    def _match_expected(self, output: Any, expected: str) -> bool:
        """
        Vérifie si l'output correspond à l'attendu.

        Pour MVP : vérification simple par inclusion de mots-clés
        ou par similarité basique.
        """
        if output is None:
            return False
        output_str = str(output).lower()
        expected_lower = expected.lower()

        # Si l'attendu est un mot-clé ou une phrase, on vérifie l'inclusion
        # Un match est considéré réussi si l'attendu contient l'output
        # ou vice versa (approche souple pour MVP)
        return expected_lower in output_str or output_str in expected_lower
