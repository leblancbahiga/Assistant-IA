"""
NURU V12 — Outils agent pour le ToolRegistry.

Expose les capacités de l'AgentOrchestrator via le registre d'outils NURU
pour que le LLM puisse déléguer des requêtes complexes à la boucle agentique.

Outils exposés :
  - agent_query(query, mode="auto")  → AgentOrchestrator.run(query)
  - agent_plan(goal)                 → AgentOrchestrator.plan(goal)
  - agent_verify(result)             → AgentOrchestrator.verify_result(result)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from src.tools.registry import ToolDefinition, ToolParameter, ToolRegistry, ToolExecutor, ToolResult

logger = logging.getLogger(__name__)

__all__ = ["register_agent_tools"]


def _get_agent_orchestrator():
    """Retourne une instance de l'AgentOrchestrator (singleton).

    Initialisation paresseuse.
    """
    try:
        from src.tools.agent_orchestrator import AgentOrchestrator
        return AgentOrchestrator.get_instance()
    except Exception as e:
        logger.warning("⚠️ AgentOrchestrator non disponible: %s", e)
        return None


# ── Handlers ─────────────────────────────────────────────────────────


def _handle_agent_query(**kwargs) -> ToolResult:
    """Exécute une requête via la boucle agentique complète.

    Plan→Execute→Verify→Synthesize avec RAG + mémoire.
    """
    params = kwargs
    query = params.get("query", "")
    mode = params.get("mode", "auto")

    if not query:
        return ToolResult(
            tool_name="agent_query", success=False, output=None,
            error="Paramètre 'query' requis",
        )

    orch = _get_agent_orchestrator()
    if orch is None:
        return ToolResult(
            tool_name="agent_query", success=False, output=None,
            error="AgentOrchestrator non disponible",
        )

    try:
        # Exécution synchrone dans un event loop existant ou nouveau
        try:
            loop = asyncio.get_running_loop()
            # Si déjà dans une boucle, créer une nouvelle tâche
            result = asyncio.run_coroutine_threadsafe(orch.run(query), loop).result(timeout=60)
        except RuntimeError:
            # Pas de boucle en cours → créer une
            result = asyncio.run(orch.run(query))

        return ToolResult(
            tool_name="agent_query", success=True,
            output=json.dumps(result, indent=2, ensure_ascii=False, default=str),
        )
    except Exception as e:
        return ToolResult(
            tool_name="agent_query", success=False, output=None,
            error=f"Erreur agent_query: {e}",
        )


def _handle_agent_plan(**kwargs) -> ToolResult:
    """Décompose un objectif en étapes via l'AgentOrchestrator.

    Retourne une liste d'étapes pour réaliser l'objectif.
    """
    params = kwargs
    goal = params.get("goal", "")

    if not goal:
        return ToolResult(
            tool_name="agent_plan", success=False, output=None,
            error="Paramètre 'goal' requis",
        )

    orch = _get_agent_orchestrator()
    if orch is None:
        return ToolResult(
            tool_name="agent_plan", success=False, output=None,
            error="AgentOrchestrator non disponible",
        )

    try:
        try:
            loop = asyncio.get_running_loop()
            steps = asyncio.run_coroutine_threadsafe(orch.plan(goal), loop).result(timeout=30)
        except RuntimeError:
            steps = asyncio.run(orch.plan(goal))

        return ToolResult(
            tool_name="agent_plan", success=True,
            output=json.dumps({"goal": goal, "steps": steps}, indent=2, ensure_ascii=False),
        )
    except Exception as e:
        return ToolResult(
            tool_name="agent_plan", success=False, output=None,
            error=f"Erreur agent_plan: {e}",
        )


def _handle_agent_verify(**kwargs) -> ToolResult:
    """Vérifie la qualité d'un résultat.

    Évalue la confiance, la présence de sources, et la cohérence.
    """
    params = kwargs
    result_raw = params.get("result", "")

    if not result_raw:
        return ToolResult(
            tool_name="agent_verify", success=False, output=None,
            error="Paramètre 'result' requis",
        )

    # Tenter de parser le JSON si c'est une chaîne
    if isinstance(result_raw, str):
        try:
            result_data = json.loads(result_raw)
        except (json.JSONDecodeError, TypeError):
            result_data = {"query": "", "rag_context": result_raw, "memory_context": ""}
    elif isinstance(result_raw, dict):
        result_data = result_raw
    else:
        result_data = {"query": str(result_raw), "rag_context": str(result_raw), "memory_context": ""}

    orch = _get_agent_orchestrator()
    if orch is None:
        return ToolResult(
            tool_name="agent_verify", success=False, output=None,
            error="AgentOrchestrator non disponible",
        )

    try:
        try:
            loop = asyncio.get_running_loop()
            verify_result = asyncio.run_coroutine_threadsafe(orch.verify_result(result_data), loop).result(timeout=30)
        except RuntimeError:
            verify_result = asyncio.run(orch.verify_result(result_data))

        return ToolResult(
            tool_name="agent_verify", success=True,
            output=json.dumps(verify_result, indent=2, ensure_ascii=False),
        )
    except Exception as e:
        return ToolResult(
            tool_name="agent_verify", success=False, output=None,
            error=f"Erreur agent_verify: {e}",
        )


# ── Définition des outils ────────────────────────────────────────────

AGENT_TOOLS = [
    ToolDefinition(
        name="agent_query",
        description="Exécute une requête via la boucle agentique complète (Plan→Execute→Verify→Synthesize). "
                    "Intègre RAG (recherche documentaire) + mémoire utilisateur pour produire "
                    "une réponse structurée avec traçabilité.",
        category="agent",
        parameters=[
            ToolParameter(name="query", type="str", description="Requête utilisateur à traiter"),
            ToolParameter(name="mode", type="str", description="Mode d'exécution: 'auto' (défaut), 'rag_only', 'memory_only'",
                          required=False, default="auto"),
        ],
    ),
    ToolDefinition(
        name="agent_plan",
        description="Décompose un objectif complexe en étapes simples et ordonnées. "
                    "Utilise l'AgentOrchestrator pour analyser l'intention et produire "
                    "une séquence d'actions logiques.",
        category="agent",
        parameters=[
            ToolParameter(name="goal", type="str", description="Objectif à décomposer en étapes"),
        ],
    ),
    ToolDefinition(
        name="agent_verify",
        description="Vérifie la qualité d'un résultat produit par l'agent. "
                    "Évalue la confiance, la présence de sources documentaires, "
                    "le contexte mémoire, et la cohérence globale.",
        category="agent",
        parameters=[
            ToolParameter(name="result", type="str", description="Résultat à vérifier (texte ou JSON)"),
        ],
    ),
]


def register_agent_tools(registry: ToolRegistry, executor: ToolExecutor) -> None:
    """Enregistre tous les outils agent dans le registre et l'exécuteur.

    Args:
        registry: ToolRegistry où enregistrer les définitions.
        executor: ToolExecutor où enregistrer les handlers.
    """
    for tool_def in AGENT_TOOLS:
        registry.register(tool_def)

    executor.register_handler("agent_query", _handle_agent_query)
    executor.register_handler("agent_plan", _handle_agent_plan)
    executor.register_handler("agent_verify", _handle_agent_verify)

    logger.info("🤖 %d outils agent enregistrés", len(AGENT_TOOLS))
