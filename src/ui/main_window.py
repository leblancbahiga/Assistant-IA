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
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
)

from src.ui.navigation.sidebar import Sidebar
from src.ui.navigation.nav_controller import NavigationController
from src.ui.navigation.status_bar import StatusBar
from src.ui.panels.right_inspector import RightInspectorPanel
from src.ui.panels.notification_manager import NotificationManager
from src.ui.panels.command_palette import CommandPalette
from src.ui.panels.title_bar import CustomTitleBar
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

        # ── Frameless (custom title bar) ──
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        # ── TitleBar custom ──
        self.title_bar = CustomTitleBar(self)
        self.title_bar.set_subtitle("")

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

        # ── Conteneur central (title bar + splitter) ──
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.title_bar)
        central_layout.addWidget(splitter, 1)  # stretch = 1
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

        # ── Notifications ──
        self.notif_mgr = NotificationManager(self)
        self.status_bar.set_notification_manager(self.notif_mgr)

        # ── Command Palette ──
        self._palette = CommandPalette(self)
        self._palette.set_main_window(self)

        if self._engine:
            self.set_engine(self._engine)

        logger.info("MainWindow prête — sidebar + stack + right panel")

    # ── Setup ────────────────────────────────────────────

    def _setup_title_bar(self) -> None:
        """Barre de titre personnalisée (non-frameless en Phase 1)."""
        # On garde la barre native macOS pour l'instant (phase 1)
        # Phase 5 (Polish) : frameless custom avec wordmark + Ctrl+K hint
        pass

    def _register_default_pages(self) -> None:
        """Enregistre les pages dans le NavigationController.

        ChatPage est chargée immédiatement (page par défaut).
        Les autres pages sont chargées paresseusement (lazy) à la première navigation.
        """
        # ── ChatPage — page par défaut, chargée tout de suite ──
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

        # ── Pages lazy — importées seulement à la 1ʳᵉ navigation ──
        lazy_pages: list[tuple[str, str, str]] = [
            ("documents", "src.ui.pages.documents_page", "DocumentsPage"),
            ("memory", "src.ui.pages.memory_page", "MemoryPage"),
            ("dashboard", "src.ui.pages.dashboard_page", "DashboardPage"),
            ("agents", "src.ui.pages.agents_page", "AgentsPage"),
            ("tools", "src.ui.pages.tools_page", "ToolsPage"),
            ("settings", "src.ui.pages.settings_page", "SettingsPage"),
            ("plugins", "src.ui.pages.plugins_page", "PluginsPage"),
            ("models", "src.ui.pages.models_page", "ModelsPage"),
        ]

        def _factory(key: str, module: str, cls_name: str, engine=None):
            def _create():
                try:
                    import importlib
                    mod = importlib.import_module(module)
                    klass = getattr(mod, cls_name)
                    if module == "src.ui.pages.documents_page":
                        return klass(engine)
                    return klass()
                except Exception as e:
                    logger.warning(f"Impossible de charger {module}.{cls_name}: {e}")
                    # Fallback : une QWidget vide
                    from PySide6.QtWidgets import QWidget
                    w = QWidget()
                    w.setObjectName("PageFallback")
                    return w
            return _create

        for key, module, cls_name in lazy_pages:
            self.nav.register_lazy(key, _factory(key, module, cls_name, self._engine))

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

        # Ctrl+B — Basculer sidebar
        QShortcut(QKeySequence("Ctrl+B"), self).activated.connect(
            self.toggle_sidebar
        )

        # Alt+← — Page précédente
        QShortcut(QKeySequence("Alt+Left"), self).activated.connect(
            self._go_back
        )

        # Alt+→ — Page suivante (non implémenté)
        QShortcut(QKeySequence("Alt+Right"), self).activated.connect(
            self._go_forward  # Placeholder
        )

        # Ctrl+Shift+F — Focus mode
        QShortcut(QKeySequence("Ctrl+Shift+F"), self).activated.connect(
            self.toggle_focus_mode
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

    def toggle_focus_mode(self) -> None:
        """Bascule entre mode focus et mode normal."""
        if getattr(self, '_focus_active', False):
            self.exit_focus_mode()
        else:
            self.enter_focus_mode()

    def enter_focus_mode(self) -> None:
        """Masque sidebar et panneau droit — focus sur le chat."""
        self._focus_active = True
        self.sidebar.setVisible(False)
        self.right_panel.setVisible(False)
        self.status_bar.show_focus_indicator(True)
        self.title_bar.set_subtitle("focus")
        logger.debug("🔍 Focus mode activé")

    def exit_focus_mode(self) -> None:
        self._focus_active = False
        self.sidebar.setVisible(True)
        self.right_panel.setVisible(True)
        self.status_bar.show_focus_indicator(False)
        self.title_bar.set_subtitle("")
        logger.debug("↩ Focus mode désactivé")

    def _new_conversation(self) -> None:
        """Nouvelle conversation — vide le chat actuel."""
        logger.debug("Nouvelle conversation demandée")
        # Phase 2 : vider le modèle de messages

    def _toggle_command_palette(self) -> None:
        """Ctrl+K — Ouvre/ferme la Command Palette."""
        if self._palette.isVisible():
            self._palette.close()
        else:
            self._palette.show_centered()

    def _on_escape(self) -> None:
        """Touche Escape — priorité : fermer palette > quitter focus > rien."""
        # Priorité 1 : palette ouverte
        if self._palette.isVisible():
            self._palette.close()
            return
        # Priorité 2 : focus mode
        if getattr(self, '_focus_active', False):
            self.exit_focus_mode()
            return
        # Priorité 3 : masquage latéraux
        if not self.right_panel.isVisible() or not self.sidebar.isVisible():
            self.exit_focus_mode()

    def _go_back(self) -> None:
        """Navigation historique — page précédente."""
        if self.nav.go_back():
            logger.debug("↩ Navigation arrière")

    def _go_forward(self) -> None:
        """Navigation avant (placeholder Phase 4)."""
        logger.debug("Navigation avant (pas encore implémentée)")

    # ── Responsive ────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        """Réagit au redimensionnement de la fenêtre."""
        super().resizeEvent(event)
        w = event.size().width()
        # < 800px → sidebar repliée, right panel caché
        if w < 800:
            if not self.sidebar.collapsed:
                self.sidebar.set_collapsed(True)
            if self.right_panel.isVisible():
                self.right_panel.hide()
        # 800-1000 → sidebar repliée, right panel visible
        elif w < 1000:
            if not self.sidebar.collapsed:
                self.sidebar.set_collapsed(True)
            if not self.right_panel.isVisible():
                self.right_panel.show()
        # > 1000 → tout visible
        else:
            if self.sidebar.collapsed:
                self.sidebar.set_collapsed(False)
            if not self.right_panel.isVisible():
                self.right_panel.show()

    # ── API Engine ───────────────────────────────────────

    def set_engine(self, engine) -> None:
        """Injecte ou remplace le moteur de conversation."""
        self._engine = engine
        if engine is None:
            return

        # StatusBar ← engine signals
        self.status_bar.set_engine(engine)

        # RightInspector ← engine signals
        self.right_panel.set_engine(engine)

        # NotificationManager ← engine errors
        try:
            engine.error_occurred.connect(self._on_engine_error)
        except Exception as e:
            logger.warning(f"set_engine notification: {e}")

        # Màj des pages qui dépendent de l'engine
        # (Phase 2b : pages avec services backend)
        logger.info("Engine connecté à StatusBar + RightInspector + Notifications")

    def _on_engine_error(self, code: str, message: str) -> None:
        """Notification d'erreur engine."""
        from src.ui.panels.notification_manager import Severity
        if hasattr(self, 'notif_mgr') and self.notif_mgr:
            self.notif_mgr.notify(
                f"[{code}] {message}",
                severity=Severity.ERROR,
                source="engine",
            )
