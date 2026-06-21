"""Outils mémoire V9 pour ToolOrchestrator.

Expose les capacités du MemoryManager via le registre d'outils NURU
pour que le LLM puisse consulter et enrichir la mémoire.

Outils exposés :
  - memory_recall(query)       → MemoryRetriever.recall_combined
  - memory_store_episode(...)  → EpisodicMemory.add
  - memory_user_profile()      → UserMemory.get_all
  - memory_stats()             → MemoryManager.get_memory_stats
  - memory_error_check(query)  → ErrorMemory.check_similar
  - memory_store_fact(...)     → SemanticMemory.add
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.tools.registry import ToolDefinition, ToolParameter, ToolRegistry, ToolExecutor, ToolResult

logger = logging.getLogger(__name__)

__all__ = ["register_memory_tools"]


def _get_memory_manager():
    """Retourne une instance du MemoryManager (singleton de session).

    Initialisation paresseuse pour ne pas créer de DB avant le premier besoin.
    """
    try:
        from src.memory.manager import MemoryManager
        return MemoryManager()
    except Exception as e:
        logger.warning("⚠️ MemoryManager non disponible: %s", e)
        return None


# ── Handlers ─────────────────────────────────────────────────────────
#
# Tous les handlers acceptent **kwargs car ToolExecutor.execute()
# appelle handler(**params). Les handlers sans paramètres reçoivent
# un dict vide, les handlers avec paramètres extraient leurs valeurs
# depuis kwargs.


def _handle_memory_recall(**kwargs) -> ToolResult:
    """Recherche combinée dans toutes les mémoires."""
    params = kwargs
    query = params.get("query", "")
    top_k = params.get("top_k", 5)
    if not query:
        return ToolResult(
            tool_name="memory_recall", success=False, output=None,
            error="Paramètre 'query' requis",
        )
    mgr = _get_memory_manager()
    if mgr is None:
        return ToolResult(
            tool_name="memory_recall", success=False, output=None,
            error="MemoryManager non disponible",
        )
    try:
        results = mgr.retriever.recall_combined(query=query, top_k=top_k)
        return ToolResult(
            tool_name="memory_recall", success=True,
            output=json.dumps(results, indent=2, ensure_ascii=False, default=str),
        )
    except Exception as e:
        return ToolResult(
            tool_name="memory_recall", success=False, output=None,
            error=f"Erreur recall: {e}",
        )


def _handle_memory_store_episode(**kwargs) -> ToolResult:
    """Enregistre un épisode dans la mémoire épisodique."""
    params = kwargs
    summary = params.get("summary", "")
    event_type = params.get("event_type", "conversation")
    importance = params.get("importance", 0.5)
    context = params.get("context", {})

    if not summary:
        return ToolResult(
            tool_name="memory_store_episode", success=False, output=None,
            error="Paramètre 'summary' requis",
        )
    mgr = _get_memory_manager()
    if mgr is None:
        return ToolResult(
            tool_name="memory_store_episode", success=False, output=None,
            error="MemoryManager non disponible",
        )
    try:
        episode_id = mgr.episodic.add(
            event_type=event_type,
            summary=summary,
            context=context,
            importance=importance,
        )
        return ToolResult(
            tool_name="memory_store_episode", success=True,
            output=json.dumps({"episode_id": episode_id}, ensure_ascii=False),
        )
    except Exception as e:
        return ToolResult(
            tool_name="memory_store_episode", success=False, output=None,
            error=f"Erreur ajout épisode: {e}",
        )


def _handle_memory_user_profile(**kwargs) -> ToolResult:
    """Retourne le profil utilisateur complet."""
    mgr = _get_memory_manager()
    if mgr is None:
        return ToolResult(
            tool_name="memory_user_profile", success=False, output=None,
            error="MemoryManager non disponible",
        )
    try:
        profile = mgr.get_user_profile()
        return ToolResult(
            tool_name="memory_user_profile", success=True,
            output=profile or "Aucune information utilisateur enregistrée.",
        )
    except Exception as e:
        return ToolResult(
            tool_name="memory_user_profile", success=False, output=None,
            error=f"Erreur profil: {e}",
        )


def _handle_memory_stats(**kwargs) -> ToolResult:
    """Retourne les statistiques de la mémoire (nombre d'entrées par type)."""
    mgr = _get_memory_manager()
    if mgr is None:
        return ToolResult(
            tool_name="memory_stats", success=False, output=None,
            error="MemoryManager non disponible",
        )
    try:
        stats = mgr.get_memory_stats()
        stats["working_memory"] = mgr.get_working_memory_size()
        stats["message_history"] = mgr.get_message_history_size()
        return ToolResult(
            tool_name="memory_stats", success=True,
            output=json.dumps(stats, indent=2, ensure_ascii=False),
        )
    except Exception as e:
        return ToolResult(
            tool_name="memory_stats", success=False, output=None,
            error=f"Erreur stats: {e}",
        )


def _handle_memory_error_check(**kwargs) -> ToolResult:
    """Vérifie si une erreur similaire existe déjà dans ErrorMemory."""
    params = kwargs
    query = params.get("query", "")
    threshold = params.get("threshold", 0.75)

    if not query:
        return ToolResult(
            tool_name="memory_error_check", success=False, output=None,
            error="Paramètre 'query' requis",
        )
    mgr = _get_memory_manager()
    if mgr is None:
        return ToolResult(
            tool_name="memory_error_check", success=False, output=None,
            error="MemoryManager non disponible",
        )
    try:
        results = mgr.check_errors(query)
        return ToolResult(
            tool_name="memory_error_check", success=True,
            output=json.dumps(results, indent=2, ensure_ascii=False, default=str),
        )
    except Exception as e:
        return ToolResult(
            tool_name="memory_error_check", success=False, output=None,
            error=f"Erreur check_errors: {e}",
        )


def _handle_memory_store_fact(**kwargs) -> ToolResult:
    """Enregistre un fait consolidé dans SemanticMemory."""
    params = kwargs
    fact = params.get("fact", "")
    category = params.get("category", "general")
    confidence = params.get("confidence", 0.8)

    if not fact:
        return ToolResult(
            tool_name="memory_store_fact", success=False, output=None,
            error="Paramètre 'fact' requis",
        )
    mgr = _get_memory_manager()
    if mgr is None:
        return ToolResult(
            tool_name="memory_store_fact", success=False, output=None,
            error="MemoryManager non disponible",
        )
    try:
        fact_id = mgr.semantic.add(
            fact=fact,
            category=category,
            confidence=confidence,
        )
        return ToolResult(
            tool_name="memory_store_fact", success=True,
            output=json.dumps({"fact_id": fact_id}, ensure_ascii=False),
        )
    except Exception as e:
        return ToolResult(
            tool_name="memory_store_fact", success=False, output=None,
            error=f"Erreur ajout fait: {e}",
        )


# ── Définition des outils ────────────────────────────────────────────

MEMORY_TOOLS = [
    ToolDefinition(
        name="memory_recall",
        description="Recherche combinée dans toutes les mémoires (épisodique, sémantique, utilisateur, erreurs). "
                    "Retourne les souvenirs pertinents pour une requête donnée, triés par score.",
        category="memory",
        parameters=[
            ToolParameter(name="query", type="str", description="Texte de recherche"),
            ToolParameter(name="top_k", type="int", description="Nombre max de résultats (défaut: 5)", required=False, default=5),
        ],
    ),
    ToolDefinition(
        name="memory_store_episode",
        description="Enregistre un nouvel épisode dans la mémoire épisodique. "
                    "Utilisé pour mémoriser des conversations, actions ou événements importants.",
        category="memory",
        parameters=[
            ToolParameter(name="summary", type="str", description="Résumé de l'épisode"),
            ToolParameter(name="event_type", type="str", description="Type d'événement (conversation, action, tool_use)", required=False, default="conversation"),
            ToolParameter(name="importance", type="float", description="Importance (0-1, défaut: 0.5)", required=False, default=0.5),
            ToolParameter(name="context", type="str", description="Contexte JSON (optionnel)", required=False, default=""),
        ],
    ),
    ToolDefinition(
        name="memory_user_profile",
        description="Retourne le profil complet de l'utilisateur (nom, préférences, identité).",
        category="memory",
        parameters=[],
    ),
    ToolDefinition(
        name="memory_stats",
        description="Retourne les statistiques de la mémoire : nombre d'entrées par type "
                    "(épisodique, sémantique, utilisateur, erreurs) + taille mémoire de travail.",
        category="memory",
        parameters=[],
    ),
    ToolDefinition(
        name="memory_error_check",
        description="Vérifie si une erreur similaire existe déjà dans la mémoire des erreurs. "
                    "Utile avant d'ajouter une nouvelle erreur ou pour éviter de répéter des erreurs passées.",
        category="memory",
        parameters=[
            ToolParameter(name="query", type="str", description="Description de l'erreur à vérifier"),
            ToolParameter(name="threshold", type="float", description="Seuil de similarité (0-1, défaut: 0.75)", required=False, default=0.75),
        ],
    ),
    ToolDefinition(
        name="memory_store_fact",
        description="Enregistre un fait consolidé dans la mémoire sémantique. "
                    "Utilisé pour mémoriser des informations factuelles à long terme.",
        category="memory",
        parameters=[
            ToolParameter(name="fact", type="str", description="Le fait à mémoriser"),
            ToolParameter(name="category", type="str", description="Catégorie (personal, professional, technical, general)", required=False, default="general"),
            ToolParameter(name="confidence", type="float", description="Niveau de confiance (0-1, défaut: 0.8)", required=False, default=0.8),
        ],
    ),
]


def register_memory_tools(registry: ToolRegistry, executor: ToolExecutor) -> None:
    """Enregistre tous les outils mémoire dans le registre et l'exécuteur.

    Args:
        registry: ToolRegistry où enregistrer les définitions.
        executor: ToolExecutor où enregistrer les handlers.
    """
    for tool_def in MEMORY_TOOLS:
        registry.register(tool_def)

    executor.register_handler("memory_recall", _handle_memory_recall)
    executor.register_handler("memory_store_episode", _handle_memory_store_episode)
    executor.register_handler("memory_user_profile", _handle_memory_user_profile)
    executor.register_handler("memory_stats", _handle_memory_stats)
    executor.register_handler("memory_error_check", _handle_memory_error_check)
    executor.register_handler("memory_store_fact", _handle_memory_store_fact)

    logger.info("🧠 %d outils mémoire enregistrés", len(MEMORY_TOOLS))
