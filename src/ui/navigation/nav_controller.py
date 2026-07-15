"""
NURU V16 — NavigationController.
Gère le QStackedWidget, la sidebar, les raccourcis et l'historique.
"""

from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QStackedWidget

from src.ui.navigation.sidebar import Sidebar


class NavigationController(QObject):
    """Orchestre la navigation entre pages du QStackedWidget."""

    def __init__(
        self,
        sidebar: Sidebar,
        stack: QStackedWidget,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._sidebar = sidebar
        self._stack = stack
        self._pages: dict[str, int] = {}  # key → index dans le stack
        self._history: list[str] = []

        sidebar.page_selected.connect(self._on_sidebar_select)

    def register_page(self, key: str, widget, make_default: bool = False) -> None:
        """Enregistre une page dans le stack."""
        index = self._stack.addWidget(widget)
        self._pages[key] = index
        if make_default:
            self._default_key = key

    def navigate_to(self, key: str) -> None:
        """Navigue vers une page enregistrée."""
        if key not in self._pages:
            return
        if self._stack.currentWidget():
            self._history.append(key)
        self._stack.setCurrentIndex(self._pages[key])
        self._sidebar.set_active(key)

    def go_back(self) -> bool:
        """Reviens à la page précédente. Retourne True si un retour a eu lieu."""
        if len(self._history) < 2:
            return False
        self._history.pop()  # current
        prev = self._history.pop()  # previous
        self.navigate_to(prev)
        return True

    @property
    def current_key(self) -> str | None:
        """Retourne la clé de la page active, ou None."""
        current = self._stack.currentWidget()
        if current is None:
            return None
        for key, index in self._pages.items():
            if self._stack.widget(index) is current:
                return key
        return None

    # ── slots ───────────────────────────────────────────

    def _on_sidebar_select(self, key: str) -> None:
        self.navigate_to(key)
