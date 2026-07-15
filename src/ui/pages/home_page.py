"""
NURU V16 — Home Page.
Page d'accueil minimaliste pour V16 (placeholder Phase 2a).
Affiche la météo, quick-actions et bienvenue.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from src.ui.tokens import Color, Spacing, Typography

_PAL = Color.DARK


class HomePage(QWidget):
    """Home — page d'accueil, hub de navigation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HomePageV16")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.MD)

        title = QLabel("🏠  Accueil")
        title.setStyleSheet(
            f"color: {_PAL['text']}; font-size: {Typography.SIZE_HEADING_1}pt; "
            f"font-family: {Typography.FAMILY_DISPLAY}; font-weight: {Typography.WEIGHT_BOLD};"
        )
        layout.addWidget(title)

        subtitle = QLabel("Bienvenue dans NURU V16")
        subtitle.setStyleSheet(
            f"color: {Color.TEXT_SECONDARY}; font-size: {Typography.SIZE_BODY}pt; "
            f"font-family: {Typography.FAMILY_BODY};"
        )
        layout.addWidget(subtitle)

        layout.addStretch()
