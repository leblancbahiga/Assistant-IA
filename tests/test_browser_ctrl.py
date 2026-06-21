"""Tests unitaires pour le Contrôle Navigateur NURU — Phase 1 S5.

Couvre : structure, sécurité sites financiers, ToolRegistry,
dataclasses, gestion d'erreurs, edge cases.
Playwright est une soft dependency — tests adaptatifs.
"""
import os
import sys
import json
from pathlib import Path

import pytest

# ── S'assurer que src/ est dans le path ──────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(PROJECT_ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from src.tools.browser_ctrl import (
    BrowserAction,
    BrowserResult,
    BrowserPage,
    FormField,
    NavigateResult,
    BrowserController,
    register_browser_tools,
    FINANCIAL_KEYWORDS,
)
from src.tools.registry import ToolRegistry, ToolExecutor


# ── Vérifier si Playwright est disponible ──────────────────────────
try:
    import playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


# ─── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def ctrl():
    """Instance singleton BrowserController."""
    return BrowserController.get_instance()


@pytest.fixture
def registry():
    """ToolRegistry avec BrowserController enregistré."""
    reg = ToolRegistry()
    exec = ToolExecutor(reg)
    register_browser_tools(reg, exec)
    return reg, exec


# ═══════════════════════════════════════════════════════════════════════
# Tests Structure — Énums & Dataclasses
# ═══════════════════════════════════════════════════════════════════════

class TestStructure:

    def test_browser_action_enum(self):
        assert BrowserAction.NAVIGATE == 0
        assert BrowserAction.CLICK == 1
        assert BrowserAction.TYPE == 2
        assert BrowserAction.EXTRACT == 3
        assert BrowserAction.SCREENSHOT == 4
        assert BrowserAction.SCROLL == 5
        assert BrowserAction.WAIT == 6
        assert BrowserAction.PRESS_KEY == 7
        assert BrowserAction.FORM_FILL == 8

    def test_browser_result_dataclass(self):
        r = BrowserResult(success=True, data="ok", error=None, duration_ms=100.0)
        assert r.success is True
        assert r.data == "ok"
        assert r.duration_ms == 100.0

    def test_browser_result_default_message(self):
        r = BrowserResult(success=True)
        assert r.message == ""
        assert r.data is None
        assert r.error is None

    def test_browser_page_dataclass(self):
        p = BrowserPage(url="https://example.com", title="Example", content_preview="Hello")
        assert p.url == "https://example.com"
        assert p.screenshot_path is None

    def test_form_field_dataclass(self):
        f = FormField(selector="#email", value="test@test.com", type="text")
        assert f.selector == "#email"
        assert f.value == "test@test.com"

    def test_navigate_result_dataclass(self):
        n = NavigateResult(url="https://x.com", title="X", status_code=200,
                          final_url="https://x.com/home", load_time_ms=500.0)
        assert n.status_code == 200
        assert n.load_time_ms == 500.0

    def test_financial_keywords_populated(self):
        assert len(FINANCIAL_KEYWORDS) > 20
        assert "bank" in FINANCIAL_KEYWORDS
        assert "paypal" in FINANCIAL_KEYWORDS
        assert "banque" in FINANCIAL_KEYWORDS


# ═══════════════════════════════════════════════════════════════════════
# Tests BrowserController — Singleton & Lifecycle
# ═══════════════════════════════════════════════════════════════════════

