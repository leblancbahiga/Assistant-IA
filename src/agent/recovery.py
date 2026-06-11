"""
NURU V9 — ErrorRecovery : stratégies de récupération par type d'erreur.

Pour chaque type d'erreur, une liste ordonnée de stratégies :
la première est tentée en priorité, on descend dans la liste à chaque retry.
"""

from __future__ import annotations

from typing import Any, Optional

from src.agent.types import ErrorType, RecoveryAction, RecoveryDecision


class ErrorRecovery:
    """
    Stratégies de recovery par type d'erreur.

    Pour chaque type d'erreur, une liste ordonnée de stratégies :
    la première est tentée en priorité, on descend dans la liste à chaque retry.
    """

    STRATEGIES: dict[ErrorType, list[RecoveryAction]] = {
        ErrorType.TOOL_FAILURE: [
            RecoveryAction.RETRY,
            RecoveryAction.ALTERNATIVE_TOOL,
            RecoveryAction.SIMPLIFY,
            RecoveryAction.ASK_USER,
        ],
        ErrorType.TIMEOUT: [
            RecoveryAction.RETRY,
            RecoveryAction.PARTIAL_RESULT,
        ],
        ErrorType.HALLUCINATION_DETECTED: [
            RecoveryAction.REGENERATE_STRICT,
            RecoveryAction.FALLBACK_TO_RAG,
        ],
        ErrorType.LOW_CONFIDENCE: [
            RecoveryAction.SEARCH_MORE,
            RecoveryAction.ASK_USER,
        ],
        ErrorType.RAM_EXCEEDED: [
            RecoveryAction.REDUCE_BATCH,
            RecoveryAction.UNLOAD_MODELS,
        ],
        ErrorType.NETWORK_ERROR: [
            RecoveryAction.RETRY_BACKOFF,
            RecoveryAction.OFFLINE_FALLBACK,
        ],
        ErrorType.USER_CANCELLED: [
            RecoveryAction.ASK_USER,
        ],
        ErrorType.UNKNOWN: [
            RecoveryAction.RETRY,
            RecoveryAction.ASK_USER,
        ],
    }

    # Message d'aide par stratégie
    STRATEGY_MESSAGES: dict[RecoveryAction, str] = {
        RecoveryAction.RETRY: "Nouvelle tentative d'exécution",
        RecoveryAction.ALTERNATIVE_TOOL: "Utilisation d'un outil alternatif",
        RecoveryAction.SIMPLIFY: "Simplification de la requête",
        RecoveryAction.ASK_USER: "Demande d'information à l'utilisateur",
        RecoveryAction.FALLBACK_TO_RAG: "Repli sur la base de connaissances RAG",
        RecoveryAction.REGENERATE_STRICT: "Régénération avec contraintes strictes",
        RecoveryAction.REDUCE_BATCH: "Réduction de la taille du lot",
        RecoveryAction.UNLOAD_MODELS: "Déchargement des modèles inutilisés",
        RecoveryAction.OFFLINE_FALLBACK: "Mode hors-ligne activé",
        RecoveryAction.ESCALATE: "Escalade vers l'utilisateur",
        RecoveryAction.PARTIAL_RESULT: "Retour du résultat partiel",
        RecoveryAction.SEARCH_MORE: "Recherche de sources supplémentaires",
        RecoveryAction.RETRY_BACKOFF: "Nouvelle tentative avec backoff exponentiel",
    }

    # ── Interface publique ──────────────────────────────────────────────

    def decide(
        self,
        error_type: ErrorType,
        attempt: int = 0,
        context: Optional[dict[str, Any]] = None,
    ) -> RecoveryDecision:
        """
        Décide de l'action de recovery.

        Args:
            error_type: Le type d'erreur rencontrée
            attempt:    Numéro de tentative (0 = première)
            context:    Contexte optionnel pour enrichir la décision

        Returns:
            RecoveryDecision avec action, params, et message

        Règles :
            - attempt=0 : première stratégie dans la liste
            - attempt=N : Nième stratégie (ou dernière si dépassé)
            - Si toutes les stratégies sont épuisées : ESCALATE
        """
        strategies = self.STRATEGIES.get(error_type, [RecoveryAction.ASK_USER])

        # Si attempt dépasse le nombre de stratégies disponibles
        if attempt >= len(strategies):
            action = RecoveryAction.ESCALATE
            params = {
                "error_type": error_type.value,
                "attempt": attempt,
                "strategies_exhausted": [s.value for s in strategies],
            }
            message = (
                f"Toutes les stratégies épuisées après {attempt+1} tentative(s) "
                f"pour {error_type.value}. Escalade nécessaire."
            )
        else:
            action = strategies[attempt]
            params = {
                "error_type": error_type.value,
                "attempt": attempt,
                "strategy_index": attempt,
            }
            message = self.STRATEGY_MESSAGES.get(
                action,
                f"Application de la stratégie {action.value}",
            )

            # Ajouter des paramètres spécifiques selon l'action
            if action == RecoveryAction.RETRY_BACKOFF:
                backoff_seconds = min(2 ** attempt, 60)
                params["backoff_seconds"] = backoff_seconds
                message = f"Nouvelle tentative après {backoff_seconds}s (backoff exponentiel)"

            if action == RecoveryAction.RETRY:
                params["retry_count"] = attempt

        # Enrichir avec le contexte fourni
        if context:
            params["context"] = context

        return RecoveryDecision(
            action=action,
            params=params,
            message=message,
        )
