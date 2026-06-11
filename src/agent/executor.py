"""
NURU V9 — TaskExecutor : exécution d'étapes de tâche avec appels d'outils.

Pour V9 MVP, les outils sont simulés (mockés dans les tests).
L'intégration réelle avec ToolRegistry viendra au Sprint 6 (Outils).
Le catalogue MOCK_TOOLS fournit des réponses factices pour chaque outil
connu, et l'exécuteur peut accepter des outils personnalisés injectés.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Optional

from src.agent.types import StepResult, TaskStatus, TaskStep, ToolCall


class TaskExecutor:
    """
    Exécute une étape de tâche en appelant les outils appropriés.

    Pour V9 MVP, les outils sont simulés via MOCK_TOOLS.
    L'intégration réelle avec ToolRegistry viendra au Sprint 6.
    """

    # Catalogue d'outils simulés pour V9 MVP
    MOCK_TOOLS: dict[str, dict[str, str]] = {
        "search_rag": {
            "description": "Recherche documents",
            "mock_response": "Résultats de recherche simulés",
        },
        "read_file": {
            "description": "Lecture fichier",
            "mock_response": "Contenu du fichier simulé",
        },
        "analyze": {
            "description": "Analyse LLM",
            "mock_response": "Analyse simulée",
        },
        "generate_report": {
            "description": "Génération rapport",
            "mock_response": "Rapport généré simulé",
        },
        "create_slides": {
            "description": "Création slides",
            "mock_response": "Slides créées simulées",
        },
        "verify": {
            "description": "Vérification",
            "mock_response": "Vérification OK simulée",
        },
        "summarize": {
            "description": "Résumé LLM",
            "mock_response": "Résumé simulé",
        },
    }

    def __init__(self, tools: Optional[dict[str, Callable]] = None):
        """
        Initialise l'exécuteur.

        Args:
            tools: Dictionnaire optionnel {tool_name: callable} pour injecter
                   de vrais outils. Les callables doivent être async.
        """
        self._custom_tools: dict[str, Callable] = tools or {}

    # ── Interface publique ──────────────────────────────────────────────

    async def execute(self, step: TaskStep) -> StepResult:
        """
        Exécute une étape et retourne le résultat structuré.

        - Itère sur les tool_calls du step
        - Pour chaque outil : l'exécute (mock ou custom)
        - Agrège les résultats
        - Gère le timeout
        - Calcule la durée

        Args:
            step: L'étape à exécuter (TaskStep avec tool_calls)

        Returns:
            StepResult contenant le statut, la sortie, et les métriques
        """
        step_id = step.step_id
        tool_results: list[dict[str, Any]] = []
        overall_output: list[str] = []
        error_message: Optional[str] = None
        status = TaskStatus.COMPLETED

        start_time = time.monotonic()

        for tc in step.tool_calls:
            result = await self._execute_single_tool(tc)
            tool_results.append(result)

            if result.get("status") == "error":
                error_message = result.get("output", "Erreur inconnue")
                status = TaskStatus.FAILED
                break
            else:
                output_text = result.get("output", "")
                if output_text:
                    overall_output.append(str(output_text))

        elapsed = time.monotonic() - start_time

        return StepResult(
            step_id=step_id,
            status=status,
            output="\n".join(overall_output) if overall_output else None,
            error=error_message,
            duration_s=round(elapsed, 3),
            tool_results=tool_results,
        )

    # ── Exécution d'un outil ────────────────────────────────────────────

    async def _execute_single_tool(
        self,
        tc: ToolCall,
    ) -> dict[str, Any]:
        """
        Exécute un appel d'outil unique (custom ou mock).

        Gère le timeout via asyncio.wait_for.
        """
        tool_name = tc.tool_name

        # 1. Outil personnalisé injecté
        if tool_name in self._custom_tools:
            try:
                fn = self._custom_tools[tool_name]
                output = await asyncio.wait_for(
                    fn(**tc.parameters),
                    timeout=tc.timeout_s,
                )
                return {
                    "tool": tool_name,
                    "status": "success",
                    "output": str(output),
                }
            except asyncio.TimeoutError:
                return {
                    "tool": tool_name,
                    "status": "error",
                    "output": f"Timeout après {tc.timeout_s}s",
                }
            except Exception as exc:
                return {
                    "tool": tool_name,
                    "status": "error",
                    "output": f"Exception : {exc}",
                }

        # 2. Outil simulé (mock)
        mock_info = self.MOCK_TOOLS.get(tool_name)
        if mock_info is not None:
            return {
                "tool": tool_name,
                "status": "success",
                "output": mock_info["mock_response"],
            }

        # 3. Outil inconnu
        return {
            "tool": tool_name,
            "status": "error",
            "output": f"Outil inconnu : '{tool_name}'",
        }

    # ── Helpers ─────────────────────────────────────────────────────────

    def _get_mock_response(self, tool_name: str) -> str:
        """
        Retourne une réponse simulée pour un outil non implémenté.

        Sera utilisée dans les phases ultérieures pour un fallback
        explicite. Pour MVP, l'exécution passe par _execute_single_tool.
        """
        mock_info = self.MOCK_TOOLS.get(tool_name)
        if mock_info:
            return mock_info["mock_response"]
        return f"Réponse simulée pour '{tool_name}' (outil inconnu)"
