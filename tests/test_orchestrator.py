"""Tests d'intégration du ToolOrchestrator — NURU V12.

Vérifie que :
- Les 4 modules sont correctement enregistrés
- Les outils, handlers, catégories sont cohérents
- Les schémas JSON/OpenAI sont valides
- L'exécution route correctement
- Le singleton fonctionne
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Generator

import pytest

# ── Ajout du path src ────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from src.tools.orchestrator import ToolOrchestrator
from src.tools.registry import ToolResult


# ── Constants ────────────────────────────────────────────────────

EXPECTED_MODULES: dict[str, int] = {
    "shell_exec": 2,  # shell_exec, shell_dry_run
    "os_control": 8,  # os_open_app, os_control_app, os_control_window,
    #   os_system_control, os_applescript, os_discover_apps,
    #   os_screenshot, os_type
    "browser_ctrl": 9,  # browser_navigate, browser_click, browser_type,
    #   browser_extract, browser_screenshot, browser_scroll,
    #   browser_form_fill, browser_execute_script, browser_get_info
    "file_ops": 12,  # file_read, file_write, file_append, file_delete,
    #   file_move, file_copy, file_mkdir, file_list,
    #   file_info, file_search, file_workspace_info,
    #   file_authorize_directory
    "memory_tools": 6,  # memory_recall, memory_store_episode,
    #   memory_user_profile, memory_stats, memory_check_errors,
    #   memory_full_context
}

TOTAL_EXPECTED_TOOLS = sum(EXPECTED_MODULES.values())  # 37

EXPECTED_TOOL_NAMES: list[str] = [
    # shell
    "shell_exec",
    "shell_dry_run",
    # os
    "os_open_app",
    "os_control_app",
    "os_control_window",
    "os_system_control",
    "os_applescript",
    "os_discover_apps",
    "os_screenshot",
    "os_type",
    # browser
    "browser_navigate",
    "browser_click",
    "browser_type",
    "browser_extract",
    "browser_screenshot",
    "browser_scroll",
    "browser_form_fill",
    "browser_execute_script",
    "browser_get_info",
    # file
    "file_read",
    "file_write",
    "file_append",
    "file_delete",
    "file_move",
    "file_copy",
    "file_mkdir",
    "file_list",
    "file_info",
    "file_search",
    "file_workspace_info",
    "file_authorize_directory",
    # memory
    "memory_recall",
    "memory_store_episode",
    "memory_user_profile",
    "memory_stats",
    "memory_error_check",
    "memory_store_fact",
]

SHELL_TOOLS = ["shell_exec", "shell_dry_run"]
OS_TOOLS = [
    "os_open_app",
    "os_control_app",
    "os_control_window",
    "os_system_control",
    "os_applescript",
    "os_discover_apps",
    "os_screenshot",
    "os_type",
]
BROWSER_TOOLS = [
    "browser_navigate",
    "browser_click",
    "browser_type",
    "browser_extract",
    "browser_screenshot",
    "browser_scroll",
    "browser_form_fill",
    "browser_execute_script",
    "browser_get_info",
]
FILE_TOOLS = [
    "file_read",
    "file_write",
    "file_append",
    "file_delete",
    "file_move",
    "file_copy",
    "file_mkdir",
    "file_list",
    "file_info",
    "file_search",
    "file_workspace_info",
    "file_authorize_directory",
]


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_orchestrator() -> Generator[None, None, None]:
    """Réinitialise le singleton avant chaque test et le nettoie après."""
    ToolOrchestrator._reset_singleton()
    yield
    ToolOrchestrator._reset_singleton()


@pytest.fixture
def orch() -> ToolOrchestrator:
    """Instance configurée du ToolOrchestrator."""
    instance = ToolOrchestrator.get_instance()
    instance.setup()
    return instance


@pytest.fixture
def raw_orch() -> ToolOrchestrator:
    """Instance non configurée du ToolOrchestrator."""
    return ToolOrchestrator.get_instance()


# ══════════════════════════════════════════════════════════════════
# 1. Singleton behavior
# ══════════════════════════════════════════════════════════════════


class TestSingleton:
    """Vérification du singleton."""

    def test_get_instance_returns_same_object(self) -> None:
        """get_instance() retourne toujours la même instance."""
        a = ToolOrchestrator.get_instance()
        b = ToolOrchestrator.get_instance()
        assert a is b

    def test_constructor_returns_same_object(self) -> None:
        """L'appel direct au constructeur retourne le singleton."""
        a = ToolOrchestrator()
        b = ToolOrchestrator()
        assert a is b

    def test_singleton_state_persists(self) -> None:
        """L'état setup persiste entre les appels à get_instance()."""
        a = ToolOrchestrator.get_instance()
        a.setup()
        b = ToolOrchestrator.get_instance()
        assert b.is_setup() is True

    def test_singleton_identity_after_reset(self) -> None:
        """_reset_singleton crée une nouvelle instance."""
        a = ToolOrchestrator.get_instance()
        ToolOrchestrator._reset_singleton()
        b = ToolOrchestrator.get_instance()
        assert a is not b

    def test_get_instance_not_setup_by_default(self) -> None:
        """Une instance fraîche n'est pas configurée."""
        orch = ToolOrchestrator.get_instance()
        assert orch.is_setup() is False


