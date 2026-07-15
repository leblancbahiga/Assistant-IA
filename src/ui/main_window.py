"""
NURU V16 — MainWindow.
Fenêtre unique : Sidebar + QStackedWidget + RightInspectorPanel + StatusBar.
Phase 1 : coque seule, ChatPage branchée.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
)

from src.ui.navigation.sidebar import Sidebar
from src.ui.navigation.nav_controller import NavigationController
from src.ui.navigation.status_bar import StatusBar
from src.ui.panels.right_inspector import RightInspectorPanel
from src.ui.pages.chat_page import ChatPage
from src.ui.theme.theme_manager import ThemeManager
from src.ui.tokens import Color, Typography, WindowSizes, Spacing

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Fenêtre unique NURU V16 — sidebar + zone principale + panneau droit."""

    def __init__(
        self,
        engine=None,
        theme: ThemeManager | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._engine = engine
        self._theme = theme

        self.setObjectName("MainWindow")
        self.setWindowTitle("NURU")
        self.resize(1100, 720)
        self.setMinimumSize(900, 600)

        # ── TitleBar custom ──
        self._setup_title_bar()

        # ── Sidebar ──
        self.sidebar = Sidebar(self)

        # ── Stack central ──
        self.stack = QStackedWidget(self)

        # ── Panneau droit ──
        self.right_panel = RightInspectorPanel(self)

        # ── Splitter horizontal ──
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.stack)
        splitter.addWidget(self.right_panel)
        splitter.setStretchFactor(0, 0)  # sidebar ne s'étire pas
        splitter.setStretchFactor(1, 1)  # stack central s'étire
        splitter.setStretchFactor(2, 0)  # right panel ne s'étire pas
        splitter.setSizes([WindowSizes.SIDEBAR_WIDTH, 700, 280])

        # ── Conteneur central ──
        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.addWidget(splitter)
        self.setCentralWidget(central)

        # ── StatusBar ──
        self.status_bar = StatusBar(self)
        self.setStatusBar(self.status_bar)

        # ── Navigation ──
        self.nav = NavigationController(
            sidebar=self.sidebar, stack=self.stack, parent=self,
        )

        # ── Pages (Phase 1 : ChatPage uniquement) ──
        self._register_default_pages()

        # ── Raccourcis ──
        self._setup_shortcuts()

        # ── Thème ──
        if self._theme:
            self._theme.apply(self)

        logger.info("MainWindow prête — sidebar + stack + right panel")

    # ── Setup ────────────────────────────────────────────

    def _setup_title_bar(self) -> None:
        """Barre de titre personnalisée (non-frameless en Phase 1)."""
        # On garde la barre native macOS pour l'instant (phase 1)
        # Phase 5 (Polish) : frameless custom avec wordmark + Ctrl+K hint
        pass

    def _register_default_pages(self) -> None:
        """Enregistre les pages dans le NavigationController.

        Phase 2a : Chat, Documents, Mémoire, Dashboard reconnectés.
        Phase 2b+ : Agents, Paramètres, Outils, Plugins, Modèles.
        """
        # ChatPage — page par défaut
        if self._engine is not None:
            try:
                from src.ui.conversation_surface import ConversationSurface

                surface = ConversationSurface(self._engine)
                chat = ChatPage(conversation_surface=surface)
            except Exception as e:
                logger.warning(f"Impossible de charger ConversationSurface: {e}")
                chat = ChatPage()
        else:
            chat = ChatPage()

        self.nav.register_page("chat", chat, make_default=True)
        self.nav.navigate_to("chat")

        # Documents Page
        try:
            from src.ui.pages.documents_page import DocumentsPage
            self.nav.register_page("documents", DocumentsPage(self._engine))
        except Exception as e:
            logger.warning(f"Impossible de charger DocumentsPage: {e}")

        # Memory Page
        try:
            from src.ui.pages.memory_page import MemoryPage
            self.nav.register_page("memory", MemoryPage())
        except Exception as e:
            logger.warning(f"Impossible de charger MemoryPage: {e}")

        # Dashboard Page
        try:
            from src.ui.pages.dashboard_page import DashboardPage
            self.nav.register_page("dashboard", DashboardPage())
        except Exception as e:
            logger.warning(f"Impossible de charger DashboardPage: {e}")

        # Agents Page
        try:
            from src.ui.pages.agents_page import AgentsPage
            self.nav.register_page("agents", AgentsPage())
        except Exception as e:
            logger.warning(f"Impossible de charger AgentsPage: {e}")

        # Tools Page
        try:
            from src.ui.pages.tools_page import ToolsPage
            self.nav.register_page("tools", ToolsPage())
        except Exception as e:
            logger.warning(f"Impossible de charger ToolsPage: {e}")

        # Settings Page
        try:
            from src.ui.pages.settings_page import SettingsPage
            self.nav.register_page("settings", SettingsPage())
        except Exception as e:
            logger.warning(f"Impossible de charger SettingsPage: {e}")

        # Plugins Page
        try:
            from src.ui.pages.plugins_page import PluginsPage
            self.nav.register_page("plugins", PluginsPage())
        except Exception as e:
            logger.warning(f"Impossible de charger PluginsPage: {e}")

        # Models Page
        try:
            from src.ui.pages.models_page import ModelsPage
            self.nav.register_page("models", ModelsPage())
        except Exception as e:
            logger.warning(f"Impossible de charger ModelsPage: {e}")

        # Home Page (placeholder)
        try:
            from src.ui.pages.home_page import HomePage
            self.nav.register_page("home", HomePage())
        except Exception as e:
            logger.debug(f"HomePage non disponible: {e}")

    def _setup_shortcuts(self) -> None:
        """Configure les raccourcis globaux."""
        from PySide6.QtGui import QShortcut, QKeySequence

        # Ctrl+K — Command Palette (placeholder Phase 1)
        # Phase 4 : implémentation réelle
        QShortcut(QKeySequence("Ctrl+K"), self).activated.connect(
            self._toggle_command_palette
        )

        # Ctrl+N — Nouvelle conversation
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(
            self._new_conversation
        )

        # Ctrl+\ — Basculer panneau droit
        QShortcut(QKeySequence("Ctrl+\\"), self).activated.connect(
            self.toggle_right_panel
        )

        # Escape — Quitter command palette / focus mode
        QShortcut(QKeySequence("Escape"), self).activated.connect(
            self._on_escape
        )

    # ── Actions ──────────────────────────────────────────

    def toggle_right_panel(self) -> None:
        visible = not self.right_panel.isVisible()
        self.right_panel.setVisible(visible)

    def toggle_sidebar(self) -> None:
        self.sidebar.set_collapsed(not self.sidebar.collapsed)

    def enter_focus_mode(self) -> None:
        """Masque sidebar et panneau droit — focus sur le chat."""
        self.sidebar.setVisible(False)
        self.right_panel.setVisible(False)

    def exit_focus_mode(self) -> None:
        self.sidebar.setVisible(True)
        self.right_panel.setVisible(True)

    def _new_conversation(self) -> None:
        """Nouvelle conversation — vide le chat actuel."""
        logger.debug("Nouvelle conversation demandée")
        # Phase 2 : vider le modèle de messages

    def _toggle_command_palette(self) -> None:
        """Placeholder — Phase 4 : vraie Command Palette."""
        logger.debug("Ctrl+K — Command Palette (Phase 4)")
        # Phase 4 : overlay CommandPalette

    def _on_escape(self) -> None:
        """Touche Escape — retour au mode normal."""
        if not self.right_panel.isVisible() or not self.sidebar.isVisible():
            self.exit_focus_mode()

    # ── API Engine ───────────────────────────────────────

    def set_engine(self, engine) -> None:
        """Injecte ou remplace le moteur de conversation."""
        self._engine = engine
        # Phase 2 : mettre à jour les pages qui en ont besoin
