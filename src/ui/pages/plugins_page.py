"""
NURU V16 — Plugins Page.
Gestionnaire de plugins NURU (Phase 2b : placeholder).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout

from src.ui.tokens import Color, Spacing, Typography, Radius

logger = logging.getLogger(__name__)

_PAL = Color.DARK


class PluginsPage(QWidget):
    """Page Plugins V16 — gestion des extensions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PluginsPageV16")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.MD)

        title = QLabel("🧩  Plugins")
        title.setStyleSheet(
            f"color: {_PAL['text']}; font-size: {Typography.SIZE_HEADING_1}pt; "
            f"font-family: {Typography.FAMILY_DISPLAY}; font-weight: {Typography.WEIGHT_BOLD};"
        )
        layout.addWidget(title)

        subtitle = QLabel("Extensions et connecteurs")
        subtitle.setStyleSheet(f"color: {Color.TEXT_SECONDARY}; font-size: {Typography.SIZE_BODY}pt;")
        layout.addWidget(subtitle)

        # Placeholder cards
        for name, desc, status in [
            ("📁 WebDAV", "Synchronisation cloud", "🔜 Bientôt"),
            ("📧 Email", "Client email intégré", "🔜 Bientôt"),
            ("📝 Notes", "Obsidian / Notion bridge", "🔜 Bientôt"),
            ("📞 VoIP", "Appels vocaux IA", "🔜 Bientôt"),
        ]:
            card = QWidget()
            card.setObjectName("PluginCard")
            card.setFixedHeight(64)
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)

            name_lbl = QLabel(name)
            name_lbl.setStyleSheet(f"color: {_PAL['text']}; font-size: {Typography.SIZE_BODY}pt; font-weight: {Typography.WEIGHT_SEMIBOLD};")
            card_layout.addWidget(name_lbl)

            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(f"color: {Color.TEXT_SECONDARY}; font-size: 9pt;")
            card_layout.addWidget(desc_lbl)

            card_layout.addStretch()

            status_lbl = QLabel(status)
            status_lbl.setStyleSheet(f"color: {Color.TEXT_MUTED}; font-size: 8pt;")
            card_layout.addWidget(status_lbl)

            layout.addWidget(card)

        layout.addStretch()