# ══════════════════════════════════════════════════════════════════
# 2. Setup & Registration
# ══════════════════════════════════════════════════════════════════


class TestSetup:
    """Vérification de la configuration."""

    def test_setup_total_tool_count(self, orch: ToolOrchestrator) -> None:
        """Le nombre total d'outils correspond à la somme des 4 modules."""
        assert len(orch.get_registry()) == TOTAL_EXPECTED_TOOLS

    def test_setup_is_idempotent(self, orch: ToolOrchestrator) -> None:
        """Un double appel à setup() ne change pas le registre."""
        # Premier appel fait dans la fixture
        count_before = len(orch.get_registry())
        orch.setup()  # deuxième appel
        assert len(orch.get_registry()) == count_before
        assert orch.is_setup() is True

    def test_initial_state_not_setup(self, raw_orch: ToolOrchestrator) -> None:
        """Avant setup, le registre est vide et is_setup est False."""
        assert raw_orch.is_setup() is False
        assert len(raw_orch.get_registry()) == 0

    def test_setup_flags_set(self, orch: ToolOrchestrator) -> None:
        """Après setup, is_setup() retourne True."""
        assert orch.is_setup() is True

    def test_setup_returns_none(self, orch: ToolOrchestrator) -> None:
        """setup() ne retourne rien (None)."""
        # La fixture a déjà appelé setup(), mais on vérifie que
        # le retour du deuxième appel est bien None
        assert orch.setup() is None

    def test_registry_has_all_tool_names(self, orch: ToolOrchestrator) -> None:
        """Tous les noms d'outils attendus sont dans le registre."""
        registered_names = {t.name for t in orch.get_registry().list_tools()}
        expected_names = set(EXPECTED_TOOL_NAMES)
        missing = expected_names - registered_names
        assert not missing, f"Outils manquants: {missing}"
        extra = registered_names - expected_names
        assert not extra, f"Outils inattendus: {extra}"

    def test_each_tool_has_category(self, orch: ToolOrchestrator) -> None:
        """Chaque outil enregistré a une catégorie non vide."""
        for tool in orch.get_registry().list_tools():
            assert tool.category, f"L'outil {tool.name} n'a pas de catégorie"

    def test_each_tool_has_description(self, orch: ToolOrchestrator) -> None:
        """Chaque outil enregistré a une description non vide."""
        for tool in orch.get_registry().list_tools():
            assert tool.description, f"L'outil {tool.name} n'a pas de description"

    def test_each_tool_has_parameters_list(self, orch: ToolOrchestrator) -> None:
        """Chaque outil a une liste de paramètres (même vide)."""
        for tool in orch.get_registry().list_tools():
            assert isinstance(tool.parameters, list)


# ══════════════════════════════════════════════════════════════════
# 3. Module registration — tool counts
# ══════════════════════════════════════════════════════════════════


