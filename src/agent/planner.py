"""
NURU V9 — TaskPlanner : décomposition d'objectifs en plans d'étapes ordonnés.

Pour V9 MVP, la décomposition est basée sur des règles de mots-clés
(pas d'appel LLM). Le planneur construit des workflows types :
  search → analyze → generate → verify

Utilise AGENT_LIMITS["max_steps"] = 5 comme contrainte.
"""

from __future__ import annotations

import time
from typing import Optional

from src.agent.types import (
    AGENT_LIMITS,
    TaskPlan,
    TaskStep,
    ToolCall,
)


class TaskPlanner:
    """
    Décompose un objectif utilisateur en un plan de tâches ordonné.

    Utilise les contraintes AGENT_LIMITS (max_steps=5).
    Identifie les dépendances entre les étapes.

    Pour V9 MVP, la décomposition est basée sur des règles (pas de LLM) :
      - Cherche des mots-clés dans le goal
      - Construit des étapes types : search → analyze → generate → verify
    """

    def __init__(self, memory_manager=None):
        self.memory = memory_manager  # optionnel, pour chercher des workflows

    # ── Interface publique ──────────────────────────────────────────────

    def plan(self, goal: str) -> TaskPlan:
        """Analyse le goal et produit un plan ordonné."""
        goal_lower = goal.lower().strip()
        max_steps = AGENT_LIMITS.get("max_steps", 5)

        if _contains_any(goal_lower, ["analyse", "analyser", "analyze"]):
            steps = self._build_analyse_workflow(goal)
        elif _contains_any(goal_lower, ["rapport", "report", "document"]):
            steps = self._build_report_workflow(goal)
        elif _contains_any(goal_lower, ["ppt", "powerpoint", "présentation", "presentation", "slides", "slide"]):
            steps = self._build_ppt_workflow(goal)
        else:
            steps = self._build_default_workflow(goal)

        # Tronquer si on dépasse la limite
        steps = steps[:max_steps]

        return TaskPlan(
            goal=goal,
            steps=steps,
            created_at=time.time(),
        )

    def format_plan(self, plan: TaskPlan) -> str:
        """Retourne une représentation lisible du plan."""
        lines = [f"📋 Plan pour : {plan.goal}"]
        for i, step in enumerate(plan.steps):
            deps = f" (après : {', '.join(step.depends_on)})" if step.depends_on else ""
            tools = ", ".join(t.tool_name for t in step.tool_calls)
            lines.append(f"  {i + 1}. {step.description} [{tools}]{deps}")
        return "\n".join(lines)

    # ── Workflows internes ──────────────────────────────────────────────

    def _build_analyse_workflow(self, goal: str) -> list[TaskStep]:
        """Workflow type pour une tâche d'analyse."""
        return [
            TaskStep(
                description="Rechercher et collecter les données pertinentes",
                tool_calls=[ToolCall(tool_name="search_rag", parameters={"query": goal})],
                depends_on=[],
                expected_output="Données collectées pour l'analyse",
            ),
            TaskStep(
                description="Analyser et résumer les informations",
                tool_calls=[ToolCall(tool_name="analyze", parameters={"goal": goal})],
                depends_on=["step_1"],
                expected_output="Analyse détaillée des données",
            ),
            TaskStep(
                description="Générer le rapport d'analyse final",
                tool_calls=[ToolCall(tool_name="generate_report", parameters={"goal": goal})],
                depends_on=["step_2"],
                expected_output="Rapport d'analyse complet",
            ),
        ]

    def _build_report_workflow(self, goal: str) -> list[TaskStep]:
        """Workflow type pour une tâche de création de rapport/document."""
        return [
            TaskStep(
                description="Rechercher les informations nécessaires",
                tool_calls=[ToolCall(tool_name="search_rag", parameters={"query": goal})],
                depends_on=[],
                expected_output="Informations collectées pour le rapport",
            ),
            TaskStep(
                description="Rédiger le rapport ou document",
                tool_calls=[ToolCall(tool_name="generate_report", parameters={"goal": goal})],
                depends_on=["step_1"],
                expected_output="Brouillon du rapport",
            ),
            TaskStep(
                description="Vérifier et valider le contenu produit",
                tool_calls=[ToolCall(tool_name="verify", parameters={"goal": goal})],
                depends_on=["step_2"],
                expected_output="Rapport vérifié et validé",
            ),
        ]

    def _build_ppt_workflow(self, goal: str) -> list[TaskStep]:
        """Workflow type pour une tâche de création de présentation."""
        return [
            TaskStep(
                description="Collecter le contenu pour la présentation",
                tool_calls=[ToolCall(tool_name="search_rag", parameters={"query": goal})],
                depends_on=[],
                expected_output="Contenu collecté pour les slides",
            ),
            TaskStep(
                description="Créer les slides de la présentation",
                tool_calls=[ToolCall(tool_name="create_slides", parameters={"goal": goal})],
                depends_on=["step_1"],
                expected_output="Présentation créée",
            ),
        ]

    def _build_default_workflow(self, goal: str) -> list[TaskStep]:
        """Workflow par défaut : comprendre → générer → vérifier."""
        return [
            TaskStep(
                description="Comprendre le contexte et rechercher des informations",
                tool_calls=[ToolCall(tool_name="search_rag", parameters={"query": goal})],
                depends_on=[],
                expected_output="Contexte compris et informations collectées",
            ),
            TaskStep(
                description="Générer une réponse adaptée",
                tool_calls=[ToolCall(tool_name="summarize", parameters={"goal": goal})],
                depends_on=["step_1"],
                expected_output="Réponse générée",
            ),
            TaskStep(
                description="Vérifier la qualité de la réponse",
                tool_calls=[ToolCall(tool_name="verify", parameters={"goal": goal})],
                depends_on=["step_2"],
                expected_output="Réponse vérifiée",
            ),
        ]


# ── Helpers ─────────────────────────────────────────────────────────

def _contains_any(text: str, keywords: list[str]) -> bool:
    """Vérifie si le texte contient au moins un des mots-clés."""
    return any(kw in text for kw in keywords)
