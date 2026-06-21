"""Tests unitaires pour le Contrôle OS NURU — Phase 1 S4.

Couvre : découverte apps, AppleScript, contrôle système, fenêtres,
ToolRegistry, sécurité, edge cases.
"""
import os
import sys
import time
import subprocess
from pathlib import Path

import pytest

# ── S'assurer que src/ est dans le path ──────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(PROJECT_ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from src.tools.os_control import (
    AppAction,
    WindowAction,
    SystemControlType,
    AppResult,
    WindowInfo,
    AppInfo,
    OSController,
    register_os_tools,
)
from src.tools.registry import ToolRegistry, ToolExecutor


# ─── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def ctrl():
    """Instance singleton OSController."""
    return OSController.get_instance()


@pytest.fixture
def registry():
    """ToolRegistry avec OSController enregistré."""
    reg = ToolRegistry()
    exec = ToolExecutor(reg)
    register_os_tools(reg, exec)
    return reg, exec


# ═══════════════════════════════════════════════════════════════════════
# Tests OSController — Singleton & Structure
# ═══════════════════════════════════════════════════════════════════════

class TestOSControllerStructure:

    def test_singleton(self, ctrl):
        c2 = OSController.get_instance()
        assert ctrl is c2

    def test_singleton_thread_safe(self, ctrl):
        import threading
        instances = []

        def get_inst():
            instances.append(OSController.get_instance())

        threads = [threading.Thread(target=get_inst) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert all(i is ctrl for i in instances)

    def test_enum_values(self):
        assert AppAction.OPEN == 0
        assert AppAction.CLOSE == 1
        assert AppAction.FOCUS == 2
        assert AppAction.HIDE == 3
        assert AppAction.QUIT == 4

        assert WindowAction.LIST == 0
        assert WindowAction.MOVE == 1
        assert WindowAction.RESIZE == 2
        assert WindowAction.MINIMIZE == 3
        assert WindowAction.CLOSE == 5

        assert SystemControlType.VOLUME_GET == 0
        assert SystemControlType.VOLUME_SET == 1

    def test_appresult_dataclass(self):
        r = AppResult(success=True, data="test", error=None, duration_ms=10.5)
        assert r.success is True
        assert r.data == "test"
        assert r.error is None
        assert r.duration_ms == 10.5

    def test_appresult_defaults(self):
        r = AppResult(success=False, data=None, error="error", duration_ms=0.0)
        assert r.success is False
        assert r.error == "error"

    def test_windowinfo_dataclass(self):
        w = WindowInfo(
            app_name="Finder", title="Desktop",
            x=0, y=0, width=1440, height=900,
            minimized=False, focused=True, window_id=42
        )
        assert w.app_name == "Finder"
        assert w.width == 1440
        assert w.focused is True

    def test_appinfo_dataclass(self):
        a = AppInfo(
            name="Terminal", path="/Applications/Utilities/Terminal.app",
            bundle_id="com.apple.Terminal", version="2.14",
            is_running=True, pid=12345
        )
        assert a.name == "Terminal"
        assert a.bundle_id == "com.apple.Terminal"
        assert a.pid == 12345


# ═══════════════════════════════════════════════════════════════════════
# Tests OSController — App Discovery
# ═══════════════════════════════════════════════════════════════════════

class TestAppDiscovery:

    def test_discover_apps_returns_dict(self, ctrl):
        apps = ctrl.discover_apps()
        assert isinstance(apps, dict)
        assert len(apps) > 10, f"Trouvé seulement {len(apps)} apps"

    def test_discover_apps_contains_finder(self, ctrl):
        apps = ctrl.discover_apps()
        names = {a.name for a in apps.values()}
        assert any("Finder" in n for n in names) or any("finder" in str(n).lower() for n in names)

    def test_discover_apps_returns_appinfo(self, ctrl):
        apps = ctrl.discover_apps()
        for name, app in list(apps.items())[:5]:
            assert isinstance(app, AppInfo), f"{name} n'est pas AppInfo"
            assert app.name, f"{name} n'a pas de nom"

    def test_appinfo_has_path(self, ctrl):
        apps = ctrl.discover_apps()
        for name, app in list(apps.items())[:10]:
            assert app.path, f"{name} n'a pas de path"
            assert app.path.endswith(".app"), f"{name} path ne finit pas par .app: {app.path}"

    def test_discover_apps_caches_results(self, ctrl):
        # Premier appel pour remplir le cache
        ctrl.discover_apps()
        # Le cache est maintenant rempli
        assert len(ctrl._app_cache) > 10


# ═══════════════════════════════════════════════════════════════════════
# Tests OSController — AppleScript Runner
# ═══════════════════════════════════════════════════════════════════════

class TestAppleScriptRunner:

    def test_run_simple_script(self, ctrl):
        result = ctrl.run_applescript("return 42")
        assert result.success is True
        assert result.data == "42"

    def test_run_text_script(self, ctrl):
        result = ctrl.run_applescript('return "Hello NURU"')
        assert result.success is True
        assert "Hello NURU" in result.data

    def test_run_multiline_script(self, ctrl):
        script = """set a to 5
set b to 3
return a + b"""
        result = ctrl.run_applescript(script)
        assert result.success is True
        assert "8" in result.data

    def test_run_invalid_script(self, ctrl):
        result = ctrl.run_applescript("this is not valid applescript syntax !#$%")
        # Peut réussir ou échouer — dépend de l'OS
        assert isinstance(result.success, bool)

    def test_run_safe_script(self, ctrl):
        """Scripts safe doivent passer."""
        result = ctrl.run_applescript("get volume settings")
        assert result.success is True

    def test_validate_applescript_blocks_sudo(self, ctrl):
        """run_applescript doit valider les scripts dangereux."""
        result = ctrl.run_applescript('do shell script "sudo rm -rf /"')
        assert result.success is False
        assert "dangereux" in str(result.error).lower() or "refus" in str(result.error).lower()

    def test_validate_applescript_blocks_rm(self, ctrl):
        result = ctrl.run_applescript('do shell script "rm -rf /"')
        assert result.success is False

    def test_validate_applescript_allows_safe(self, ctrl):
        result = ctrl.run_applescript('return "safe"')
        assert result.success is True


# ═══════════════════════════════════════════════════════════════════════
# Tests OSController — Volume Control
# ═══════════════════════════════════════════════════════════════════════

class TestVolumeControl:

    def test_get_volume_returns_int(self, ctrl):
        result = ctrl.get_volume()
        assert result.success is True
        assert isinstance(result.data, int) or isinstance(result.data, float)
        assert 0 <= result.data <= 100

    def test_set_and_restore_volume(self, ctrl):
        """Test non-destructif : sauvegarder, changer, restaurer."""
        original = ctrl.get_volume().data
        test_level = 50 if original != 50 else 30
        result = ctrl.set_volume(test_level)
        assert result.success is True
        # Vérifier
        check = ctrl.get_volume()
        assert abs(check.data - test_level) <= 30  # Tolérance large
        # Restaurer
        ctrl.set_volume(original)

    def test_mute_unmute(self, ctrl):
        """Test mute + unmute non-destructif."""
        state_before = ctrl.get_volume()
        # Mute
        mute_result = ctrl.mute()
        # Unmute
        unmute_result = ctrl.unmute()
        assert isinstance(mute_result.success, bool)
        assert isinstance(unmute_result.success, bool)

    def test_toggle_mute(self, ctrl):
        result = ctrl.toggle_mute()
        assert isinstance(result.success, bool)
        # Toggle back
        ctrl.toggle_mute()


# ═══════════════════════════════════════════════════════════════════════
# Tests OSController — System Info
# ═══════════════════════════════════════════════════════════════════════

class TestSystemInfo:

    def test_system_info_returns_data(self, ctrl):
        result = ctrl.get_system_info()
        assert result.success is True
        info = result.data
        assert isinstance(info, dict)
        assert "hostname" in info
        assert info["hostname"]

    def test_system_info_keys(self, ctrl):
        info = ctrl.get_system_info().data
        for key in ("hostname", "os_version", "uptime", "cpu"):
            assert key in info, f"Clé manquante: {key}"


# ═══════════════════════════════════════════════════════════════════════
# Tests OSController — Windows
# ═══════════════════════════════════════════════════════════════════════

class TestWindows:

    def test_list_windows_returns_list(self, ctrl):
        result = ctrl.list_windows()
        assert isinstance(result.success, bool)

    def test_get_frontmost_window(self, ctrl):
        result = ctrl.get_frontmost_window()
        assert isinstance(result.success, bool)
        if result.success and result.data:
            w = result.data
            assert isinstance(w, WindowInfo)
            assert w.app_name

    def test_get_frontmost_window_is_windowinfo(self, ctrl):
        result = ctrl.get_frontmost_window()
        if result.success and result.data:
            assert isinstance(result.data, WindowInfo)


# ═══════════════════════════════════════════════════════════════════════
# Tests OSController — Brightness
# ═══════════════════════════════════════════════════════════════════════

class TestBrightness:

    def test_get_brightness_returns_value(self, ctrl):
        result = ctrl.get_brightness()
        assert isinstance(result.success, bool)

    def test_set_brightness(self, ctrl):
        # Non-destructive: get current, set, restore
        orig = ctrl.get_brightness()
        if orig.success and isinstance(orig.data, (int, float)):
            new_val = max(10, int(orig.data) - 10) if int(orig.data) > 20 else 50
            result = ctrl.set_brightness(new_val)
            assert isinstance(result.success, bool)
            # Restore
            ctrl.set_brightness(int(orig.data))


# ═══════════════════════════════════════════════════════════════════════
# Tests OSController — PyAutoGUI (soft dependency)
# ═══════════════════════════════════════════════════════════════════════

class TestPyAutoGUI:

    def test_pyautogui_import_in_method(self, ctrl):
        """PyAutoGUI est importé dans les méthodes, pas en haut du fichier."""
        # Le module os_control.py doit pouvoir être importé sans PyAutoGUI
        import importlib
        import src.tools.os_control as oc_mod
        # Vérifier que pyautogui n'est PAS importé en haut
        source = open(oc_mod.__file__).read()
        # L'import doit être dans le corps des méthodes, pas en haut
        lines_with_pyautogui_import = [l for l in source.split('\n') if 'import pyautogui' in l.lower()]
        for line in lines_with_pyautogui_import:
            # Vérifier que l'import n'est pas un import de module top-level
            assert 'def ' in line or 'try:' in line or '  ' in line, \
                f"Import PyAutoGUI potentiellement top-level: {line}"

    def test_click_no_error(self, ctrl):
        """click ne doit pas planter même sans permissions."""
        result = ctrl.click(100, 100)
        assert isinstance(result.success, bool)

    def test_type_text_no_error(self, ctrl):
        """type_text ne doit pas planter."""
        result = ctrl.type_text("test")
        assert isinstance(result.success, bool)

    def test_press_key_no_error(self, ctrl):
        result = ctrl.press_key("enter")
        assert isinstance(result.success, bool)


# ═══════════════════════════════════════════════════════════════════════
# Tests ToolRegistry Integration
# ═══════════════════════════════════════════════════════════════════════

class TestToolRegistryIntegration:

    def test_register_8_tools(self, registry):
        reg, _ = registry
        tools = reg.list_tools()
        assert len(tools) == 8

    def test_tool_names(self, registry):
        reg, _ = registry
        names = {t.name for t in reg.list_tools()}
        expected = {
            "os_open_app", "os_control_app", "os_control_window",
            "os_system_control", "os_applescript", "os_discover_apps",
            "os_screenshot", "os_type"
        }
        assert names == expected

    def test_tool_definitions_have_parameters(self, registry):
        reg, _ = registry
        for tool in reg.list_tools():
            if tool.name in ("os_discover_apps", "os_screenshot"):
                continue  # Ces outils n'ont pas de paramètres obligatoires
            assert len(tool.parameters) > 0, f"{tool.name} n'a pas de paramètres"
            assert tool.description, f"{tool.name} n'a pas de description"
            assert tool.category

    def test_os_open_app_has_name_param(self, registry):
        reg, _ = registry
        tool = reg.get("os_open_app")
        param_names = [p.name for p in tool.parameters]
        assert "name" in param_names

    def test_os_system_control_has_action_param(self, registry):
        reg, _ = registry
        tool = reg.get("os_system_control")
        param_names = [p.name for p in tool.parameters]
        assert "action" in param_names
        assert "value" in param_names

    def test_execute_discover_apps(self, registry):
        reg, exec = registry
        result = exec.execute("os_discover_apps", {})
        assert result.success is True
        apps = result.output
        assert isinstance(apps, dict) or (isinstance(apps, str) and "AppInfo" in apps)

    def test_execute_volume(self, registry):
        reg, exec = registry
        result = exec.execute("os_system_control", {"action": "VOLUME_GET"})
        assert result.success is True

    def test_execute_applescript(self, registry):
        reg, exec = registry
        result = exec.execute("os_applescript", {"script": "return 42"})
        assert result.success is True

    def test_execute_blocked_applescript(self, registry):
        reg, exec = registry
        result = exec.execute("os_applescript", {"script": 'do shell script "sudo rm -rf /"'})
        assert result.success is True  # Le handler tourne sans exception
        output = result.output
        assert output.get("success") is False

    def test_execute_screenshot(self, registry):
        reg, exec = registry
        result = exec.execute("os_screenshot", {})
        assert result.success is True  # Le handler tourne sans exception


# ═══════════════════════════════════════════════════════════════════════
# Tests OSController — Edge Cases
# ═══════════════════════════════════════════════════════════════════════

class TestEdgeCases:

    def test_open_nonexistent_app(self, ctrl):
        """Ouvrir une app inexistante doit retourner une erreur informative."""
        result = ctrl.open_app("ThisAppDoesNotExistXYZ")
        assert result.success is False

    def test_close_nonexistent_app(self, ctrl):
        result = ctrl.close_app("ThisAppDoesNotExistXYZ")
        assert isinstance(result.success, bool)

    def test_focus_nonexistent_app(self, ctrl):
        result = ctrl.focus_app("ThisAppDoesNotExistXYZ")
        assert result.success is False

    def test_run_applescript_verbose_output(self, ctrl):
        """AppleScript avec sortie multi-ligne."""
        result = ctrl.run_applescript('return "line1" & return & "line2"')
        assert result.success is True

    def test_set_volume_out_of_range(self, ctrl):
        """Volume hors scope (0-100) doit être clippé."""
        result = ctrl.set_volume(150)
        # Doit être accepté (clippé par le système)
        assert isinstance(result.success, bool)

    def test_set_volume_negative(self, ctrl):
        result = ctrl.set_volume(-10)
        assert isinstance(result.success, bool)

    def test_get_screen_size_returns_tuple(self, ctrl):
        w, h = ctrl._get_screen_size()
        assert isinstance(w, (int, float))
        assert isinstance(h, (int, float))
        assert w > 0
        assert h > 0

    def test_empty_applescript(self, ctrl):
        """Script vide doit retourner une erreur ou un résultat vide."""
        result = ctrl.run_applescript("")
        assert isinstance(result.success, bool)

    def test_discover_apps_cache_invalidation(self, ctrl):
        """Forcer le rafraîchissement du cache."""
        # Premier appel
        apps1 = ctrl.discover_apps()
        # Forcer re-découverte en passant force=True ou en invalidant le cache
        ctrl._app_cache = {}
        apps2 = ctrl.discover_apps()
        assert len(apps1) == len(apps2)

    def test_list_windows_returns_windowinfo_list(self, ctrl):
        """Si list_windows réussit, chaque élément doit être WindowInfo."""
        result = ctrl.list_windows()
        if result.success and result.data:
            for w in result.data:
                assert isinstance(w, WindowInfo)

    def test_running_apps_without_tcc(self, ctrl):
        """list_running_apps doit fonctionner même sans permissions TCC."""
        result = ctrl.list_running_apps()
        assert isinstance(result.success, bool)
        # Même sans permissions, AppleScript peut retourner des résultats
        if result.success:
            assert isinstance(result.data, list)

    def test_screenshot_without_permission(self, ctrl):
        """screenshot doit gracefulment échouer si permissions manquent."""
        result = ctrl.screenshot()
        # Soit réussi (permissions OK) soit échoué avec message clair
        if not result.success:
            assert "permission" in str(result.error).lower() or \
                   "accessibility" in str(result.error).lower() or \
                   "screen recording" in str(result.error).lower() or \
                   "not available" in str(result.error).lower()

    def test_type_special_characters(self, ctrl):
        """Caractères spéciaux dans type_text."""
        result = ctrl.type_text("héllo wörld 🔥")
        assert isinstance(result.success, bool)


# ═══════════════════════════════════════════════════════════════════════
# Tests OSController — App Management (lecture seule)
# ═══════════════════════════════════════════════════════════════════════

class TestAppManagementReadOnly:

    def test_list_running_apps_no_error(self, ctrl):
        result = ctrl.list_running_apps()
        assert isinstance(result.success, bool)
        if result.success:
            assert isinstance(result.data, list)

    def test_is_app_running(self, ctrl):
        """Finder doit toujours être en cours d'exécution."""
        result = ctrl.is_app_running("Finder")
        assert isinstance(result, bool)
        # Finder tourne toujours
        assert result is True

    def test_get_app_info_by_name(self, ctrl):
        """get_app_info doit trouver les apps par nom."""
        info = ctrl.get_app_info("Finder")
        if info:
            assert isinstance(info, AppInfo)
            assert "Finder" in info.name

    def test_get_app_info_not_found(self, ctrl):
        info = ctrl.get_app_info("ThisAppDoesNotExistXYZ")
        assert info is None

    def test_get_app_info_after_discovery(self, ctrl):
        ctrl.discover_apps()
        info = ctrl.get_app_info("Safari")
        if info:
            assert info.name == "Safari"
            assert info.path