class TestModuleCounts:
    """Vérification des counts par module."""

    def _get_tool_names(self, orch: ToolOrchestrator) -> set[str]:
        return {t.name for t in orch.get_registry().list_tools()}

    def test_shell_tools_count(self, orch: ToolOrchestrator) -> None:
        """Les 2 outils shell sont enregistrés."""
        names = self._get_tool_names(orch)
        for tool in SHELL_TOOLS:
            assert tool in names, f"Outil shell manquant: {tool}"

    def test_os_tools_count(self, orch: ToolOrchestrator) -> None:
        """Les 8 outils OS sont enregistrés."""
        names = self._get_tool_names(orch)
        for tool in OS_TOOLS:
            assert tool in names, f"Outil OS manquant: {tool}"

    def test_browser_tools_count(self, orch: ToolOrchestrator) -> None:
        """Les 9 outils navigateur sont enregistrés."""
        names = self._get_tool_names(orch)
        for tool in BROWSER_TOOLS:
            assert tool in names, f"Outil browser manquant: {tool}"

    def test_file_tools_count(self, orch: ToolOrchestrator) -> None:
        """Les 12 outils fichier sont enregistrés."""
        names = self._get_tool_names(orch)
        for tool in FILE_TOOLS:
            assert tool in names, f"Outil fichier manquant: {tool}"


# ══════════════════════════════════════════════════════════════════
# 4. No duplicates
# ══════════════════════════════════════════════════════════════════


class TestNoDuplicates:
    """Vérification qu'il n'y a pas de doublons."""

    def test_no_duplicate_tool_names(self, orch: ToolOrchestrator) -> None:
        """Aucun nom d'outil n'est dupliqué."""
        names = [t.name for t in orch.get_registry().list_tools()]
        assert len(names) == len(set(names)), "Noms d'outils dupliqués!"

    def test_no_duplicate_tool_definitions(self, orch: ToolOrchestrator) -> None:
        """Chaque appel register crée une définition distincte."""
        # Si register est appelé deux fois avec le même nom,
        # le second écrase le premier. On vérifie que le compte
        # total est exact.
        assert len(orch.get_registry()) == TOTAL_EXPECTED_TOOLS


# ══════════════════════════════════════════════════════════════════
# 5. Handler registration
# ══════════════════════════════════════════════════════════════════


class TestHandlers:
    """Vérification des handlers."""

    def test_all_tools_have_handlers(self, orch: ToolOrchestrator) -> None:
        """Chaque outil enregistré a un handler dans l'exécuteur."""
        executor = orch.get_executor()
        for tool in orch.get_registry().list_tools():
            assert tool.name in executor._handlers, (
                f"Pas de handler pour {tool.name}"
            )

    def test_handler_count_matches_tool_count(self, orch: ToolOrchestrator) -> None:
        """Le nombre de handlers est égal au nombre d'outils."""
        executor = orch.get_executor()
        assert len(executor._handlers) == TOTAL_EXPECTED_TOOLS

    def test_shell_handlers_exist(self, orch: ToolOrchestrator) -> None:
        """Les handlers shell sont enregistrés."""
        executor = orch.get_executor()
        for name in SHELL_TOOLS:
            assert name in executor._handlers

    def test_os_handlers_exist(self, orch: ToolOrchestrator) -> None:
        """Les handlers OS sont enregistrés."""
        executor = orch.get_executor()
        for name in OS_TOOLS:
            assert name in executor._handlers

    def test_browser_handlers_exist(self, orch: ToolOrchestrator) -> None:
        """Les handlers navigateur sont enregistrés."""
        executor = orch.get_executor()
        for name in BROWSER_TOOLS:
            assert name in executor._handlers

    def test_file_handlers_exist(self, orch: ToolOrchestrator) -> None:
        """Les handlers fichier sont enregistrés."""
        executor = orch.get_executor()
        for name in FILE_TOOLS:
            assert name in executor._handlers


# ══════════════════════════════════════════════════════════════════
# 6. Category distribution
# ══════════════════════════════════════════════════════════════════


