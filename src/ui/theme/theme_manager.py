"""
NURU V16 — ThemeManager.
Signal theme_changed → tous les widgets se mettent à jour.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from src.ui.theme.qss_builder import build_qss


class ThemeManager(QObject):
    """Service central qui applique tokens.py → QSS global.

    Usage:
        theme = ThemeManager(parent)
        theme.apply(main_window)
        # Plus tard, basculer thème clair/sombre :
        theme.set_dark(False)
    """

    theme_changed = Signal()  # émis après application du nouveau QSS

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._dark = True

    @property
    def is_dark(self) -> bool:
        return self._dark

    def apply(self, widget: QObject | None = None) -> None:
        """Applique le QSS généré à l'application entière."""
        qss = build_qss(dark=self._dark)
        QApplication.instance().setStyleSheet(qss)
        self.theme_changed.emit()

    def set_dark(self, dark: bool) -> None:
        if dark != self._dark:
            self._dark = dark
            self.apply()

    def toggle(self) -> bool:
        """Bascule dark/light. Retourne le nouvel état (True = dark)."""
        self._dark = not self._dark
        self.apply()
        return self._dark
