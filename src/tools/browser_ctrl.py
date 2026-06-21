"""Contrôle navigateur avec Playwright — Navigation web, clics,
formulaires, extraction, screenshot, sécurité sites financiers.

Classes:
    BrowserAction: Actions disponibles sur le navigateur.
    BrowserResult: Résultat standard d'une opération navigateur.
    BrowserPage: Informations sur une page web visitée.
    FormField: Champ de formulaire à remplir.
    NavigateResult: Résultat d'une navigation vers une URL.
    BrowserController: Contrôleur navigateur singleton thread-safe.

Fonctions:
    register_browser_tools: Enregistre les outils navigateur dans le registre.

Utilisation:
    ctrl = BrowserController.get_instance()
    ctrl.initialize(browser_type="chromium", headless=False)
    result = ctrl.navigate("https://example.com")
    if result.status_code == 200:
        print(f"Page: {result.title}")
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Any

from src.core.events import EventBus
from src.tools.registry import ToolDefinition, ToolParameter, ToolExecutor, ToolRegistry

logger = logging.getLogger(__name__)

# ── Constantes ──────────────────────────────────────────────────

DEFAULT_TIMEOUT_MS: int = 30000
DEFAULT_WAIT_TIMEOUT: int = 10000
SCREENSHOT_DIR: str = os.path.expanduser("~/Nuru_Workspace/screenshots")
MAX_NAVIGATION_HISTORY: int = 100
SCREENSHOT_DEFAULT_DIR: str = os.path.expanduser("~/Nuru_Workspace/screenshots")

# Sites financiers patterns (URL + titre)
FINANCIAL_KEYWORDS: set[str] = {
    "bank", "banque", "paypal", "stripe", "credit", "carte",
    "credit-agricole", "bnp", "societe-generale", "credit-mutuel",
    "ca-caisse", "lcl", "hsbc", "ing", "fortis", "belfius",
    "deutsche-bank", "commerzbank", "postbank",
    "chase", "wells-fargo", "citi", "amex", "american-express",
    "capital-one", "us-bank", "pnc", "td-bank",
    "barclays", "lloyds", "natwest", "halifax", "santander",
    "paypal.com", "stripe.com", "square", "venmo", "wise",
    "revolut", "n26", "monzo", "starling",
    "coinbase", "binance", "kraken", "crypto",
    "virement", "paiement", "payment", "transaction",
    "compte", "account", "balance", "solde",
    "identifiant", "mot-de-passe", "password", "login",
    "code-secret", "pin", "2fa", "otp",
    "securite", "securite-sociale", "ssn", "rib", "iban",
    "carte-bleue", "carte-de-credit", "credit-card",
    "numero-carte", "card-number", "cvv", "cvc",
    "expiration", "date-expiration",
}

# ── Enums ────────────────────────────────────────────────────────


class BrowserAction(IntEnum):
    """Actions disponibles sur le navigateur.

    Values:
        NAVIGATE (0): Naviguer vers une URL.
        CLICK (1): Cliquer sur un élément.
        TYPE (2): Saisir du texte dans un champ.
        EXTRACT (3): Extraire des données de la page.
        SCREENSHOT (4): Capturer une capture d'écran.
        SCROLL (5): Défiler la page.
        WAIT (6): Attendre un élément.
        PRESS_KEY (7): Presser une touche.
        FORM_FILL (8): Remplir un formulaire.
        SELECT (9): Sélectionner une option.
        HOVER (10): Survivoler un élément.
        GET_TEXT (11): Obtenir le texte d'un élément.
        GET_ATTRIBUTE (12): Obtenir un attribut d'un élément.
        GET_URL (13): Obtenir l'URL courante.
        GET_TITLE (14): Obtenir le titre de la page.
        GET_COOKIES (15): Obtenir les cookies.
    """

    NAVIGATE = 0
    CLICK = 1
    TYPE = 2
    EXTRACT = 3
    SCREENSHOT = 4
    SCROLL = 5
    WAIT = 6
    PRESS_KEY = 7
    FORM_FILL = 8
    SELECT = 9
    HOVER = 10
    GET_TEXT = 11
    GET_ATTRIBUTE = 12
    GET_URL = 13
    GET_TITLE = 14
    GET_COOKIES = 15


# ── Dataclasses ──────────────────────────────────────────────────


@dataclass
class BrowserResult:
    """Résultat standard d'une opération navigateur.

    Attributes:
        success: L'opération a réussi.
        message: Message descriptif du résultat.
        data: Données additionnelles (texte, HTML, etc.).
        error: Message d'erreur si échec.
        duration_ms: Durée d'exécution en millisecondes.
    """

    success: bool
    message: str = ""
    data: Any = None
    error: str | None = None
    duration_ms: float = 0.0


@dataclass
class BrowserPage:
    """Informations sur une page web visitée.

    Attributes:
        url: URL de la page.
        title: Titre de la page.
        content_preview: Aperçu du contenu textuel.
        screenshot_path: Chemin de la capture d'écran prise.
        cookies: Liste des cookies de la page.
    """

    url: str
    title: str
    content_preview: str
    screenshot_path: str | None = None
    cookies: list | None = None


@dataclass
class FormField:
    """Champ de formulaire à remplir.

    Attributes:
        selector: Sélecteur CSS/XPath du champ.
        value: Valeur à saisir (str, bool pour checkbox, None).
        type: Type de champ (text, checkbox, select, radio, file).
    """

    selector: str
    value: str | bool | None
    type: str = "text"


@dataclass
class NavigateResult:
    """Résultat d'une navigation vers une URL.

    Attributes:
        url: URL demandée.
        title: Titre de la page chargée.
        status_code: Code de statut HTTP.
        final_url: URL finale après redirections.
        load_time_ms: Temps de chargement en millisecondes.
    """

    url: str
    title: str
    status_code: int
    final_url: str
    load_time_ms: float


# ── BrowserController ───────────────────────────────────────────


class BrowserController:
    """Contrôleur navigateur singleton utilisant Playwright.

    Fournit des méthodes unifiées pour :
    - Navigation web (URL, back, forward, reload)
    - Interaction (clic, saisie, sélection, survol)
    - Extraction (texte, HTML, attributs, liens, images)
    - Capture d'écran et PDF
    - Remplissage de formulaires
    - Gestion des cookies
    - Sécurité (blocage sites financiers non approuvés)

    Utilise Playwright (sync API) en dépendance logicielle (soft dep).
    Si Playwright n'est pas installé, toutes les méthodes retournent
    un BrowserResult avec erreur.

    Utilisation::
        ctrl = BrowserController.get_instance()
        result = ctrl.initialize(browser_type="chromium", headless=True)
        if result.success:
            nav = ctrl.navigate("https://example.com")
            print(f"Titre: {nav.title}")
    """

    _instance: BrowserController | None = None
    _singleton_lock: threading.Lock = threading.Lock()
    _initialized: bool = False

    def __new__(cls, *args: Any, **kwargs: Any) -> BrowserController:
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
        self._initialized = True

        # Playwright objects (lazy, set by initialize)
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._browser_type: str = "chromium"
        self._headless: bool = True
        self._channel: str | None = None
        self._browser_version: str = ""

        # Navigation state
        self._current_url: str = ""
        self._navigation_history: list[dict] = []
        self._history_lock: threading.Lock = threading.Lock()

        # Financial sites approval
        self._approved_financial_sites: set[str] = set()
        self._approval_lock: threading.Lock = threading.Lock()

        # Browser pages management
        self._pages: list[Any] = []
        self._current_page_index: int = 0
        self._pages_lock: threading.Lock = threading.Lock()

        # Error flag for missing playwright
        self._playwright_available: bool | None = None

        logger.debug("BrowserController initialisé")

    # ── Singleton helper ──

    @classmethod
    def get_instance(cls) -> BrowserController:
        """Retourne l'instance unique du contrôleur navigateur.

        Returns:
            L'instance unique de BrowserController.
        """
        return cls()

    # ── Playwright availability check ──

    @staticmethod
    def _check_playwright() -> bool:
        """Vérifie si Playwright est installé et disponible.

        Returns:
            True si Playwright peut être importé, False sinon.
        """
        try:
            import playwright  # noqa: F401
            return True
        except ImportError:
            return False

    def _ensure_playwright(self) -> BrowserResult | None:
        """Vérifie que Playwright est disponible.

        Si Playwright n'est pas installé, retourne un BrowserResult
        avec l'erreur appropriée.

        Returns:
            None si Playwright est disponible, BrowserResult sinon.
        """
        if self._playwright_available is None:
            self._playwright_available = self._check_playwright()
        if not self._playwright_available:
            return BrowserResult(
                success=False,
                message="Playwright non disponible",
                error="Playwright n'est pas installé. Installez-le avec: pip install playwright && playwright install",
            )
        return None

    # ── Lifecycle ──

    def initialize(
        self,
        browser_type: str = "chromium",
        headless: bool = True,
        channel: str | None = None,
        user_data_dir: str | None = None,
        proxy: dict | None = None,
    ) -> BrowserResult:
        """Initialise le navigateur Playwright.

        Lance Playwright, crée le navigateur, le contexte et la page.
        Si channel='chrome' ou 'firefox', utilise le navigateur système.
        Si headless=False, lance le navigateur visible.
        Si user_data_dir, préserve la session (cookies, historique).

        Args:
            browser_type: Type de navigateur ('chromium', 'firefox', 'webkit').
            headless: Lancer en mode headless (sans interface) si True.
            channel: Canal système ('chrome', 'firefox', None).
            user_data_dir: Répertoire de données utilisateur pour la session.
            proxy: Configuration proxy dict (ex: {'server': 'http://proxy:8080'}).

        Returns:
            BrowserResult indiquant le succès ou l'échec de l'initialisation.
        """
        start = time.time()
        bus = EventBus()

        # Vérifier Playwright
        playwright_check = self._ensure_playwright()
        if playwright_check is not None:
            return playwright_check

        try:
            from playwright.sync_api import sync_playwright  # soft dependency
        except ImportError:
            self._playwright_available = False
            return BrowserResult(
                success=False,
                message="Playwright non installé",
                error="Playwright non installé (soft dependency)",
                duration_ms=(time.time() - start) * 1000,
            )

        try:
            # Démarrer Playwright
            self._playwright = sync_playwright().start()

            # Sélectionner le type de navigateur
            browser_launcher = getattr(self._playwright, browser_type, None)
            if browser_launcher is None:
                self._playwright.stop()
                self._playwright = None
                return BrowserResult(
                    success=False,
                    message=f"Type de navigateur inconnu: {browser_type}",
                    error=(
                        f"Le type de navigateur '{browser_type}' n'est pas "
                        f"supporté. Utilisez 'chromium', 'firefox' ou 'webkit'."
                    ),
                    duration_ms=(time.time() - start) * 1000,
                )

            # Paramètres de lancement
            launch_options: dict[str, Any] = {
                "headless": headless,
            }
            if channel is not None:
                launch_options["channel"] = channel
            if proxy is not None:
                launch_options["proxy"] = proxy

            # Lancer le navigateur
            self._browser = browser_launcher.launch(**launch_options)
            self._browser_type = browser_type
            self._headless = headless
            self._channel = channel
            self._browser_version = self._browser.version

            # Contexte de navigation
            context_options: dict[str, Any] = {}
            if user_data_dir is not None:
                context_options["user_data_dir"] = user_data_dir

            # Configurer user-agent par défaut
            context_options.setdefault(
                "user_agent",
                (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )

            if proxy is not None:
                context_options["proxy"] = proxy

            self._context = self._browser.new_context(**context_options)
            self._page = self._context.new_page()
            self._pages = [self._page]
            self._current_page_index = 0

            # Configurer les événements de navigation
            self._page.on("load", self._on_page_load)
            self._page.on("framenavigated", self._on_frame_navigated)

            duration = (time.time() - start) * 1000
            bus.emit_sync("browser:initialized", {
                "browser_type": browser_type,
                "headless": headless,
                "channel": channel,
                "version": self._browser_version,
            })

            logger.info(
                "BrowserController initialisé: %s (headless=%s, channel=%s, v%s)",
                browser_type, headless, channel, self._browser_version,
            )

            return BrowserResult(
                success=True,
                message=f"Navigateur {browser_type} initialisé avec succès",
                data={
                    "browser_type": browser_type,
                    "headless": headless,
                    "channel": channel,
                    "version": self._browser_version,
                },
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("browser:error", {
                "action": "initialize",
                "error": str(e),
            })
            logger.error("Erreur initialisation navigateur: %s", e)
            return BrowserResult(
                success=False,
                message="Erreur lors de l'initialisation du navigateur",
                error=str(e),
                duration_ms=duration,
            )

    def _on_page_load(self, frame: Any) -> None:
        """Callback appelé lors du chargement d'une page.

        Met à jour l'URL courante et émet un événement.

        Args:
            frame: Frame Playwright qui a déclenché l'événement.
        """
        try:
            if self._page and frame == self._page:
                url = self._page.url
                self._current_url = url
                bus = EventBus()
                bus.emit_sync("browser:page:load", {"url": url})
        except Exception as e:
            logger.debug("Erreur dans _on_page_load: %s", e)

    def _on_frame_navigated(self, frame: Any) -> None:
        """Callback appelé lors de la navigation d'une frame.

        Args:
            frame: Frame Playwright qui a navigué.
        """
        try:
            if self._page and frame == self._page:
                url = self._page.url
                self._current_url = url
        except Exception as e:
            logger.debug("Erreur dans _on_frame_navigated: %s", e)

    def close(self) -> BrowserResult:
        """Ferme le navigateur proprement.

        Ferme la page, le contexte, le navigateur et Playwright dans
        l'ordre inverse de l'initialisation.

        Returns:
            BrowserResult indiquant le succès ou la fermeture.
        """
        start = time.time()
        bus = EventBus()

        errors: list[str] = []

        try:
            if self._page is not None:
                try:
                    self._page.close()
                except Exception as e:
                    errors.append(f"page.close: {e}")
                self._page = None
        except Exception as e:
            errors.append(f"page: {e}")

        try:
            if self._context is not None:
                try:
                    self._context.close()
                except Exception as e:
                    errors.append(f"context.close: {e}")
                self._context = None
        except Exception as e:
            errors.append(f"context: {e}")

        try:
            if self._browser is not None:
                try:
                    self._browser.close()
                except Exception as e:
                    errors.append(f"browser.close: {e}")
                self._browser = None
        except Exception as e:
            errors.append(f"browser: {e}")

        try:
            if self._playwright is not None:
                try:
                    self._playwright.stop()
                except Exception as e:
                    errors.append(f"playwright.stop: {e}")
                self._playwright = None
        except Exception as e:
            errors.append(f"playwright: {e}")

        self._pages = []
        self._current_page_index = 0

        duration = (time.time() - start) * 1000
        bus.emit_sync("browser:closed", {})

        if errors:
            logger.warning("BrowserController fermé avec erreurs: %s", errors)
            return BrowserResult(
                success=False,
                message="Fermeture du navigateur avec erreurs",
                error="; ".join(errors),
                duration_ms=duration,
            )

        logger.info("BrowserController fermé proprement")
        return BrowserResult(
            success=True,
            message="Navigateur fermé avec succès",
            duration_ms=duration,
        )

    def is_initialized(self) -> bool:
        """Vérifie si le navigateur est initialisé et prêt.

        Returns:
            True si le navigateur est prêt, False sinon.
        """
        return (
            self._playwright is not None
            and self._browser is not None
            and self._page is not None
            and not self._page.is_closed()
        )

    def get_browser_info(self) -> dict:
        """Retourne les informations sur le navigateur courant.

        Returns:
            Dict avec les clés: browser_type, version, headless,
            channel, is_initialized, current_url.
        """
        return {
            "browser_type": self._browser_type,
            "version": self._browser_version,
            "headless": self._headless,
            "channel": self._channel,
            "is_initialized": self.is_initialized(),
            "current_url": self._current_url,
            "pages_count": len(self._pages),
            "current_page_index": self._current_page_index,
        }

    # ── Helpers internes ──

    def _ensure_initialized(self) -> BrowserResult | None:
        """Vérifie que le navigateur est initialisé.

        Returns:
            None si le navigateur est prêt, BrowserResult d'erreur sinon.
        """
        # Vérifier Playwright
        playwright_check = self._ensure_playwright()
        if playwright_check is not None:
            return playwright_check

        if not self.is_initialized():
            return BrowserResult(
                success=False,
                message="Navigateur non initialisé",
                error=(
                    "Le navigateur n'est pas initialisé. "
                    "Appelez BrowserController.initialize() d'abord."
                ),
            )
        return None

    def _get_playwright_locator(self, page: Any, selector: str) -> Any:
        """Résout un sélecteur en un locateur Playwright.

        Supporte :
        - Sélecteurs CSS standards (ex: '#my-id', '.my-class')
        - XPath (préfixé par '//' ou 'xpath=')
        - Text matching (préfixé par 'text=')
        - Placeholder (préfixé par 'placeholder=')
        - Label (préfixé par 'label=')
        - Test-id (préfixé par 'data-testid=')

        Args:
            page: Page Playwright sur laquelle chercher.
            selector: Sélecteur à résoudre.

        Returns:
            Locateur Playwright prêt à être utilisé.
        """
        selector = selector.strip()

        # Détection automatique du type de sélecteur
        if selector.startswith("//") or selector.startswith("xpath="):
            # XPath
            if selector.startswith("xpath="):
                xpath_expr = selector[6:].strip()
            else:
                xpath_expr = selector
            return page.locator(f"xpath={xpath_expr}")

        if selector.startswith("text="):
            return page.get_by_text(selector[5:].strip())

        if selector.startswith("placeholder="):
            return page.get_by_placeholder(selector[12:].strip())

        if selector.startswith("label="):
            return page.get_by_label(selector[6:].strip())

        if selector.startswith("data-testid="):
            return page.get_by_test_id(selector[12:].strip())

        if selector.startswith("role="):
            # role=button, role=link, etc.
            role_expr = selector[5:].strip()
            return page.get_by_role(role_expr)

        if selector.startswith("alt="):
            return page.get_by_alt_text(selector[4:].strip())

        if selector.startswith("title="):
            return page.get_by_title(selector[6:].strip())

        # Par défaut : sélecteur CSS
        return page.locator(selector)

    @staticmethod
    def _sanitize_input(text: str) -> str:
        """Nettoie le texte avant de le saisir dans un champ.

        Supprime les caractères de contrôle et normalise les espaces.

        Args:
            text: Texte à nettoyer.

        Returns:
            Texte nettoyé, sûr pour la saisie.
        """
        import unicodedata

        # Supprimer les caractères de contrôle sauf \n, \t, \r
        sanitized: list[str] = []
        for char in text:
            cat = unicodedata.category(char)
            if cat.startswith("C") and char not in ("\n", "\t", "\r"):
                continue
            sanitized.append(char)
        return "".join(sanitized)

    def _get_default_screenshot_path(self) -> str:
        """Génère un chemin par défaut pour les captures d'écran.

        Format: ~/Nuru_Workspace/screenshots/YYYY-MM-DD_HHMMSS.png

        Returns:
            Chemin absolu du fichier de capture.
        """
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        return os.path.join(SCREENSHOT_DIR, f"screenshot_{timestamp}.png")

    @staticmethod
    def _detect_financial_keywords(url: str, title: str | None) -> bool:
        """Détecte si une URL ou un titre contient des mots-clés financiers.

        Compare l'URL (lowercase) et le titre (lowercase) contre un
        ensemble de mots-clés financiers connus.

        Args:
            url: URL à analyser.
            title: Titre de la page (peut être None).

        Returns:
            True si des mots-clés financiers sont détectés.
        """
        url_lower = url.lower()
        for keyword in FINANCIAL_KEYWORDS:
            if keyword in url_lower:
                return True

        if title:
            title_lower = title.lower()
            for keyword in FINANCIAL_KEYWORDS:
                if keyword in title_lower:
                    return True

        return False

    def _check_financial_site(self, url: str) -> BrowserResult | None:
        """Vérifie si un site est un site financier non approuvé.

        Si l'URL correspond à un site financier et que le site n'est
        pas dans la liste des sites approuvés, retourne une erreur.

        Args:
            url: URL à vérifier.

        Returns:
            None si le site est sûr/approuvé, BrowserResult d'erreur sinon.
        """
        # Obtenir le titre pour l'analyse
        title = None
        try:
            if self._page and not self._page.is_closed():
                title = self._page.title()
        except Exception:
            pass

        if not self._detect_financial_keywords(url, title):
            return None

        # Extraire le domaine pour vérifier l'approbation
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
        except Exception:
            domain = url.lower()

        with self._approval_lock:
            # Vérifier si le domaine ou l'URL complète est approuvé
            for approved in self._approved_financial_sites:
                if approved in domain or domain in approved:
                    return None

        return BrowserResult(
            success=False,
            message="Site financier bloqué par sécurité",
            error=(
                f"Le site '{url}' a été détecté comme site financier "
                f"et n'est pas dans la liste des sites approuvés. "
                f"Utilisez approve_financial_site() pour l'autoriser."
            ),
        )

    # ── Navigation ──

    def navigate(
        self,
        url: str,
        timeout: int = DEFAULT_TIMEOUT_MS,
        wait_until: str = "load",
    ) -> NavigateResult:
        """Navigue vers une URL et attend le chargement de la page.

        Valide la sécurité, charge la page, met à jour l'historique.

        Args:
            url: URL complète (avec https://) à charger.
            timeout: Timeout en millisecondes (défaut: 30000).
            wait_until: Condition d'attente ('load', 'domcontentloaded',
                       'networkidle', 'commit').

        Returns:
            NavigateResult avec les informations de la page chargée.
        """
        start = time.time()
        bus = EventBus()

        # Validation du navigateur
        init_check = self._ensure_initialized()
        if init_check is not None:
            return NavigateResult(
                url=url,
                title="",
                status_code=0,
                final_url="",
                load_time_ms=(time.time() - start) * 1000,
            )

        # Ajouter https:// si nécessaire
        if not url.startswith(("http://", "https://", "file://", "data:")):
            url = "https://" + url

        # Vérification sécurité site financier
        security_check = self._check_financial_site(url)
        if security_check is not None:
            bus.emit_sync("browser:error", {
                "action": "navigate",
                "url": url,
                "error": security_check.error,
            })
            return NavigateResult(
                url=url,
                title="",
                status_code=0,
                final_url="",
                load_time_ms=(time.time() - start) * 1000,
            )

        try:
            # Naviguer
            response = self._page.goto(url, timeout=timeout, wait_until=wait_until)

            # Récupérer les informations de la page
            final_url = self._page.url
            title = self._page.title()
            status_code = response.status if response else 0
            self._current_url = final_url

            duration = (time.time() - start) * 1000

            # Ajouter à l'historique
            history_entry = {
                "url": url,
                "final_url": final_url,
                "title": title,
                "status_code": status_code,
                "timestamp": time.time(),
                "load_time_ms": duration,
            }
            with self._history_lock:
                self._navigation_history.append(history_entry)
                if len(self._navigation_history) > MAX_NAVIGATION_HISTORY:
                    self._navigation_history.pop(0)

            bus.emit_sync("browser:navigate", {
                "url": url,
                "final_url": final_url,
                "title": title,
                "status_code": status_code,
                "duration_ms": duration,
            })

            logger.info(
                "Navigation: %s -> %s (status=%d, %.0fms)",
                url, final_url, status_code, duration,
            )

            return NavigateResult(
                url=url,
                title=title,
                status_code=status_code,
                final_url=final_url,
                load_time_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("browser:error", {
                "action": "navigate",
                "url": url,
                "error": str(e),
            })
            logger.error("Erreur navigation vers %s: %s", url, e)
            return NavigateResult(
                url=url,
                title="",
                status_code=0,
                final_url="",
                load_time_ms=duration,
            )

    def go_back(self) -> NavigateResult | None:
        """Recule dans l'historique de navigation.

        Returns:
            NavigateResult si la navigation a eu lieu, None sinon.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return None

        try:
            self._page.go_back(timeout=DEFAULT_TIMEOUT_MS)
            duration = (time.time() - start) * 1000

            bus = EventBus()
            bus.emit_sync("browser:navigate", {
                "action": "back",
                "url": self._page.url,
                "title": self._page.title(),
                "duration_ms": duration,
            })

            return NavigateResult(
                url=self._page.url,
                title=self._page.title(),
                status_code=200,
                final_url=self._page.url,
                load_time_ms=duration,
            )
        except Exception as e:
            logger.error("Erreur go_back: %s", e)
            return None

    def go_forward(self) -> NavigateResult | None:
        """Avance dans l'historique de navigation.

        Returns:
            NavigateResult si la navigation a eu lieu, None sinon.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return None

        try:
            self._page.go_forward(timeout=DEFAULT_TIMEOUT_MS)
            duration = (time.time() - start) * 1000

            bus = EventBus()
            bus.emit_sync("browser:navigate", {
                "action": "forward",
                "url": self._page.url,
                "title": self._page.title(),
                "duration_ms": duration,
            })

            return NavigateResult(
                url=self._page.url,
                title=self._page.title(),
                status_code=200,
                final_url=self._page.url,
                load_time_ms=duration,
            )
        except Exception as e:
            logger.error("Erreur go_forward: %s", e)
            return None

    def reload(self) -> NavigateResult:
        """Recharge la page courante.

        Returns:
            NavigateResult avec les informations de la page rechargée.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return NavigateResult(
                url=self._current_url,
                title="",
                status_code=0,
                final_url="",
                load_time_ms=(time.time() - start) * 1000,
            )

        try:
            self._page.reload(timeout=DEFAULT_TIMEOUT_MS)
            duration = (time.time() - start) * 1000

            bus = EventBus()
            bus.emit_sync("browser:navigate", {
                "action": "reload",
                "url": self._page.url,
                "title": self._page.title(),
                "duration_ms": duration,
            })

            return NavigateResult(
                url=self._page.url,
                title=self._page.title(),
                status_code=200,
                final_url=self._page.url,
                load_time_ms=duration,
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            logger.error("Erreur reload: %s", e)
            return NavigateResult(
                url=self._current_url,
                title="",
                status_code=0,
                final_url="",
                load_time_ms=duration,
            )

    def get_current_url(self) -> str:
        """Retourne l'URL courante de la page active.

        Returns:
            URL courante, ou chaîne vide si non disponible.
        """
        init_check = self._ensure_initialized()
        if init_check is not None:
            return ""

        try:
            if self._page and not self._page.is_closed():
                return self._page.url
        except Exception:
            pass
        return self._current_url

    def get_page_title(self) -> str:
        """Retourne le titre de la page active.

        Returns:
            Titre de la page, ou chaîne vide si non disponible.
        """
        init_check = self._ensure_initialized()
        if init_check is not None:
            return ""

        try:
            if self._page and not self._page.is_closed():
                return self._page.title()
        except Exception:
            pass
        return ""

    # ── Interaction ──

    def click(
        self,
        selector: str,
        timeout: int = DEFAULT_WAIT_TIMEOUT,
        force: bool = False,
    ) -> BrowserResult:
        """Clique sur un élément identifié par un sélecteur.

        Attend que le sélecteur soit visible avant de cliquer.

        Args:
            selector: Sélecteur CSS, XPath, ou texte de l'élément.
            timeout: Timeout en millisecondes (défaut: 10000).
            force: Forcer le clic même si l'élément n'est pas visible.

        Returns:
            BrowserResult indiquant le succès ou l'échec du clic.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        try:
            locator = self._get_playwright_locator(self._page, selector)

            if not force:
                locator.wait_for(state="visible", timeout=timeout)
                locator.click(timeout=timeout)
            else:
                locator.click(force=True, timeout=timeout)

            duration = (time.time() - start) * 1000

            bus = EventBus()
            bus.emit_sync("browser:click", {
                "selector": selector,
                "force": force,
                "duration_ms": duration,
            })

            return BrowserResult(
                success=True,
                message=f"Clic sur '{selector}' réussi",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            bus = EventBus()
            bus.emit_sync("browser:error", {
                "action": "click",
                "selector": selector,
                "error": str(e),
            })
            return BrowserResult(
                success=False,
                message=f"Échec du clic sur '{selector}'",
                error=str(e),
                duration_ms=duration,
            )

    def type(
        self,
        selector: str,
        text: str,
        delay: int = 50,
        clear_first: bool = True,
    ) -> BrowserResult:
        """Saisit du texte dans un champ de formulaire.

        Efface d'abord le champ si clear_first=True, puis tape le
        texte caractère par caractère avec le délai spécifié.

        Args:
            selector: Sélecteur du champ de saisie.
            text: Texte à saisir.
            delay: Délai entre chaque caractère en ms (défaut: 50).
            clear_first: Effacer le champ avant de saisir (défaut: True).

        Returns:
            BrowserResult indiquant le succès ou l'échec.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        try:
            locator = self._get_playwright_locator(self._page, selector)
            locator.wait_for(state="visible", timeout=DEFAULT_WAIT_TIMEOUT)

            if clear_first:
                locator.fill("")
                # Petit délai pour s'assurer que le champ est vidé
                time.sleep(0.05)

            # Saisir le texte nettoyé
            safe_text = self._sanitize_input(text)
            locator.fill(safe_text)

            duration = (time.time() - start) * 1000

            bus = EventBus()
            bus.emit_sync("browser:type", {
                "selector": selector,
                "length": len(safe_text),
                "clear_first": clear_first,
                "duration_ms": duration,
            })

            return BrowserResult(
                success=True,
                message=f"Saisie de {len(safe_text)} caractères dans '{selector}'",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            bus = EventBus()
            bus.emit_sync("browser:error", {
                "action": "type",
                "selector": selector,
                "error": str(e),
            })
            return BrowserResult(
                success=False,
                message=f"Échec de la saisie dans '{selector}'",
                error=str(e),
                duration_ms=duration,
            )

    def press_key(
        self,
        key: str,
        selector: str | None = None,
    ) -> BrowserResult:
        """Presse une touche du clavier.

        Si un sélecteur est fourni, focus d'abord l'élément.

        Args:
            key: Touche à presser ('Enter', 'Tab', 'Escape', 'ArrowDown', etc.).
            selector: Sélecteur de l'élément à focuser avant (optionnel).

        Returns:
            BrowserResult indiquant le succès ou l'échec.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        try:
            if selector:
                locator = self._get_playwright_locator(self._page, selector)
                locator.wait_for(state="visible", timeout=DEFAULT_WAIT_TIMEOUT)
                locator.press(key)
            else:
                self._page.keyboard.press(key)

            duration = (time.time() - start) * 1000

            return BrowserResult(
                success=True,
                message=f"Touche '{key}' pressée",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message=f"Échec de la pression de touche '{key}'",
                error=str(e),
                duration_ms=duration,
            )

    def select_option(
        self,
        selector: str,
        value: str | list[str],
    ) -> BrowserResult:
        """Sélectionne une ou plusieurs options dans un menu <select>.

        Args:
            selector: Sélecteur de l'élément <select>.
            value: Valeur(s) à sélectionner.

        Returns:
            BrowserResult indiquant le succès ou l'échec.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        try:
            locator = self._get_playwright_locator(self._page, selector)
            locator.wait_for(state="visible", timeout=DEFAULT_WAIT_TIMEOUT)

            if isinstance(value, str):
                locator.select_option(value)
            else:
                locator.select_option(value)

            duration = (time.time() - start) * 1000

            return BrowserResult(
                success=True,
                message=f"Option(s) sélectionnée(s) dans '{selector}'",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message=f"Échec de la sélection dans '{selector}'",
                error=str(e),
                duration_ms=duration,
            )

    def check(self, selector: str) -> BrowserResult:
        """Coche une case à cocher (checkbox) ou bouton radio.

        Args:
            selector: Sélecteur de l'élément à cocher.

        Returns:
            BrowserResult indiquant le succès ou l'échec.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        try:
            locator = self._get_playwright_locator(self._page, selector)
            locator.wait_for(state="visible", timeout=DEFAULT_WAIT_TIMEOUT)

            if locator.is_checked():
                return BrowserResult(
                    success=True,
                    message=f"L'élément '{selector}' est déjà coché",
                    duration_ms=(time.time() - start) * 1000,
                )

            locator.check()
            duration = (time.time() - start) * 1000

            return BrowserResult(
                success=True,
                message=f"Case cochée: '{selector}'",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message=f"Échec du cochage de '{selector}'",
                error=str(e),
                duration_ms=duration,
            )

    def uncheck(self, selector: str) -> BrowserResult:
        """Décoche une case à cocher (checkbox).

        Args:
            selector: Sélecteur de la case à décocher.

        Returns:
            BrowserResult indiquant le succès ou l'échec.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        try:
            locator = self._get_playwright_locator(self._page, selector)
            locator.wait_for(state="visible", timeout=DEFAULT_WAIT_TIMEOUT)

            if not locator.is_checked():
                return BrowserResult(
                    success=True,
                    message=f"L'élément '{selector}' est déjà décoché",
                    duration_ms=(time.time() - start) * 1000,
                )

            locator.uncheck()
            duration = (time.time() - start) * 1000

            return BrowserResult(
                success=True,
                message=f"Case décochée: '{selector}'",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message=f"Échec du décochage de '{selector}'",
                error=str(e),
                duration_ms=duration,
            )

    def hover(self, selector: str) -> BrowserResult:
        """Survole un élément avec la souris.

        Args:
            selector: Sélecteur de l'élément à survoler.

        Returns:
            BrowserResult indiquant le succès ou l'échec.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        try:
            locator = self._get_playwright_locator(self._page, selector)
            locator.wait_for(state="visible", timeout=DEFAULT_WAIT_TIMEOUT)
            locator.hover()

            duration = (time.time() - start) * 1000

            return BrowserResult(
                success=True,
                message=f"Survol de '{selector}' réussi",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message=f"Échec du survol de '{selector}'",
                error=str(e),
                duration_ms=duration,
            )

    def scroll_to(self, selector: str) -> BrowserResult:
        """Défile la page jusqu'à ce qu'un élément soit visible.

        Args:
            selector: Sélecteur de l'élément vers lequel défiler.

        Returns:
            BrowserResult indiquant le succès ou l'échec.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        try:
            locator = self._get_playwright_locator(self._page, selector)
            locator.scroll_into_view_if_needed()

            duration = (time.time() - start) * 1000

            return BrowserResult(
                success=True,
                message=f"Page défilée vers '{selector}'",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message=f"Échec du défilement vers '{selector}'",
                error=str(e),
                duration_ms=duration,
            )

    def scroll_by(self, delta_x: int, delta_y: int) -> BrowserResult:
        """Défile la page d'un décalage en pixels.

        Args:
            delta_x: Décalage horizontal en pixels (négatif = gauche).
            delta_y: Décalage vertical en pixels (négatif = haut).

        Returns:
            BrowserResult indiquant le succès ou l'échec.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        try:
            self._page.evaluate(
                f"window.scrollBy({delta_x}, {delta_y})"
            )

            duration = (time.time() - start) * 1000

            direction = "bas" if delta_y > 0 else "haut" if delta_y < 0 else ""
            return BrowserResult(
                success=True,
                message=f"Page défilée vers le {direction} ({delta_y}px)",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message="Échec du défilement",
                error=str(e),
                duration_ms=duration,
            )

    # ── Extraction ──

    def get_text(
        self,
        selector: str,
        timeout: int = 5000,
    ) -> BrowserResult:
        """Extrait le texte contenu d'un élément.

        Args:
            selector: Sélecteur de l'élément.
            timeout: Timeout en ms pour attendre l'élément.

        Returns:
            BrowserResult avec data=texte de l'élément.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        try:
            locator = self._get_playwright_locator(self._page, selector)
            locator.wait_for(state="attached", timeout=timeout)
            text = locator.text_content()

            duration = (time.time() - start) * 1000

            return BrowserResult(
                success=True,
                message=f"Texte extrait de '{selector}'",
                data=text or "",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message=f"Échec de l'extraction de texte de '{selector}'",
                error=str(e),
                duration_ms=duration,
            )

    def get_attribute(
        self,
        selector: str,
        attr: str,
    ) -> BrowserResult:
        """Extrait un attribut d'un élément.

        Args:
            selector: Sélecteur de l'élément.
            attr: Nom de l'attribut ('href', 'src', 'alt', 'class', etc.).

        Returns:
            BrowserResult avec data=valeur de l'attribut.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        try:
            locator = self._get_playwright_locator(self._page, selector)
            locator.wait_for(state="attached", timeout=DEFAULT_WAIT_TIMEOUT)
            value = locator.get_attribute(attr)

            duration = (time.time() - start) * 1000

            return BrowserResult(
                success=True,
                message=f"Attribut '{attr}' extrait de '{selector}'",
                data=value or "",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message=f"Échec de l'extraction de l'attribut '{attr}'",
                error=str(e),
                duration_ms=duration,
            )

    def get_html(
        self,
        selector: str | None = None,
    ) -> BrowserResult:
        """Extrait le HTML d'un élément ou de la page complète.

        Args:
            selector: Sélecteur de l'élément (None = page complète).

        Returns:
            BrowserResult avec data=HTML extrait.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        try:
            if selector is None:
                # HTML complet de la page
                html = self._page.content()
                msg = "HTML complet de la page extrait"
            else:
                locator = self._get_playwright_locator(self._page, selector)
                locator.wait_for(state="attached", timeout=DEFAULT_WAIT_TIMEOUT)
                html = locator.inner_html()
                msg = f"HTML de '{selector}' extrait"

            duration = (time.time() - start) * 1000

            return BrowserResult(
                success=True,
                message=msg,
                data=html,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message="Échec de l'extraction HTML",
                error=str(e),
                duration_ms=duration,
            )

    def extract_data(
        self,
        selectors: dict[str, str],
    ) -> dict[str, str]:
        """Extraction structurée de données via des sélecteurs multiples.

        Utile pour le scraping : fournit un dictionnaire {nom: sélecteur}
        et retourne un dictionnaire {nom: texte_extrait}.

        Args:
            selectors: Dictionnaire {nom: sélecteur}.
                     Ex: {"title": "h1", "price": ".price", "desc": ".description"}

        Returns:
            Dictionnaire {nom: texte_extrait} des données collectées.
        """
        result: dict[str, str] = {}
        for name, selector in selectors.items():
            r = self.get_text(selector)
            result[name] = r.data if r.success else ""
        return result

    def get_all_links(self) -> list[dict[str, str]]:
        """Extrait tous les liens (anchor tags) de la page courante.

        Returns:
            Liste de dicts {href, text} pour chaque lien trouvé.
        """
        init_check = self._ensure_initialized()
        if init_check is not None:
            return []

        try:
            links: list[dict[str, str]] = self._page.evaluate(
                """() => {
                    const anchors = document.querySelectorAll('a[href]');
                    return Array.from(anchors).map(a => ({
                        href: a.href,
                        text: a.textContent.trim().substring(0, 500)
                    }));
                }"""
            )
            return links
        except Exception as e:
            logger.warning("Erreur extraction liens: %s", e)
            return []

    def get_images(self) -> list[dict[str, str]]:
        """Extrait toutes les images de la page courante.

        Returns:
            Liste de dicts {src, alt, width, height} pour chaque image.
        """
        init_check = self._ensure_initialized()
        if init_check is not None:
            return []

        try:
            images: list[dict[str, str]] = self._page.evaluate(
                """() => {
                    const imgs = document.querySelectorAll('img[src]');
                    return Array.from(imgs).map(img => ({
                        src: img.src,
                        alt: img.alt || '',
                        width: img.naturalWidth ? String(img.naturalWidth) : '',
                        height: img.naturalHeight ? String(img.naturalHeight) : '',
                    }));
                }"""
            )
            return images
        except Exception as e:
            logger.warning("Erreur extraction images: %s", e)
            return []

    def get_forms(self) -> list[dict]:
        """Détecte tous les formulaires et leurs champs sur la page.

        Returns:
            Liste de dicts représentant chaque formulaire avec
            ses champs (name, type, selector, label).
        """
        init_check = self._ensure_initialized()
        if init_check is not None:
            return []

        try:
            forms: list[dict] = self._page.evaluate(
                """() => {
                    const forms = document.querySelectorAll('form');
                    return Array.from(forms).map((form, fi) => {
                        const inputs = form.querySelectorAll('input, select, textarea, button');
                        return {
                            index: fi,
                            action: form.action || '',
                            method: form.method || 'get',
                            fields: Array.from(inputs).map(input => ({
                                name: input.name || '',
                                type: input.type || input.tagName.toLowerCase(),
                                id: input.id || '',
                                placeholder: input.placeholder || '',
                                label: (
                                    document.querySelector(`label[for="${input.id}"]`)
                                    ? document.querySelector(`label[for="${input.id}"]`).textContent.trim()
                                    : ''
                                ),
                                required: input.required || false,
                                disabled: input.disabled || false,
                                value: input.value || '',
                                selector: input.id
                                    ? `#${input.id}`
                                    : input.name
                                    ? `[name="${input.name}"]`
                                    : `${input.tagName.toLowerCase()}[type="${input.type || 'text'}"]`
                            }))
                        };
                    });
                }"""
            )
            return forms
        except Exception as e:
            logger.warning("Erreur extraction formulaires: %s", e)
            return []

    # ── Screenshot ──

    def screenshot(
        self,
        full_page: bool = False,
        path: str | None = None,
        selector: str | None = None,
    ) -> BrowserResult:
        """Capture une capture d'écran de la page ou d'un élément.

        Si path=None, génère un chemin dans ~/Nuru_Workspace/screenshots/.
        Si selector est fourni, ne capture que cet élément.

        Args:
            full_page: Capturer la page entière (scroll complet) si True.
            path: Chemin de sauvegarde (None = généré automatiquement).
            selector: Sélecteur d'élément à capturer uniquement.

        Returns:
            BrowserResult avec data=chemin du fichier de capture.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        # Déterminer le chemin de sauvegarde
        if path is None:
            path = self._get_default_screenshot_path()
        else:
            path = os.path.expanduser(path)
            # Créer le répertoire parent si nécessaire
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)

        try:
            if selector is not None:
                # Capture d'un élément spécifique
                locator = self._get_playwright_locator(self._page, selector)
                locator.wait_for(state="visible", timeout=DEFAULT_WAIT_TIMEOUT)
                locator.screenshot(path=path)
                msg = f"Capture d'écran de '{selector}'"
            else:
                # Capture de la page entière
                self._page.screenshot(path=path, full_page=full_page)
                msg = f"Capture d'écran de la page (full_page={full_page})"

            duration = (time.time() - start) * 1000

            bus = EventBus()
            bus.emit_sync("browser:screenshot", {
                "path": path,
                "full_page": full_page,
                "selector": selector,
                "duration_ms": duration,
            })

            logger.info("Capture d'écran: %s (%.0fms)", path, duration)

            return BrowserResult(
                success=True,
                message=msg,
                data=path,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message="Échec de la capture d'écran",
                error=str(e),
                duration_ms=duration,
            )

    # ── PDF ──

    def pdf(self, path: str | None = None) -> BrowserResult:
        """Génère un PDF de la page courante.

        Args:
            path: Chemin de sauvegarde (None = généré automatiquement).

        Returns:
            BrowserResult avec data=chemin du fichier PDF.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        if path is None:
            os.makedirs(SCREENSHOT_DIR, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            path = os.path.join(SCREENSHOT_DIR, f"page_{timestamp}.pdf")
        else:
            path = os.path.expanduser(path)
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)

        try:
            self._page.pdf(path=path)
            duration = (time.time() - start) * 1000

            logger.info("PDF généré: %s (%.0fms)", path, duration)

            return BrowserResult(
                success=True,
                message=f"PDF généré avec succès",
                data=path,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message="Échec de la génération PDF",
                error=str(e),
                duration_ms=duration,
            )

    # ── Form Filling ──

    def fill_form(
        self,
        fields: list[FormField],
        submit: bool = False,
    ) -> BrowserResult:
        """Remplit un formulaire avec des champs multiples.

        Supporte les types de champs : text, checkbox, select, radio, file.

        Args:
            fields: Liste de FormField à remplir.
            submit: Si True, clique sur le bouton submit après.

        Returns:
            BrowserResult indiquant le succès ou l'échec global.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        errors: list[str] = []
        filled_count = 0

        for i, field in enumerate(fields):
            try:
                locator = self._get_playwright_locator(self._page, field.selector)
                locator.wait_for(state="visible", timeout=DEFAULT_WAIT_TIMEOUT)

                field_type = field.type.lower()

                if field_type == "text" or field_type == "textarea":
                    value = str(field.value) if field.value is not None else ""
                    safe_value = self._sanitize_input(value)
                    locator.fill(safe_value)
                    filled_count += 1

                elif field_type == "checkbox":
                    should_check = bool(field.value)
                    is_checked = locator.is_checked()
                    if should_check and not is_checked:
                        locator.check()
                    elif not should_check and is_checked:
                        locator.uncheck()
                    filled_count += 1

                elif field_type == "select":
                    if isinstance(field.value, list):
                        locator.select_option(field.value)
                    else:
                        locator.select_option(str(field.value) if field.value is not None else "")
                    filled_count += 1

                elif field_type == "radio":
                    value = str(field.value) if field.value is not None else ""
                    locator.check()
                    filled_count += 1

                elif field_type == "file":
                    value = str(field.value) if field.value is not None else ""
                    if value:
                        locator.set_input_files(value)
                        filled_count += 1
                    else:
                        errors.append(f"Champ[{i}] file: chemin vide")

                else:
                    # Par défaut, traiter comme text
                    value = str(field.value) if field.value is not None else ""
                    safe_value = self._sanitize_input(value)
                    locator.fill(safe_value)
                    filled_count += 1

            except Exception as e:
                errors.append(f"Champ[{i}] '{field.selector}': {e}")

        # Soumettre si demandé
        if submit and not errors:
            try:
                submit_btn = self._page.locator(
                    "button[type='submit'], input[type='submit'], "
                    "button:has-text('Envoyer'), button:has-text('Submit'), "
                    "button:has-text('Valider'), button:has-text('Continuer')"
                )
                if submit_btn.count() > 0:
                    submit_btn.first.click(timeout=DEFAULT_WAIT_TIMEOUT)
                    filled_count += 1
                else:
                    # Essayer de presser Enter dans le dernier champ
                    if fields:
                        last_locator = self._get_playwright_locator(
                            self._page, fields[-1].selector
                        )
                        last_locator.press("Enter")
            except Exception as e:
                errors.append(f"Submit: {e}")

        duration = (time.time() - start) * 1000

        bus = EventBus()
        bus.emit_sync("browser:form_fill", {
            "fields_count": len(fields),
            "filled": filled_count,
            "submit": submit,
            "errors": errors,
            "duration_ms": duration,
        })

        if errors:
            return BrowserResult(
                success=False,
                message=f"Formulaire rempli avec {len(errors)} erreur(s)",
                data={
                    "filled_count": filled_count,
                    "total_fields": len(fields),
                },
                error="; ".join(errors),
                duration_ms=duration,
            )

        return BrowserResult(
            success=True,
            message=(
                f"Formulaire rempli avec succès "
                f"({filled_count}/{len(fields)} champs)"
            ),
            data={
                "filled_count": filled_count,
                "total_fields": len(fields),
            },
            duration_ms=duration,
        )

    # ── Wait / Utility ──

    def wait(
        self,
        selector: str | None = None,
        timeout: int = DEFAULT_WAIT_TIMEOUT,
        state: str = "visible",
    ) -> BrowserResult:
        """Attend qu'un élément atteigne un état spécifique.

        Args:
            selector: Sélecteur à attendre (None = attend le timeout).
            timeout: Timeout en ms (défaut: 10000).
            state: État attendu ('visible', 'hidden', 'attached', 'detached').

        Returns:
            BrowserResult indiquant le succès ou le timeout.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        if selector is None:
            # Attente passive
            time.sleep(timeout / 1000.0)
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=True,
                message=f"Attente passive de {timeout}ms terminée",
                duration_ms=duration,
            )

        try:
            locator = self._get_playwright_locator(self._page, selector)
            locator.wait_for(state=state, timeout=timeout)

            duration = (time.time() - start) * 1000

            return BrowserResult(
                success=True,
                message=(
                    f"Élément '{selector}' atteint l'état '{state}'"
                ),
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message=(
                    f"État '{state}' non atteint pour '{selector}'"
                ),
                error=str(e),
                duration_ms=duration,
            )

    def wait_for_navigation(
        self,
        timeout: int = DEFAULT_TIMEOUT_MS,
    ) -> BrowserResult:
        """Attend que la page termine une navigation.

        Utile après un clic sur un lien ou la soumission d'un formulaire.

        Args:
            timeout: Timeout en ms (défaut: 30000).

        Returns:
            BrowserResult indiquant le succès ou le timeout.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        try:
            self._page.wait_for_load_state("networkidle", timeout=timeout)
            duration = (time.time() - start) * 1000

            return BrowserResult(
                success=True,
                message="Navigation terminée (networkidle)",
                data={
                    "url": self._page.url,
                    "title": self._page.title(),
                },
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message="Timeout ou échec de la navigation",
                error=str(e),
                duration_ms=duration,
            )

    def wait_for_load_state(
        self,
        state: str = "networkidle",
    ) -> BrowserResult:
        """Attend un état de chargement spécifique de la page.

        Args:
            state: État attendu ('load', 'domcontentloaded', 'networkidle').

        Returns:
            BrowserResult indiquant le succès ou le timeout.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        valid_states = {"load", "domcontentloaded", "networkidle"}
        if state not in valid_states:
            return BrowserResult(
                success=False,
                message=f"État invalide: '{state}'",
                error=(
                    f"État doit être l'un de: {', '.join(sorted(valid_states))}"
                ),
                duration_ms=(time.time() - start) * 1000,
            )

        try:
            self._page.wait_for_load_state(state, timeout=DEFAULT_TIMEOUT_MS)
            duration = (time.time() - start) * 1000

            return BrowserResult(
                success=True,
                message=f"État de chargement '{state}' atteint",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message=f"État '{state}' non atteint",
                error=str(e),
                duration_ms=duration,
            )

    def execute_script(self, script: str) -> BrowserResult:
        """Exécute du JavaScript dans le contexte de la page.

        La validation de sécurité bloque les scripts accédant à des
        API sensibles (crypto.subtle, require('child_process'), etc.).

        Args:
            script: Code JavaScript à exécuter.

        Returns:
            BrowserResult avec data=résultat de l'exécution JS.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        # Validation de sécurité (côté Python)
        sensitive_patterns = [
            "crypto.subtle",
            "require('child_process')",
            "require(\"child_process\")",
            "process.binding",
            "process.mainModule",
            "import('child_process')",
            "import(\"child_process\")",
            "eval(",
            "Function(",
            "new Function",
            "document.write",
            "document.open",
            "XMLHttpRequest",
            "fetch(",
            "WebSocket(",
            "localStorage.clear",
            "indexedDB.deleteDatabase",
            "navigator.sendBeacon",
        ]

        script_lower = script.lower()
        for pattern in sensitive_patterns:
            if pattern.lower() in script_lower:
                duration = (time.time() - start) * 1000
                return BrowserResult(
                    success=False,
                    message="Script bloqué par sécurité",
                    error=(
                        f"Le script contient un motif sensible: '{pattern}'. "
                        f"Cette API est bloquée pour des raisons de sécurité."
                    ),
                    duration_ms=duration,
                )

        try:
            result = self._page.evaluate(script)
            duration = (time.time() - start) * 1000

            bus = EventBus()
            bus.emit_sync("browser:script", {
                "script_length": len(script),
                "duration_ms": duration,
            })

            return BrowserResult(
                success=True,
                message="Script exécuté avec succès",
                data=result,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message="Échec de l'exécution du script",
                error=str(e),
                duration_ms=duration,
            )

    def get_navigation_history(self) -> list[dict]:
        """Retourne l'historique complet des URLs visitées.

        Returns:
            Liste de dicts avec url, final_url, title, status_code,
            timestamp, load_time_ms pour chaque navigation.
        """
        with self._history_lock:
            return list(self._navigation_history)

    def clear_navigation_history(self) -> None:
        """Efface l'historique de navigation."""
        with self._history_lock:
            self._navigation_history.clear()

    # ── Cookie Management ──

    def get_cookies(self) -> list[dict]:
        """Retourne tous les cookies du contexte de navigation.

        Returns:
            Liste de dicts représentant les cookies.
        """
        init_check = self._ensure_initialized()
        if init_check is not None:
            return []

        try:
            if self._context:
                return self._context.cookies()
            return []
        except Exception as e:
            logger.warning("Erreur récupération cookies: %s", e)
            return []

    def set_cookie(
        self,
        name: str,
        value: str,
        url: str | None = None,
        domain: str | None = None,
        path: str | None = None,
        secure: bool = False,
        http_only: bool = False,
        same_site: str | None = None,
    ) -> BrowserResult:
        """Définit un cookie dans le contexte de navigation.

        Args:
            name: Nom du cookie.
            value: Valeur du cookie.
            url: URL associée au cookie.
            domain: Domaine du cookie.
            path: Chemin du cookie ('/' par défaut).
            secure: Cookie sécurisé (HTTPS seulement).
            http_only: Cookie inaccessible via JavaScript.
            same_site: Politique SameSite ('Strict', 'Lax', 'None').

        Returns:
            BrowserResult indiquant le succès ou l'échec.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        try:
            cookie: dict[str, Any] = {
                "name": name,
                "value": value,
                "secure": secure,
                "http_only": http_only,
            }

            if url is not None:
                cookie["url"] = url
            if domain is not None:
                cookie["domain"] = domain
            if path is not None:
                cookie["path"] = path
            else:
                cookie["path"] = "/"
            if same_site is not None:
                cookie["same_site"] = same_site

            if self._context:
                self._context.add_cookies([cookie])

            duration = (time.time() - start) * 1000

            return BrowserResult(
                success=True,
                message=f"Cookie '{name}' défini",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message=f"Échec de la définition du cookie '{name}'",
                error=str(e),
                duration_ms=duration,
            )

    def delete_cookie(self, name: str) -> BrowserResult:
        """Supprime un cookie par son nom.

        Note: Playwright ne supporte pas la suppression directe d'un
        cookie par nom. On recrée un cookie vide avec la même date
        d'expiration passée via le contexte.

        Args:
            name: Nom du cookie à supprimer.

        Returns:
            BrowserResult indiquant le succès ou l'échec.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        try:
            if self._context:
                # Récupérer tous les cookies
                all_cookies = self._context.cookies()
                # Filtrer pour garder ceux qui ne sont pas à supprimer
                remaining = [c for c in all_cookies if c.get("name") != name]
                # Effacer tous les cookies
                self._context.clear_cookies()
                # Remettre les cookies restants
                if remaining:
                    self._context.add_cookies(remaining)

            duration = (time.time() - start) * 1000

            return BrowserResult(
                success=True,
                message=f"Cookie '{name}' supprimé",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message=f"Échec de la suppression du cookie '{name}'",
                error=str(e),
                duration_ms=duration,
            )

    def clear_cookies(self) -> BrowserResult:
        """Supprime tous les cookies du contexte de navigation.

        Returns:
            BrowserResult indiquant le succès ou l'échec.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        try:
            if self._context:
                self._context.clear_cookies()

            duration = (time.time() - start) * 1000

            return BrowserResult(
                success=True,
                message="Tous les cookies ont été supprimés",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message="Échec de la suppression des cookies",
                error=str(e),
                duration_ms=duration,
            )

    # ── Financial Site Approval ──

    def approve_financial_site(self, site: str) -> BrowserResult:
        """Ajoute un site financier à la liste des sites approuvés.

        Une fois approuvé, les navigations vers ce site ne seront
        plus bloquées par la sécurité financière.

        Args:
            site: Domaine ou URL partielle à approuver.

        Returns:
            BrowserResult indiquant que le site a été approuvé.
        """
        with self._approval_lock:
            self._approved_financial_sites.add(site.lower())

        logger.info("Site financier approuvé: %s", site)

        return BrowserResult(
            success=True,
            message=f"Site financier '{site}' approuvé",
            data={"approved_sites": list(self._approved_financial_sites)},
        )

    def is_financial_site_approved(self, url: str) -> bool:
        """Vérifie si un site financier est dans la liste des approuvés.

        Args:
            url: URL ou domaine à vérifier.

        Returns:
            True si le site est approuvé, False sinon.
        """
        from urllib.parse import urlparse

        url_lower = url.lower()

        try:
            parsed = urlparse(url_lower)
            domain = parsed.netloc or url_lower
        except Exception:
            domain = url_lower

        with self._approval_lock:
            for approved in self._approved_financial_sites:
                if approved in domain or domain in approved:
                    return True

        return False

    def _scroll_to_top(self) -> BrowserResult:
        """Défile la page tout en haut.

        Returns:
            BrowserResult indiquant le succès ou l'échec.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        try:
            self._page.evaluate("window.scrollTo(0, 0)")
            duration = (time.time() - start) * 1000

            return BrowserResult(
                success=True,
                message="Page défilée tout en haut",
                duration_ms=duration,
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message="Échec du défilement en haut",
                error=str(e),
                duration_ms=duration,
            )

    def _scroll_to_bottom(self) -> BrowserResult:
        """Défile la page tout en bas.

        Returns:
            BrowserResult indiquant le succès ou l'échec.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        try:
            self._page.evaluate(
                "window.scrollTo(0, document.body.scrollHeight)"
            )
            duration = (time.time() - start) * 1000

            return BrowserResult(
                success=True,
                message="Page défilée tout en bas",
                duration_ms=duration,
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message="Échec du défilement en bas",
                error=str(e),
                duration_ms=duration,
            )

    # ── Context Management ──

    def create_new_context(
        self,
        user_data_dir: str | None = None,
    ) -> BrowserResult:
        """Crée un nouveau contexte de navigation (nouvelle session).

        Note: Le nouveau contexte devient le contexte actif.
        L'ancien contexte et sa page sont conservés.

        Args:
            user_data_dir: Répertoire de données utilisateur optionnel.

        Returns:
            BrowserResult indiquant le succès ou l'échec.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        try:
            if self._browser is None:
                return BrowserResult(
                    success=False,
                    message="Navigateur non disponible",
                    error="Le navigateur n'est pas initialisé ou a été fermé.",
                    duration_ms=(time.time() - start) * 1000,
                )

            context_options: dict[str, Any] = {}
            if user_data_dir is not None:
                context_options["user_data_dir"] = user_data_dir

            new_context = self._browser.new_context(**context_options)
            new_page = new_context.new_page()

            # Garder l'ancien contexte mais utiliser le nouveau
            self._context = new_context
            self._page = new_page

            with self._pages_lock:
                self._pages.append(new_page)
                self._current_page_index = len(self._pages) - 1

            duration = (time.time() - start) * 1000

            return BrowserResult(
                success=True,
                message="Nouveau contexte de navigation créé",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message="Échec de la création du contexte",
                error=str(e),
                duration_ms=duration,
            )

    def create_new_page(self) -> BrowserResult:
        """Crée un nouvel onglet / une nouvelle page dans le contexte courant.

        Returns:
            BrowserResult indiquant le succès ou l'échec.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        try:
            if self._context is None:
                return BrowserResult(
                    success=False,
                    message="Contexte non disponible",
                    error="Le contexte de navigation n'existe pas.",
                    duration_ms=(time.time() - start) * 1000,
                )

            new_page = self._context.new_page()

            with self._pages_lock:
                self._pages.append(new_page)
                self._current_page_index = len(self._pages) - 1

            self._page = new_page

            duration = (time.time() - start) * 1000

            return BrowserResult(
                success=True,
                message="Nouvelle page créée",
                data={"pages_count": len(self._pages), "page_index": self._current_page_index},
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return BrowserResult(
                success=False,
                message="Échec de la création de la page",
                error=str(e),
                duration_ms=duration,
            )

    def switch_to_page(self, index: int) -> BrowserResult:
        """Bascule vers un onglet / une page par son index.

        Args:
            index: Index de la page dans la liste (0 = première).

        Returns:
            BrowserResult indiquant le succès ou l'échec.
        """
        start = time.time()

        init_check = self._ensure_initialized()
        if init_check is not None:
            return init_check

        with self._pages_lock:
            if index < 0 or index >= len(self._pages):
                return BrowserResult(
                    success=False,
                    message=f"Index de page invalide: {index}",
                    error=(
                        f"La page index {index} n'existe pas. "
                        f"Pages disponibles: 0-{len(self._pages) - 1}"
                    ),
                    duration_ms=(time.time() - start) * 1000,
                )

            page = self._pages[index]
            if page.is_closed():
                return BrowserResult(
                    success=False,
                    message=f"La page {index} est fermée",
                    error=f"La page à l'index {index} a été fermée.",
                    duration_ms=(time.time() - start) * 1000,
                )

            self._page = page
            self._current_page_index = index

            # Mettre à jour l'URL courante
            try:
                self._current_url = page.url
            except Exception:
                pass

        duration = (time.time() - start) * 1000

        return BrowserResult(
            success=True,
            message=f"Basculé vers la page {index}",
            data={
                "url": self._current_url,
                "pages_count": len(self._pages),
                "page_index": index,
            },
            duration_ms=duration,
        )


# ── Fonction d'enregistrement des outils ────────────────────────


def register_browser_tools(
    registry: ToolRegistry, executor: ToolExecutor
) -> None:
    """Enregistre les outils de contrôle navigateur dans le ToolRegistry.

    Définit 9 outils :
    - ``browser_navigate`` : Navigue vers une URL.
    - ``browser_click`` : Clique sur un élément.
    - ``browser_type`` : Saisit du texte dans un champ.
    - ``browser_extract`` : Extrait des données de la page (texte, HTML, attributs, liens).
    - ``browser_screenshot`` : Capture une capture d'écran.
    - ``browser_scroll`` : Défile la page.
    - ``browser_form_fill`` : Remplit un formulaire.
    - ``browser_execute_script`` : Exécute du JavaScript.
    - ``browser_get_info`` : Obtient les informations du navigateur.

    Les handlers sont enregistrés dans le ToolExecutor fourni.

    Args:
        registry: Registre d'outils (ToolRegistry).
        executor: Exécuteur d'outils (ToolExecutor).
    """

    # ── browser_navigate ───────────────────────────────────────

    navigate_def = ToolDefinition(
        name="browser_navigate",
        description=(
            "Navigue vers une URL dans le navigateur contrôlé. "
            "Attend le chargement complet de la page. "
            "Retourne l'URL finale, le titre, le code de statut "
            "et le temps de chargement. "
            "Les sites financiers (banques, PayPal, etc.) sont "
            "bloqués par sécurité sauf approbation explicite."
        ),
        category="web",
        parameters=[
            ToolParameter(
                name="url",
                type="str",
                description=(
                    "URL complète (avec https://) vers laquelle naviguer. "
                    "Ex: 'https://example.com/page'"
                ),
                required=True,
            ),
            ToolParameter(
                name="timeout",
                type="int",
                description=(
                    "Timeout en millisecondes "
                    "(défaut: 30000, max: 120000)"
                ),
                required=False,
                default=DEFAULT_TIMEOUT_MS,
            ),
            ToolParameter(
                name="wait_until",
                type="str",
                description=(
                    "Condition d'attente: 'load' (défaut), "
                    "'domcontentloaded', 'networkidle'"
                ),
                required=False,
                default="load",
            ),
        ],
    )

    def _navigate_handler(**kwargs: Any) -> dict:
        ctrl = BrowserController.get_instance()
        url = kwargs.get("url", "")
        timeout = kwargs.get("timeout", DEFAULT_TIMEOUT_MS)
        wait_until = kwargs.get("wait_until", "load")

        result = ctrl.navigate(url=url, timeout=timeout, wait_until=wait_until)

        return {
            "success": result.status_code > 0 or result.title != "",
            "url": result.url,
            "title": result.title,
            "status_code": result.status_code,
            "final_url": result.final_url,
            "load_time_ms": result.load_time_ms,
        }

    registry.register(navigate_def)
    executor.register_handler("browser_navigate", _navigate_handler)

    # ── browser_click ──────────────────────────────────────────

    click_def = ToolDefinition(
        name="browser_click",
        description=(
            "Clique sur un élément de la page web identifié par un "
            "sélecteur. Supporte les sélecteurs CSS ('.class', '#id'), "
            "XPath ('//div[...]'), et les sélecteurs texte ('text=...'). "
            "Attend que l'élément soit visible avant de cliquer."
        ),
        category="web",
        parameters=[
            ToolParameter(
                name="selector",
                type="str",
                description=(
                    "Sélecteur de l'élément à cliquer. "
                    "Ex: '#submit-btn', '.nav-link', "
                    "'//button[text()=\"OK\"]', 'text=Continuer'"
                ),
                required=True,
            ),
            ToolParameter(
                name="timeout",
                type="int",
                description="Timeout en ms (défaut: 10000)",
                required=False,
                default=DEFAULT_WAIT_TIMEOUT,
            ),
            ToolParameter(
                name="force",
                type="bool",
                description=(
                    "Forcer le clic même si l'élément n'est pas "
                    "visible (défaut: false)"
                ),
                required=False,
                default=False,
            ),
        ],
    )

    def _click_handler(**kwargs: Any) -> dict:
        ctrl = BrowserController.get_instance()
        selector = kwargs.get("selector", "")
        timeout = kwargs.get("timeout", DEFAULT_WAIT_TIMEOUT)
        force = bool(kwargs.get("force", False))

        result = ctrl.click(selector=selector, timeout=timeout, force=force)

        return {
            "success": result.success,
            "message": result.message,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }

    registry.register(click_def)
    executor.register_handler("browser_click", _click_handler)

    # ── browser_type ───────────────────────────────────────────

    type_def = ToolDefinition(
        name="browser_type",
        description=(
            "Saisit du texte dans un champ de formulaire. "
            "Efface d'abord le champ avant de saisir. "
            "Utile pour remplir les champs de connexion, "
            "recherche, etc."
        ),
        category="web",
        parameters=[
            ToolParameter(
                name="selector",
                type="str",
                description=(
                    "Sélecteur du champ de saisie. "
                    "Ex: '#email', '[name=\"username\"]', "
                    "'input[type=\"email\"]'"
                ),
                required=True,
            ),
            ToolParameter(
                name="text",
                type="str",
                description="Texte à saisir dans le champ",
                required=True,
            ),
            ToolParameter(
                name="delay",
                type="int",
                description=(
                    "Délai entre caractères en ms "
                    "(défaut: 50, 0 = instantané)"
                ),
                required=False,
                default=50,
            ),
            ToolParameter(
                name="clear_first",
                type="bool",
                description=(
                    "Effacer le champ avant de saisir "
                    "(défaut: true)"
                ),
                required=False,
                default=True,
            ),
        ],
    )

    def _type_handler(**kwargs: Any) -> dict:
        ctrl = BrowserController.get_instance()
        selector = kwargs.get("selector", "")
        text = kwargs.get("text", "")
        delay = kwargs.get("delay", 50)
        clear_first = kwargs.get("clear_first", True)

        result = ctrl.type(
            selector=selector,
            text=text,
            delay=delay,
            clear_first=clear_first,
        )

        return {
            "success": result.success,
            "message": result.message,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }

    registry.register(type_def)
    executor.register_handler("browser_type", _type_handler)

    # ── browser_extract ────────────────────────────────────────

    extract_def = ToolDefinition(
        name="browser_extract",
        description=(
            "Extrait des données de la page web courante. "
            "Actions disponibles: 'get_text' (texte d'un élément), "
            "'get_html' (HTML d'un élément ou de la page), "
            "'get_attribute' (attribut d'un élément), "
            "'get_links' (tous les liens de la page), "
            "'get_images' (toutes les images de la page), "
            "'get_forms' (tous les formulaires et leurs champs)."
        ),
        category="web",
        parameters=[
            ToolParameter(
                name="action",
                type="str",
                description=(
                    "Action d'extraction: 'get_text', 'get_html', "
                    "'get_attribute', 'get_links', 'get_images', "
                    "'get_forms'"
                ),
                required=True,
            ),
            ToolParameter(
                name="selector",
                type="str",
                description=(
                    "Sélecteur CSS/XPath pour get_text, get_html, "
                    "get_attribute. Ignoré pour get_links, get_images, "
                    "get_forms."
                ),
                required=False,
                default="",
            ),
            ToolParameter(
                name="attribute",
                type="str",
                description=(
                    "Nom de l'attribut pour get_attribute "
                    "(ex: 'href', 'src', 'alt', 'class')"
                ),
                required=False,
                default="",
            ),
        ],
    )

    def _extract_handler(**kwargs: Any) -> dict:
        ctrl = BrowserController.get_instance()
        action = kwargs.get("action", "").lower()
        selector = kwargs.get("selector", "")
        attribute = kwargs.get("attribute", "")

        if action == "get_text":
            result = ctrl.get_text(selector=selector)
            return {
                "success": result.success,
                "data": result.data,
                "error": result.error,
                "duration_ms": result.duration_ms,
            }

        elif action == "get_html":
            sel = selector if selector else None
            result = ctrl.get_html(selector=sel)
            return {
                "success": result.success,
                "data": result.data,
                "error": result.error,
                "duration_ms": result.duration_ms,
            }

        elif action == "get_attribute":
            if not attribute:
                return {
                    "success": False,
                    "data": None,
                    "error": "Le paramètre 'attribute' est requis pour get_attribute",
                    "duration_ms": 0,
                }
            result = ctrl.get_attribute(selector=selector, attr=attribute)
            return {
                "success": result.success,
                "data": result.data,
                "error": result.error,
                "duration_ms": result.duration_ms,
            }

        elif action == "get_links":
            links = ctrl.get_all_links()
            return {
                "success": True,
                "data": links,
                "error": None,
                "duration_ms": 0,
            }

        elif action == "get_images":
            images = ctrl.get_images()
            return {
                "success": True,
                "data": images,
                "error": None,
                "duration_ms": 0,
            }

        elif action == "get_forms":
            forms = ctrl.get_forms()
            return {
                "success": True,
                "data": forms,
                "error": None,
                "duration_ms": 0,
            }

        else:
            return {
                "success": False,
                "data": None,
                "error": (
                    f"Action inconnue: '{action}'. "
                    f"Actions disponibles: get_text, get_html, "
                    f"get_attribute, get_links, get_images, get_forms"
                ),
                "duration_ms": 0,
            }

    registry.register(extract_def)
    executor.register_handler("browser_extract", _extract_handler)

    # ── browser_screenshot ─────────────────────────────────────

    screenshot_def = ToolDefinition(
        name="browser_screenshot",
        description=(
            "Capture une capture d'écran de la page web courante. "
            "Peut capturer la page entière (full_page=true) ou "
            "un élément spécifique (avec le paramètre selector). "
            "Retourne le chemin du fichier PNG généré."
        ),
        category="web",
        parameters=[
            ToolParameter(
                name="full_page",
                type="bool",
                description=(
                    "Capturer la page entière (scroll complet) "
                    "si true, seulement la partie visible si false "
                    "(défaut: false)"
                ),
                required=False,
                default=False,
            ),
            ToolParameter(
                name="selector",
                type="str",
                description=(
                    "Sélecteur CSS/XPath d'un élément à capturer "
                    "uniquement (optionnel)"
                ),
                required=False,
                default="",
            ),
            ToolParameter(
                name="path",
                type="str",
                description=(
                    "Chemin de sauvegarde (optionnel). "
                    "Si non fourni, généré dans ~/Nuru_Workspace/screenshots/"
                ),
                required=False,
                default="",
            ),
        ],
    )

    def _screenshot_handler(**kwargs: Any) -> dict:
        ctrl = BrowserController.get_instance()
        full_page = bool(kwargs.get("full_page", False))
        selector = kwargs.get("selector", "") or None
        path = kwargs.get("path", "") or None

        result = ctrl.screenshot(
            full_page=full_page,
            path=path,
            selector=selector,
        )

        return {
            "success": result.success,
            "path": result.data,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }

    registry.register(screenshot_def)
    executor.register_handler("browser_screenshot", _screenshot_handler)

    # ── browser_scroll ─────────────────────────────────────────

    scroll_def = ToolDefinition(
        name="browser_scroll",
        description=(
            "Défile la page web dans une direction donnée. "
            "Directions: 'up', 'down', 'left', 'right', 'top', "
            "'bottom', ou 'to_element' pour défiler vers un élément. "
            "Le paramètre 'pixels' contrôle l'amplitude du défilement."
        ),
        category="web",
        parameters=[
            ToolParameter(
                name="direction",
                type="str",
                description=(
                    "Direction du défilement: 'up', 'down', 'left', "
                    "'right', 'top', 'bottom', 'to_element'"
                ),
                required=True,
            ),
            ToolParameter(
                name="selector",
                type="str",
                description=(
                    "Sélecteur de l'élément cible pour "
                    "direction='to_element'"
                ),
                required=False,
                default="",
            ),
            ToolParameter(
                name="pixels",
                type="int",
                description=(
                    "Nombre de pixels à défiler "
                    "(défaut: 500, ignoré pour top/bottom/to_element)"
                ),
                required=False,
                default=500,
            ),
        ],
    )

    def _scroll_handler(**kwargs: Any) -> dict:
        ctrl = BrowserController.get_instance()
        direction = kwargs.get("direction", "").lower()
        selector = kwargs.get("selector", "")
        pixels = kwargs.get("pixels", 500)

        if direction == "to_element":
            if not selector:
                return {
                    "success": False,
                    "error": "Le paramètre 'selector' est requis pour to_element",
                    "duration_ms": 0,
                }
            result = ctrl.scroll_to(selector=selector)
        elif direction == "up":
            result = ctrl.scroll_by(delta_x=0, delta_y=-abs(pixels))
        elif direction == "down":
            result = ctrl.scroll_by(delta_x=0, delta_y=abs(pixels))
        elif direction == "left":
            result = ctrl.scroll_by(delta_x=-abs(pixels), delta_y=0)
        elif direction == "right":
            result = ctrl.scroll_by(delta_x=abs(pixels), delta_y=0)
        elif direction == "top":
            result = ctrl._scroll_to_top()
        elif direction == "bottom":
            result = ctrl._scroll_to_bottom()
        else:
            return {
                "success": False,
                "error": (
                    f"Direction inconnue: '{direction}'. "
                    f"Directions: up, down, left, right, top, "
                    f"bottom, to_element"
                ),
                "duration_ms": 0,
            }

        return {
            "success": result.success,
            "message": result.message,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }

    registry.register(scroll_def)
    executor.register_handler("browser_scroll", _scroll_handler)

    # ── browser_form_fill ──────────────────────────────────────

    form_fill_def = ToolDefinition(
        name="browser_form_fill",
        description=(
            "Remplit un formulaire web avec des champs multiples. "
            "Les champs sont définis par une liste de dictionnaires "
            "contenant: selector (str), value (str|bool), "
            "et type optionnel (text, checkbox, select, radio, file). "
            "Peut soumettre le formulaire automatiquement."
        ),
        category="web",
        parameters=[
            ToolParameter(
                name="fields",
                type="list",
                description=(
                    "Liste de champs à remplir. Chaque champ est un dict: "
                    "{'selector': '#email', 'value': 'test@ex.com', "
                    "'type': 'text'}. "
                    "Les types supportés: text (défaut), checkbox, "
                    "select, radio, file."
                ),
                required=True,
            ),
            ToolParameter(
                name="submit",
                type="bool",
                description=(
                    "Soumettre le formulaire après remplissage "
                    "en cliquant sur le bouton submit "
                    "(défaut: false)"
                ),
                required=False,
                default=False,
            ),
        ],
    )

    def _form_fill_handler(**kwargs: Any) -> dict:
        ctrl = BrowserController.get_instance()
        fields_data = kwargs.get("fields", [])
        submit = bool(kwargs.get("submit", False))

        # Convertir les dicts en objets FormField
        fields: list[FormField] = []
        for f in fields_data:
            if isinstance(f, dict):
                fields.append(FormField(
                    selector=f.get("selector", ""),
                    value=f.get("value"),
                    type=f.get("type", "text"),
                ))

        if not fields:
            return {
                "success": False,
                "error": "Aucun champ fourni. "
                         "Fournissez une liste de champs avec "
                         "selector et value.",
                "duration_ms": 0,
            }

        result = ctrl.fill_form(fields=fields, submit=submit)

        return {
            "success": result.success,
            "message": result.message,
            "data": result.data,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }

    registry.register(form_fill_def)
    executor.register_handler("browser_form_fill", _form_fill_handler)

    # ── browser_execute_script ─────────────────────────────────

    script_def = ToolDefinition(
        name="browser_execute_script",
        description=(
            "Exécute du JavaScript dans la page web courante. "
            "Retourne le résultat de l'exécution. "
            "La sécurité bloque les scripts utilisant des API "
            "sensibles (crypto.subtle, require, eval, etc.)."
        ),
        category="web",
        parameters=[
            ToolParameter(
                name="script",
                type="str",
                description=(
                    "Code JavaScript à exécuter dans le navigateur. "
                    "Ex: 'document.title' ou "
                    "'document.querySelector(\"h1\").textContent'"
                ),
                required=True,
            ),
        ],
    )

    def _script_handler(**kwargs: Any) -> dict:
        ctrl = BrowserController.get_instance()
        script = kwargs.get("script", "")

        result = ctrl.execute_script(script=script)

        return {
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }

    registry.register(script_def)
    executor.register_handler("browser_execute_script", _script_handler)

    # ── browser_get_info ───────────────────────────────────────

    info_def = ToolDefinition(
        name="browser_get_info",
        description=(
            "Retourne les informations actuelles sur le navigateur "
            "contrôlé: type (chromium/firefox/webkit), version, "
            "mode headless, URL courante, nombre de pages ouvertes. "
            "Utile pour vérifier l'état du navigateur."
        ),
        category="web",
        parameters=[],
    )

    def _info_handler(**kwargs: Any) -> dict:  # noqa: ARG001
        ctrl = BrowserController.get_instance()
        info = ctrl.get_browser_info()

        return {
            "success": True,
            "data": info,
            "error": None,
            "duration_ms": 0,
        }

    registry.register(info_def)
    executor.register_handler("browser_get_info", _info_handler)