class TestCategories:
    """Vérification des catégories."""

    def test_two_categories_total(self, orch: ToolOrchestrator) -> None:
        """Il y a exactement 2 catégories : 'system' et 'web'."""
        cats = orch.list_categories()
        assert set(cats.keys()) == {"system", "web", "memory"}, (
            f"Catégories inattendues: {set(cats.keys())}"
        )

    def test_system_category_count(self, orch: ToolOrchestrator) -> None:
        """La catégorie 'system' contient 22 outils (2 shell + 8 os + 12 file)."""
        cats = orch.list_categories()
        assert cats.get("system", 0) == 22, (
            f"Attendu 22 outils system, obtenu {cats.get('system', 0)}"
        )

    def test_web_category_count(self, orch: ToolOrchestrator) -> None:
        """La catégorie 'web' contient 9 outils navigateur."""
        cats = orch.list_categories()
        assert cats.get("web", 0) == 9

    def test_get_tools_by_category_system(self, orch: ToolOrchestrator) -> None:
        """get_tools_by_category('system') retourne 22 outils."""
        tools = orch.get_tools_by_category("system")
        assert len(tools) == 22

    def test_get_tools_by_category_web(self, orch: ToolOrchestrator) -> None:
        """get_tools_by_category('web') retourne 9 outils."""
        tools = orch.get_tools_by_category("web")
        assert len(tools) == 9

    def test_get_tools_by_category_empty(self, orch: ToolOrchestrator) -> None:
        """get_tools_by_category('inexistant') retourne une liste vide."""
        tools = orch.get_tools_by_category("inexistant")
        assert tools == []

    def test_all_tools_have_system_or_web_category(self, orch: ToolOrchestrator) -> None:
        """Tous les outils sont dans une catégorie valide."""
        valid_categories = {"system", "web", "memory"}
        for tool in orch.get_registry().list_tools():
            assert tool.category in valid_categories, (
                f"Outil {tool.name} a une catégorie invalide: {tool.category}"
            )


# ══════════════════════════════════════════════════════════════════
# 7. JSON schema output
# ══════════════════════════════════════════════════════════════════


class TestJsonSchema:
    """Vérification des exportations JSON."""

    def test_get_tools_json_returns_list(self, orch: ToolOrchestrator) -> None:
        """get_tools_json() retourne une liste."""
        schema = orch.get_tools_json()
        assert isinstance(schema, list)

    def test_get_tools_json_length(self, orch: ToolOrchestrator) -> None:
        """get_tools_json() contient tous les outils."""
        schema = orch.get_tools_json()
        assert len(schema) == TOTAL_EXPECTED_TOOLS

    def test_get_tools_json_each_has_name(self, orch: ToolOrchestrator) -> None:
        """Chaque entrée du schéma a un champ 'name'. """
        for entry in orch.get_tools_json():
            assert "name" in entry, f"Entrée sans name: {entry}"

    def test_get_tools_json_each_has_description(self, orch: ToolOrchestrator) -> None:
        """Chaque entrée du schéma a un champ 'description'."""
        for entry in orch.get_tools_json():
            assert "description" in entry

    def test_get_tools_json_each_has_parameters(self, orch: ToolOrchestrator) -> None:
        """Chaque entrée du schéma a un champ 'parameters' de type object."""
        for entry in orch.get_tools_json():
            assert "parameters" in entry
            assert entry["parameters"]["type"] == "object"
            assert "properties" in entry["parameters"]

    def test_get_tools_json_names_match(self, orch: ToolOrchestrator) -> None:
        """Les noms dans get_tools_json() correspondent aux outils enregistrés."""
        schema_names = {entry["name"] for entry in orch.get_tools_json()}
        assert schema_names == set(EXPECTED_TOOL_NAMES)

    def test_get_tools_json_string_valid(self, orch: ToolOrchestrator) -> None:
        """get_tools_json_string() produit un JSON valide."""
        json_str = orch.get_tools_json_string()
        parsed = json.loads(json_str)
        assert isinstance(parsed, list)
        assert len(parsed) == TOTAL_EXPECTED_TOOLS

    def test_get_tools_json_string_indent(self, orch: ToolOrchestrator) -> None:
        """get_tools_json_string(indent=4) utilise 4 espaces."""
        json_str = orch.get_tools_json_string(indent=4)
        # La seconde ligne devrait commencer par 4 espaces
        lines = json_str.splitlines()
        assert len(lines) > 2
        # Vérifie que l'indentation est plus grande qu'avec indent=2
        compact = orch.get_tools_json_string(indent=2)
        assert len(json_str) >= len(compact)


# ══════════════════════════════════════════════════════════════════
# 8. OpenAI-compatible schema
# ══════════════════════════════════════════════════════════════════


