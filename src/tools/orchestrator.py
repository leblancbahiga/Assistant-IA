"""Orchestrateur central des outils NURU — ToolOrchestrator singleton.

Centralise le registre des 4 modules outils (shell, os, browser, file)
et expose les schémas JSON pour le LLM via plusieurs formats.

Intégration MCP (Model Context Protocol) :
  - get_tools_json()        → schéma JSON brut pour LLM
  - get_tools_json_schema() → OpenAI-compatible function calling
  - execute_tool()          → routage unifié
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

from src.tools.registry import ToolExecutor, ToolRegistry, ToolResult

# ── Import des 4 modules d'outils ────────────────────────────────

from src.tools.shell_exec import register_shell_tools
from src.tools.os_control import register_os_tools
from src.tools.browser_ctrl import register_browser_tools
from src.tools.file_ops import register_file_tools
from src.tools.memory_tools import register_memory_tools
from src.tools.agent_tools import register_agent_tools

logger = logging.getLogger(__name__)


# ── ToolOrchestrator ─────────────────────────────────────────────


class ToolOrchestrator:
    """Orchestrateur central de tous les outils NURU.

    Singleton thread-safe. Gère le registre central, l'exécuteur,
    et l'export de schémas JSON pour le LLM et les clients MCP.

    Utilisation::

        orch = ToolOrchestrator.get_instance()
        orch.setup()
        result = orch.execute("shell_exec", {"command": "ls -la"})
        schema = orch.get_tools_json()
    """

    _instance: ToolOrchestrator | None = None
    _singleton_lock: threading.Lock = threading.Lock()
    _initialized: bool = False

    def __new__(cls, *args: Any, **kwargs: Any) -> ToolOrchestrator:
        """Crée ou retourne l'instance unique (thread-safe)."""
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def __init__(self) -> None:
        """Initialisation unique du singleton."""
        if self._initialized:
            return
        self._registry: ToolRegistry = ToolRegistry()
        self._executor: ToolExecutor = ToolExecutor(self._registry)
        self._setup_done: bool = False
        self._initialized = True
        logger.debug("ToolOrchestrator initialisé (non configuré)")

    # ── Singleton helper ─────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> ToolOrchestrator:
        """Retourne l'instance unique du ToolOrchestrator.

        Returns:
            L'instance unique de ToolOrchestrator.
        """
        return cls()

    # ── Setup ────────────────────────────────────────────────────

    def setup(self) -> None:
        """Initialise le registre et enregistre les 4 modules d'outils.

        Appelle séquentiellement :
        - register_shell_tools()   → 2 outils category='system'
        - register_os_tools()      → 8 outils category='system'
        - register_browser_tools() → 9 outils category='web'
        - register_file_tools()    → 12 outils category='system'

        L'appel est idempotent : une seconde exécution ne fait rien.
        """
        if self._setup_done:
            logger.debug("ToolOrchestrator déjà configuré, ignoré")
            return

        register_shell_tools(self._registry, self._executor)
        register_os_tools(self._registry, self._executor)
        register_browser_tools(self._registry, self._executor)
        register_file_tools(self._registry, self._executor)
        register_memory_tools(self._registry, self._executor)
        register_agent_tools(self._registry, self._executor)

        self._setup_done = True
        logger.info(
            "ToolOrchestrator configuré: %d outils, %d catégories",
            len(self._registry),
            len(self.list_categories()),
        )

    # ── Accesseurs ───────────────────────────────────────────────

    def get_registry(self) -> ToolRegistry:
        """Retourne le registre central des outils.

        Returns:
            ToolRegistry contenant tous les outils enregistrés.
        """
        return self._registry

    def get_executor(self) -> ToolExecutor:
        """Retourne l'exécuteur central des outils.

        Returns:
            ToolExecutor contenant tous les handlers enregistrés.
        """
        return self._executor

    def is_setup(self) -> bool:
        """Vérifie si l'orchestrateur a été configuré.

        Returns:
            True si setup() a déjà été appelé.
        """
        return self._setup_done

    # ── Exécution ────────────────────────────────────────────────

    def execute(self, tool_name: str, params: dict[str, Any] | None = None) -> ToolResult:
        """Exécute un outil par son nom avec les paramètres donnés.

        Args:
            tool_name: Nom de l'outil à exécuter.
            params: Dictionnaire de paramètres (peut être None).

        Returns:
            ToolResult contenant le résultat ou l'erreur.

        Exemples:
            >>> orch.execute("shell_exec", {"command": "echo hello"})
            ToolResult(tool_name='shell_exec', success=True, output=...)
            >>> orch.execute("outil_inexistant")
            ToolResult(tool_name='outil_inexistant', success=False, error=...)
        """
        if params is None:
            params = {}
        return self._executor.execute(tool_name, params)

    # ── Export JSON pour LLM ─────────────────────────────────────

    def get_tools_json(self) -> list[dict]:
        """Retourne la liste complète des schémas d'outils pour le LLM.

        Chaque outil est représenté par :
        - ``name`` : nom unique de l'outil
        - ``description`` : description en langage naturel
        - ``parameters`` : schéma JSON des paramètres (type object)

        Returns:
            Liste de dictionnaires représentant les outils.

        Exemple:
            >>> schema = orhelloch.get_tools_json()
            >>> schema[0]["name"]
            'shell_exec'
        """
        return self._registry.to_llm_schema()

    def get_tools_json_schema(self) -> list[dict]:
        """Retourne les schémas au format OpenAI function calling.

        Chaque outil est formaté selon la spécification OpenAI :
        ``{ "type": "function", "function": { "name", "description",
        "parameters" } }``

        Returns:
            Liste de dictionnaires compatibles OpenAI API.
        """
        raw = self._registry.to_llm_schema()
        return [
            {
                "type": "function",
                "function": {
                    "name": item["name"],
                    "description": item["description"],
                    "parameters": item["parameters"],
                },
            }
            for item in raw
        ]

    def get_tools_json_string(self, indent: int = 2) -> str:
        """Retourne la liste des schémas d'outils comme chaîne JSON.

        Args:
            indent: Nombre d'espaces pour l'indentation (défaut: 2).

        Returns:
            JSON string représentant tous les outils.
        """
        return json.dumps(self.get_tools_json(), indent=indent, ensure_ascii=False)

    # ── Catégories ───────────────────────────────────────────────

    def get_tools_by_category(self, category: str) -> list[dict]:
        """Retourne les outils d'une catégorie donnée.

        Args:
            category: Nom de la catégorie ('system', 'web').

        Returns:
            Liste des schémas d'outils de cette catégorie.

        Exemple:
            >>> web_tools = orch.get_tools_by_category("web")
            >>> len(web_tools)
            9
        """
        tools = self._registry.list_by_category(category)
        return [t.to_schema() for t in tools]

    def list_categories(self) -> dict[str, int]:
        """Liste toutes les catégories avec le nombre d'outils.

        Returns:
            Dictionnaire {nom_catégorie: nombre_outils}.

        Exemple:
            >>> orch.list_categories()
            {'system': 22, 'web': 9}
        """
        counts: dict[str, int] = {}
        for t in self._registry.list_tools():
            counts[t.category] = counts.get(t.category, 0) + 1
        return counts

    # ── Réinitialisation (pour tests) ────────────────────────────

    def reset(self) -> None:
        """Réinitialise l'orchestrateur pour les tests.

        Vide le registre, l'exécuteur, et remet le flag setup à False.
        """
        self._registry = ToolRegistry()
        self._executor = ToolExecutor(self._registry)
        self._setup_done = False
        logger.debug("ToolOrchestrator réinitialisé")

    @classmethod
    def _reset_singleton(cls) -> None:
        """Rétablit l'état vierge du singleton (usage tests uniquement)."""
        with cls._singleton_lock:
            cls._instance = None
