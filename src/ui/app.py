"""
NURU V16 — NuruApp (nouveau bootstrap UI).
Remplace AmbientApp comme point d'entrée UI quand USE_NEW_UI = True.
Phase 1 : coque seule, ChatPage branchée, backend non touché.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow
from src.ui.theme.theme_manager import ThemeManager
from src.ui.tokens import Color

logger = logging.getLogger(__name__)


class NuruApp:
    """Bootstrap UI V16.

    Crée la fenêtre principale et les services UI partagés.
    Le backend (engine) est injecté, jamais importé directement.
    """

    def __init__(self, app: QApplication, engine=None):
        self._app = app
        self._engine = engine

        # Thème
        self.theme = ThemeManager()

        # Fenêtre principale
        self.main_window = MainWindow(engine=self._engine, theme=self.theme)

        # Palette globale Qt
        self._setup_palette(app)

        # Appliquer le thème
        self.theme.apply()

        logger.info("✅ NURU V16 — Interface prête")

    def _setup_palette(self, app: QApplication) -> None:
        """Configure la palette globale Qt."""
        palette = app.palette()
        palette.setColor(palette.ColorRole.Window, "#070A10")
        palette.setColor(palette.ColorRole.WindowText, "#E8ECF1")
        palette.setColor(palette.ColorRole.Base, "#0D1117")
        palette.setColor(palette.ColorRole.Text, "#E8ECF1")
        palette.setColor(palette.ColorRole.Button, "#151B26")
        palette.setColor(palette.ColorRole.ButtonText, "#E8ECF1")
        palette.setColor(palette.ColorRole.Highlight, "#00D4FF")
        palette.setColor(palette.ColorRole.HighlightedText, "#070A10")
        app.setPalette(palette)

    def show(self) -> None:
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def run(self) -> int:
        self.show()
        return self._app.exec()