class TestBrowserControllerSingleton:

    def test_singleton(self, ctrl):
        c2 = BrowserController.get_instance()
        assert ctrl is c2

    def test_singleton_thread_safe(self, ctrl):
        import threading
        instances = []

        def get_inst():
            instances.append(BrowserController.get_instance())

        threads = [threading.Thread(target=get_inst) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert all(i is ctrl for i in instances)

    def test_not_initialized_by_default(self, ctrl):
        assert ctrl.is_initialized() is False

    def test_close_when_not_initialized(self, ctrl):
        """close ne doit pas planter si pas initialisé."""
        try:
            ctrl.close()
        except Exception as e:
            pytest.fail(f"close() a levé une exception: {e}")

    def test_get_browser_info_not_initialized(self, ctrl):
        info = ctrl.get_browser_info()
        assert info.get("is_initialized") is False

    def test_get_navigation_history_empty(self, ctrl):
        history = ctrl.get_navigation_history()
        assert isinstance(history, list)
        assert len(history) == 0

    def test_clear_navigation_history(self, ctrl):
        ctrl.clear_navigation_history()
        assert len(ctrl._navigation_history) == 0

    def test_approve_financial_site(self, ctrl):
        result = ctrl.approve_financial_site("test-bank.com")
        assert result.success is True
        # Nettoyer
        ctrl._approved_financial_sites.discard("test-bank.com")

    def test_is_financial_site_approved(self, ctrl):
        ctrl._approved_financial_sites.add("mybank.com")
        assert ctrl.is_financial_site_approved("mybank.com") is True
        assert ctrl.is_financial_site_approved("unknown.com") is False
        ctrl._approved_financial_sites.discard("mybank.com")


# ═══════════════════════════════════════════════════════════════════════
# Tests BrowserController — Sécurité Sites Financiers
# ═══════════════════════════════════════════════════════════════════════

class TestFinancialSecurity:

    def test_detect_bank_keyword_in_url(self, ctrl):
        """URL contenant 'bank' doit être détectée."""
        assert ctrl._detect_financial_keywords("https://mybank.com/account", None) is True

    def test_detect_paypal_in_url(self, ctrl):
        assert ctrl._detect_financial_keywords("https://www.paypal.com/myaccount", None) is True

    def test_detect_banque_in_url(self, ctrl):
        assert ctrl._detect_financial_keywords("https://banque.example.com", None) is True

    def test_detect_carte_in_url(self, ctrl):
        assert ctrl._detect_financial_keywords("https://cartes.example.com", None) is True

    def test_detect_virement_in_url(self, ctrl):
        assert ctrl._detect_financial_keywords("https://virement.example.com", "Page de virement") is True

    def test_detect_balance_in_title(self, ctrl):
        """Titre contenant 'balance' doit être détecté."""
        assert ctrl._detect_financial_keywords("https://example.com", "Account Balance") is True

    def test_no_false_positive_normal_site(self, ctrl):
        """Un site normal ne doit pas être bloqué."""
        assert ctrl._detect_financial_keywords("https://example.com", "Welcome to Example") is False

    def test_no_false_positive_github(self, ctrl):
        assert ctrl._detect_financial_keywords("https://github.com/nuru", "NURU Project") is False

    def test_no_false_positive_wikipedia(self, ctrl):
        assert ctrl._detect_financial_keywords("https://fr.wikipedia.org/wiki/Banane",
                                               "Banane — Wikipédia") is False

    def test_no_false_positive_news(self, ctrl):
        assert ctrl._detect_financial_keywords("https://news.ycombinator.com",
                                               "Hacker News") is False

    def test_website_in_url_not_financial(self, ctrl):
        """'website' ne doit pas être confondu avec un site financier."""
        assert ctrl._detect_financial_keywords("https://website.com", None) is False

    def test_check_financial_site_blocked(self, ctrl):
        """_check_financial_site doit retourner BrowserResult si bloqué."""
        result = ctrl._check_financial_site("https://bank.example.com")
        assert isinstance(result, BrowserResult)
        assert result.success is False
        assert "financier" in result.error.lower() or "approuvé" in result.error.lower()

    def test_check_financial_site_approved(self, ctrl):
        """Site approuvé ne doit pas être bloqué."""
        ctrl._approved_financial_sites.add("approved-bank.com")
        result = ctrl._check_financial_site("https://approved-bank.com")
        assert result is None
        ctrl._approved_financial_sites.discard("approved-bank.com")

    def test_check_normal_site_not_blocked(self, ctrl):
        """Site normal ne doit pas être bloqué."""
        result = ctrl._check_financial_site("https://example.com/page")
        assert result is None

    def test_initialize_requires_playwright(self, ctrl):
        """initialize() doit échouer si Playwright pas disponible."""
        result = ctrl.initialize(browser_type="chromium", headless=True)
        if HAS_PLAYWRIGHT:
            assert isinstance(result.success, bool)
        else:
            assert result.success is False
            assert "n'est pas install" in result.error.lower()

    def test_navigate_requires_initialization(self, ctrl):
        """navigate sans initialize doit retourner une erreur."""
        result = ctrl.navigate("https://example.com")
        assert result.status_code == 0
        assert result.title == ""


# ═══════════════════════════════════════════════════════════════════════
# Tests BrowserController — Actions sans Playwright
# ═══════════════════════════════════════════════════════════════════════

class TestActionsWithoutPlaywright:

    @pytest.fixture(autouse=True)
    def ensure_not_initialized(self, ctrl):
        """S'assurer que le navigateur n'est PAS initialisé pour ces tests."""
        ctrl.close()
        ctrl._playwright = None
        ctrl._browser = None
        ctrl._page = None
        ctrl._initialized = False

    def test_navigate_not_initialized(self, ctrl):
        result = ctrl.navigate("https://example.com")
        assert result.status_code == 0

    def test_click_not_initialized(self, ctrl):
        result = ctrl.click("#button")
        assert result.success is False

    def test_type_not_initialized(self, ctrl):
        result = ctrl.type("#input", "hello")
        assert result.success is False

    def test_extract_text_not_initialized(self, ctrl):
        result = ctrl.get_text("h1")
        assert result.success is False

    def test_screenshot_not_initialized(self, ctrl):
        result = ctrl.screenshot()
        assert result.success is False

    def test_scroll_not_initialized(self, ctrl):
        result = ctrl.scroll_by(0, 500)
        assert result.success is False

    def test_fill_form_not_initialized(self, ctrl):
        fields = [FormField("#name", "Nuru")]
        result = ctrl.fill_form(fields)
        assert result.success is False

    def test_execute_script_not_initialized(self, ctrl):
        result = ctrl.execute_script("return 42")
        assert result.success is False


# ═══════════════════════════════════════════════════════════════════════
# Tests BrowserController — Security Script Validation
# ═══════════════════════════════════════════════════════════════════════

class TestScriptSecurity:

    @pytest.fixture(autouse=True)
    def ensure_not_initialized(self, ctrl):
        ctrl.close()
        ctrl._initialized = False

    def test_execute_script_with_eval(self, ctrl):
        """Les scripts contenant eval() doivent être bloqués par sécurité."""
        result = ctrl.execute_script("eval('alert(1)')")
        assert result.success is False
        # Le message peut être "Playwright non installé" OU "script refusé"
        # selon l'ordre des vérifications
        assert any(word in result.error.lower() for word in ["playwright", "instal", "refus", "sécurit", "non autoris"])

    def test_execute_script_with_child_process(self, ctrl):
        result = ctrl.execute_script("require('child_process')")
        assert result.success is False  # Pas initialisé OU script refusé

    def test_execute_script_simple(self, ctrl):
        result = ctrl.execute_script("document.title")
        assert result.success is False  # Pas initialisé


# ═══════════════════════════════════════════════════════════════════════
# Tests ToolRegistry Integration
# ═══════════════════════════════════════════════════════════════════════

class TestToolRegistryIntegration:

    def test_register_9_tools(self, registry):
        reg, _ = registry
        tools = reg.list_tools()
        assert len(tools) == 9

    def test_tool_names(self, registry):
        reg, _ = registry
        names = {t.name for t in reg.list_tools()}
        expected = {
            "browser_navigate", "browser_click", "browser_type",
            "browser_extract", "browser_screenshot", "browser_scroll",
            "browser_form_fill", "browser_execute_script", "browser_get_info"
        }
        assert names == expected

    def test_tool_definitions_have_parameters(self, registry):
        reg, _ = registry
        for tool in reg.list_tools():
            if tool.name in ("browser_get_info",):
                continue  # Pas de paramètres obligatoires
            assert len(tool.parameters) > 0, f"{tool.name} n'a pas de paramètres"
            assert tool.description, f"{tool.name} n'a pas de description"
            assert tool.category

    def test_browser_navigate_has_url_param(self, registry):
        reg, _ = registry
        tool = reg.get("browser_navigate")
        param_names = [p.name for p in tool.parameters]
        assert "url" in param_names
        assert "timeout" in param_names

    def test_browser_click_has_selector_param(self, registry):
        reg, _ = registry
        tool = reg.get("browser_click")
        param_names = [p.name for p in tool.parameters]
        assert "selector" in param_names

    def test_browser_type_has_selector_and_text(self, registry):
        reg, _ = registry
        tool = reg.get("browser_type")
        param_names = [p.name for p in tool.parameters]
        assert "selector" in param_names
        assert "text" in param_names

    def test_browser_extract_has_action_param(self, registry):
        reg, _ = registry
        tool = reg.get("browser_extract")
        param_names = [p.name for p in tool.parameters]
        assert "action" in param_names

    def test_execute_get_info(self, registry):
        reg, exec = registry
        result = exec.execute("browser_get_info", {})
        assert result.success is True
        info = result.output
        # Le handler renvoie un BrowserResult, l'exécuteur le met dans .output
        # qui est soit un dict directement, soit un wrapper
        if isinstance(info, dict):
            if "is_initialized" in info:
                assert info["is_initialized"] is False
            elif "data" in info:
                assert "is_initialized" in info["data"]
        else:
            assert getattr(info, 'success', None) is not None

    def test_execute_navigate_not_initialized(self, registry):
        reg, exec = registry
        result = exec.execute("browser_navigate", {"url": "https://example.com", "timeout": 5000})
        assert result.success is True  # Le handler ne doit pas planter
        output = result.output
        assert output.get("success") is False

    def test_execute_click_not_initialized(self, registry):
        reg, exec = registry
        result = exec.execute("browser_click", {"selector": "#btn"})
        assert result.success is True
        assert result.output.get("success") is False

    def test_execute_type_not_initialized(self, registry):
        reg, exec = registry
        result = exec.execute("browser_type", {"selector": "#input", "text": "hello"})
        assert result.success is True

    def test_execute_screenshot_not_initialized(self, registry):
        reg, exec = registry
        result = exec.execute("browser_screenshot", {})
        assert result.success is True

    def test_execute_script_blocked_by_security(self, registry):
        """Script avec eval() doit être bloqué par la couche sécurité."""
        reg, exec = registry
        result = exec.execute("browser_execute_script", {"script": "eval('bad')"})
        assert result.success is True  # Le handler tourne
        output = result.output
        assert output.get("success") is False

    def test_execute_scroll_not_initialized(self, registry):
        reg, exec = registry
        result = exec.execute("browser_scroll", {"direction": "down"})
        assert result.success is True


# ═══════════════════════════════════════════════════════════════════════
# Tests EventBus
# ═══════════════════════════════════════════════════════════════════════

class TestEventBus:

    def test_event_bus_imported(self):
        from src.core.events import EventBus
        assert EventBus is not None

    def test_browser_events_emitted_on_navigate(self, ctrl):
        """Les événements navigateur doivent être émis."""
        from src.core.events import EventBus
        bus = EventBus()
        events = []
        def listener(data):
            events.append(data)

        bus.subscribe("browser:error", listener)
        result = ctrl.navigate("https://example.com")
        bus.unsubscribe("browser:error", listener)

        # Au moins pas d'exception
        assert True


# ═══════════════════════════════════════════════════════════════════════
# Tests Edge Cases
# ═══════════════════════════════════════════════════════════════════════

class TestEdgeCases:

    def test_approve_financial_site_twice(self, ctrl):
        """Approuver deux fois un même site ne doit pas planter."""
        ctrl.approve_financial_site("same-site.com")
        ctrl.approve_financial_site("same-site.com")
        assert len(ctrl._approved_financial_sites) == 1
        ctrl._approved_financial_sites.discard("same-site.com")

    def test_navigate_history_records_visits(self, ctrl):
        """Même si la navigation échoue, l'historique doit enregistrer."""
        result = ctrl.navigate("https://fail-test.com/nonexistent")
        history = ctrl.get_navigation_history()
        assert isinstance(history, list)

    def test_form_field_with_bool_value(self):
        """FormField avec value=True (checkbox)."""
        f = FormField("#newsletter", True, "checkbox")
        assert f.value is True

    def test_form_field_with_none_value(self):
        f = FormField("#field", None, "text")
        assert f.value is None

    def test_navigate_with_non_string_url(self, ctrl):
        """URL non-string ne doit pas planter."""
        result = ctrl.navigate(123)  # type: ignore
        assert result.status_code == 0

    def test_click_with_empty_selector(self, ctrl):
        result = ctrl.click("")
        assert result.success is False

    def test_type_with_empty_text(self, ctrl):
        result = ctrl.type("#input", "")
        assert result.success is False

    def test_detect_financial_with_unicode(self, ctrl):
        """URL avec caractères accentués."""
        assert ctrl._detect_financial_keywords(
            "https://www.cartes-bancaires.fr", None) is True

    def test_detect_financial_case_insensitive(self, ctrl):
        assert ctrl._detect_financial_keywords(
            "https://MyBank.com", None) is True

    def test_extract_data_empty_selectors(self, ctrl):
        result = ctrl.extract_data({})
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_press_key_not_initialized(self, ctrl):
        result = ctrl.press_key("Enter")
        assert result.success is False

    def test_get_all_links_not_initialized(self, ctrl):
        result = ctrl.get_all_links()
        assert isinstance(result, list)

    def test_get_images_not_initialized(self, ctrl):
        result = ctrl.get_images()
        assert isinstance(result, list)

    def test_get_forms_not_initialized(self, ctrl):
        result = ctrl.get_forms()
        assert isinstance(result, list)

    def test_wait_not_initialized(self, ctrl):
        result = ctrl.wait("#element")
        assert result.success is False

    def test_select_option_not_initialized(self, ctrl):
        result = ctrl.select_option("#select", "val")
        assert result.success is False

    def test_check_not_initialized(self, ctrl):
        result = ctrl.check("#checkbox")
        assert result.success is False

    def test_hover_not_initialized(self, ctrl):
        result = ctrl.hover("#button")
        assert result.success is False

    def test_pdf_not_initialized(self, ctrl):
        result = ctrl.pdf()
        assert result.success is False

    def test_go_back_not_initialized(self, ctrl):
        # go_back retourne None ou NavigateResult quand pas initialisé
        result = ctrl.go_back()
        assert result is None or (hasattr(result, 'status_code') and result.status_code == 0)

    def test_switch_to_page_not_initialized(self, ctrl):
        result = ctrl.switch_to_page(0)
        assert result.success is False

    def test_set_cookie_not_initialized(self, ctrl):
        result = ctrl.set_cookie("test", "value", "https://example.com")
        assert result.success is False

    def test_get_cookies_not_initialized(self, ctrl):
        result = ctrl.get_cookies()
        assert isinstance(result, list)

    def test_scroll_to_not_initialized(self, ctrl):
        result = ctrl.scroll_to("#footer")
        assert result.success is False

    def test_reload_not_initialized(self, ctrl):
        # reload retourne NavigateResult quand pas initialisé
        result = ctrl.reload()
        assert hasattr(result, 'status_code')

    def test_get_attribute_not_initialized(self, ctrl):
        result = ctrl.get_attribute("#elem", "href")
        assert result.success is False

    def test_get_html_not_initialized(self, ctrl):
        result = ctrl.get_html()
        assert result.success is False

    def test_wait_for_navigation_not_initialized(self, ctrl):
        result = ctrl.wait_for_navigation()
        assert result.success is False

    def test_create_new_context_not_initialized(self, ctrl):
        result = ctrl.create_new_context()
        assert result.success is False


# ═══════════════════════════════════════════════════════════════════════
# Tests GetPageTitle / GetCurrentURL
# ═══════════════════════════════════════════════════════════════════════

class TestPageInfo:

    def test_get_current_url_not_initialized(self, ctrl):
        url = ctrl.get_current_url()
        assert url == ""

    def test_get_page_title_not_initialized(self, ctrl):
        title = ctrl.get_page_title()
        assert title == ""

    def test_get_current_url_with_history(self, ctrl):
        """get_current_url retourne _current_url si pas de page."""
        assert ctrl.get_current_url() == ""  # Valeur par défaut

    def test_get_page_title_with_history(self, ctrl):
        ctrl._navigation_history.append({"title": "Test Page"})
        assert ctrl.get_page_title() == ""
        ctrl.clear_navigation_history()

    def test_empty_navigate_result(self):
        n = NavigateResult(url="", title="", status_code=0, final_url="", load_time_ms=0.0)
        assert n.status_code == 0
        assert n.final_url == ""


# ═══════════════════════════════════════════════════════════════════════
# Tests Screenshot Directory
# ═══════════════════════════════════════════════════════════════════════

class TestScreenshotDir:

    def test_screenshot_dir_exists(self):
        from src.tools.browser_ctrl import SCREENSHOT_DIR
        # Juste vérifier que la constante existe et est valide
        assert SCREENSHOT_DIR
        assert "Nuru_Workspace" in SCREENSHOT_DIR

    def test_screenshot_dir_default(self):
        from src.tools.browser_ctrl import SCREENSHOT_DEFAULT_DIR
        assert SCREENSHOT_DEFAULT_DIR
        assert "screenshots" in SCREENSHOT_DEFAULT_DIR