class TestOpenAiSchema:
    """Vérification du format OpenAI function calling."""

    def test_openai_schema_returns_list(self, orch: ToolOrchestrator) -> None:
        """get_tools_json_schema() retourne une liste."""
        schema = orch.get_tools_json_schema()
        assert isinstance(schema, list)

    def test_openai_schema_length(self, orch: ToolOrchestrator) -> None:
        """get_tools_json_schema() contient tous les outils."""
        assert len(orch.get_tools_json_schema()) == TOTAL_EXPECTED_TOOLS

    def test_openai_schema_each_has_type_function(self, orch: ToolOrchestrator) -> None:
        """Chaque entrée a 'type': 'function'."""
        for entry in orch.get_tools_json_schema():
            assert entry.get("type") == "function", (
                f"Type manquant dans: {entry}"
            )

    def test_openai_schema_each_has_function_key(self, orch: ToolOrchestrator) -> None:
        """Chaque entrée a une clé 'function' avec name, description, parameters."""
        for entry in orch.get_tools_json_schema():
            assert "function" in entry
            fn = entry["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn
            assert fn["parameters"]["type"] == "object"

    def test_openai_schema_names_match(self, orch: ToolOrchestrator) -> None:
        """Les noms dans le schéma OpenAI correspondent aux outils."""
        openai_names = {entry["function"]["name"] for entry in orch.get_tools_json_schema()}
        assert openai_names == set(EXPECTED_TOOL_NAMES)

    def test_openai_schema_roundtrip_json(self, orch: ToolOrchestrator) -> None:
        """Le schéma OpenAI peut être sérialisé en JSON."""
        schema = orch.get_tools_json_schema()
        serialized = json.dumps(schema, ensure_ascii=False)
        recovered = json.loads(serialized)
        assert isinstance(recovered, list)
        assert len(recovered) == TOTAL_EXPECTED_TOOLS


# ══════════════════════════════════════════════════════════════════
# 9. Execute — unknown tools & edge cases
# ══════════════════════════════════════════════════════════════════


class TestExecuteEdgeCases:
    """Vérification de l'exécution pour les cas limites."""

    def test_execute_unknown_tool(self, orch: ToolOrchestrator) -> None:
        """execute() sur un outil inconnu retourne ToolResult avec erreur."""
        result = orch.execute("outil_inexistant", {})
        assert isinstance(result, ToolResult)
        assert result.success is False
        assert "inconnu" in (result.error or "").lower() or "pas de handler" in (result.error or "").lower()

    def test_execute_no_params_defaults_to_empty(self, orch: ToolOrchestrator) -> None:
        """execute() sans params utilise un dict vide."""
        result = orch.execute("outil_inexistant")
        assert isinstance(result, ToolResult)
        assert result.success is False

    def test_execute_shell_tool_ok(self, orch: ToolOrchestrator) -> None:
        """L'exécuteur a un handler pour shell_exec."""
        executor = orch.get_executor()
        assert "shell_exec" in executor._handlers

    def test_execute_with_none_params(self, orch: ToolOrchestrator) -> None:
        """execute(name, None) ne lève pas d'exception."""
        result = orch.execute("outil_test", None)
        assert isinstance(result, ToolResult)

    def test_registry_get_returns_none_for_unknown(self, orch: ToolOrchestrator) -> None:
        """registry.get() retourne None pour un outil inconnu."""
        assert orch.get_registry().get("inexistant") is None

    def test_executor_execute_nonexistent_handler(self, orch: ToolOrchestrator) -> None:
        """Executor.execute() retourne une erreur si le handler n'existe pas."""
        # Enregistrer un tool sans handler
        from src.tools.registry import ToolDefinition, ToolParameter

        orch.get_registry().register(
            ToolDefinition(
                name="tool_sans_handler",
                description="Test",
                category="system",
                parameters=[
                    ToolParameter(name="x", type="str", description="test")
                ],
            )
        )
        result = orch.get_executor().execute("tool_sans_handler", {"x": "y"})
        assert result.success is False
        assert "handler" in (result.error or "").lower()


# ══════════════════════════════════════════════════════════════════
# 10. Execute — handler verification per module
# ══════════════════════════════════════════════════════════════════


class TestExecuteModuleHandlers:
    """Vérifie que chaque module a des handlers qui répondent."""

    def _check_handler(
        self, orch: ToolOrchestrator, tool_name: str, params: dict[str, Any]
    ) -> None:
        """Vérifie que le handler existe et peut être appelé (peut échouer)."""
        executor = orch.get_executor()
        assert tool_name in executor._handlers, (
            f"Handler manquant: {tool_name}"
        )
        # On vérifie que l'appel est possible (même s'il échoue pour raisons métier)
        result = executor.execute(tool_name, params)
        assert isinstance(result, ToolResult)
        # Au moins, le handler a été trouvé et appelé (success ou non)
        # (ne pas faire d'assertion sur result.success car ça peut dépendre
        #  de l'environnement — ex: Playwright non installé)

    def test_shell_exec_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler shell_exec peut être appelé."""
        self._check_handler(orch, "shell_exec", {"command": "echo hello"})

    def test_shell_dry_run_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler shell_dry_run peut être appelé."""
        self._check_handler(orch, "shell_dry_run", {"command": "echo hello"})

    def test_os_open_app_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler os_open_app peut être appelé."""
        self._check_handler(orch, "os_open_app", {"name": "Finder"})

    def test_os_control_app_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler os_control_app peut être appelé."""
        self._check_handler(orch, "os_control_app", {"action": "focus", "name": "Finder"})

    def test_os_control_window_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler os_control_window peut être appelé."""
        self._check_handler(
            orch,
            "os_control_window",
            {"action": "list"},
        )

    def test_os_system_control_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler os_system_control peut être appelé."""
        self._check_handler(orch, "os_system_control", {"action": "volume_get"})

    def test_os_applescript_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler os_applescript peut être appelé."""
        self._check_handler(orch, "os_applescript", {"script": 'return "hello"'})

    def test_os_discover_apps_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler os_discover_apps peut être appelé."""
        self._check_handler(orch, "os_discover_apps", {})

    def test_os_screenshot_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler os_screenshot peut être appelé."""
        self._check_handler(orch, "os_screenshot", {})

    def test_os_type_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler os_type peut être appelé."""
        self._check_handler(orch, "os_type", {"text": "hello"})

    def test_browser_navigate_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler browser_navigate peut être appelé."""
        self._check_handler(
            orch,
            "browser_navigate",
            {"url": "https://example.com", "timeout": 5000},
        )

    def test_browser_click_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler browser_click peut être appelé."""
        self._check_handler(orch, "browser_click", {"selector": "body"})

    def test_browser_type_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler browser_type peut être appelé."""
        self._check_handler(orch, "browser_type", {"selector": "input", "text": "test"})

    def test_browser_extract_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler browser_extract peut être appelé."""
        self._check_handler(orch, "browser_extract", {})

    def test_browser_screenshot_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler browser_screenshot peut être appelé."""
        self._check_handler(orch, "browser_screenshot", {})

    def test_browser_scroll_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler browser_scroll peut être appelé."""
        self._check_handler(orch, "browser_scroll", {"direction": "down"})

    def test_browser_form_fill_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler browser_form_fill peut être appelé."""
        self._check_handler(
            orch,
            "browser_form_fill",
            {"fields": [{"selector": "#name", "value": "test"}]},
        )

    def test_browser_execute_script_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler browser_execute_script peut être appelé."""
        self._check_handler(
            orch,
            "browser_execute_script",
            {"script": "document.title"},
        )

    def test_browser_get_info_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler browser_get_info peut être appelé."""
        self._check_handler(orch, "browser_get_info", {})

    def test_file_read_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler file_read peut être appelé."""
        self._check_handler(
            orch,
            "file_read",
            {"path": "/tmp/test_orchestrator_lecture.txt"},
        )

    def test_file_write_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler file_write peut être appelé."""
        self._check_handler(
            orch,
            "file_write",
            {"path": "/tmp/test_orchestrator_ecriture.txt", "content": "test"},
        )

    def test_file_append_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler file_append peut être appelé."""
        self._check_handler(
            orch,
            "file_append",
            {"path": "/tmp/test_orchestrator_append.txt", "content": "ligne"},
        )

    def test_file_delete_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler file_delete peut être appelé."""
        self._check_handler(orch, "file_delete", {"path": "/tmp/test_orchestrator_delete.txt"})

    def test_file_move_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler file_move peut être appelé."""
        self._check_handler(
            orch,
            "file_move",
            {"source": "/tmp/test_orchestrator_src.txt", "destination": "/tmp/test_orchestrator_dst.txt"},
        )

    def test_file_copy_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler file_copy peut être appelé."""
        self._check_handler(
            orch,
            "file_copy",
            {"source": "/tmp/test_orchestrator_cpy_src.txt", "destination": "/tmp/test_orchestrator_cpy_dst.txt"},
        )

    def test_file_mkdir_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler file_mkdir peut être appelé."""
        self._check_handler(
            orch,
            "file_mkdir",
            {"path": "/tmp/test_orchestrateur_dossier"},
        )

    def test_file_list_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler file_list peut être appelé."""
        self._check_handler(
            orch,
            "file_list",
            {"path": "/tmp"},
        )

    def test_file_info_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler file_info peut être appelé."""
        self._check_handler(orch, "file_info", {"path": "/tmp"})

    def test_file_search_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler file_search peut être appelé."""
        self._check_handler(orch, "file_search", {"pattern": "*.txt"})

    def test_file_workspace_info_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler file_workspace_info peut être appelé."""
        self._check_handler(orch, "file_workspace_info", {})

    def test_file_authorize_directory_handler_callable(self, orch: ToolOrchestrator) -> None:
        """Le handler file_authorize_directory peut être appelé."""
        self._check_handler(
            orch,
            "file_authorize_directory",
            {"path": "/tmp"},
        )


# ══════════════════════════════════════════════════════════════════
# 11. Reset
# ══════════════════════════════════════════════════════════════════


class TestReset:
    """Vérification de la réinitialisation."""

    def test_reset_clears_registry(self, orch: ToolOrchestrator) -> None:
        """reset() vide le registre."""
        assert len(orch.get_registry()) > 0
        orch.reset()
        assert len(orch.get_registry()) == 0
        assert orch.is_setup() is False

    def test_reset_then_setup_works(self, orch: ToolOrchestrator) -> None:
        """Après reset(), un nouveau setup() fonctionne."""
        orch.reset()
        orch.setup()
        assert len(orch.get_registry()) == TOTAL_EXPECTED_TOOLS
        assert orch.is_setup() is True

    def test_reset_clears_executor_handlers(self, orch: ToolOrchestrator) -> None:
        """reset() vide les handlers de l'exécuteur."""
        assert len(orch.get_executor()._handlers) > 0
        orch.reset()
        assert len(orch.get_executor()._handlers) == 0


# ══════════════════════════════════════════════════════════════════
# 12. Integration — result types
# ══════════════════════════════════════════════════════════════════


class TestIntegration:
    """Vérifications intégrées supplémentaires."""

    def test_registry_and_executor_use_same_registry(self, orch: ToolOrchestrator) -> None:
        """Le registre et l'exécuteur partagent la même instance de registre."""
        assert orch.get_executor().registry is orch.get_registry()

    def test_get_instance_after_setup(self, orch: ToolOrchestrator) -> None:
        """get_instance() après setup() retourne l'instance configurée."""
        ToolOrchestrator._reset_singleton()
        instance = ToolOrchestrator.get_instance()
        assert instance.is_setup() is False
        instance.setup()
        assert instance.is_setup() is True
        same = ToolOrchestrator.get_instance()
        assert same.is_setup() is True
        assert same is instance

    def test_unknown_category_returns_empty_list(self, orch: ToolOrchestrator) -> None:
        """get_tools_by_category() avec catégorie inconnue retourne []."""
        assert orch.get_tools_by_category("unknown_xyz") == []

    def test_list_categories_contains_all(self, orch: ToolOrchestrator) -> None:
        """list_categories() contient 'system', 'web', 'memory'."""
        cats = orch.list_categories()
        assert "system" in cats
        assert "web" in cats
        assert "memory" in cats
        assert sum(cats.values()) == TOTAL_EXPECTED_TOOLS

    def test_tool_schema_name_equals_definition_name(self, orch: ToolOrchestrator) -> None:
        """Le nom dans to_schema() correspond au nom du ToolDefinition."""
        for tool in orch.get_registry().list_tools():
            schema = tool.to_schema()
            assert schema["name"] == tool.name

    def test_parameter_required_field_in_schema(self, orch: ToolOrchestrator) -> None:
        """Les paramètres required apparaissent dans le champ required du schema."""
        for tool in orch.get_registry().list_tools():
            schema = tool.to_schema()
            required = schema["parameters"].get("required", [])
            for param in tool.parameters:
                if param.required:
                    assert param.name in required, (
                        f"Le paramètre requis {param.name} de {tool.name} "
                        f"n'est pas dans required={required}"
                    )
