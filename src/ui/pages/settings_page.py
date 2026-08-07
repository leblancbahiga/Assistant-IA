"""
NURU V16 — Settings Page.
Wrapper autour de settings_page.py existant (6 sections : Général, Modèles,
RAG, Mémoire, Voix, Système).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from src.ui.tokens import Color, Spacing, Typography

logger = logging.getLogger(__name__)

_PAL = Color.DARK


class SettingsPage(QWidget):
    """Page Paramètres V16 — 6 sections configurables."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsPageV16")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.MD)

        title = QLabel("⚙️  Paramètres")
        title.setStyleSheet(
            f"color: {_PAL['text']}; font-size: {Typography.SIZE_HEADING_1}pt; "
            f"font-family: {Typography.FAMILY_DISPLAY}; font-weight: {Typography.WEIGHT_BOLD};"
        )
        layout.addWidget(title)

        try:
            from src.ui.components.settings_page import SettingsPage as LegacySettingsPage
            self._inner = LegacySettingsPage()
            layout.addWidget(self._inner, stretch=1)
        except Exception as e:
            logger.warning(f"Impossible de charger SettingsPage: {e}")
            placeholder = QLabel("Paramètres — module non disponible")
            placeholder.setStyleSheet(f"color: {Color.TEXT_MUTED};")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(placeholder, stretch=1)
