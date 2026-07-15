"""
NURU V16 — Models Page.
Gestionnaire de modèles LLM (Phase 2b : placeholder avec liste).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame,
)

from src.ui.tokens import Color, Spacing, Typography

logger = logging.getLogger(__name__)

_PAL = Color.DARK


class ModelsPage(QWidget):
    """Page Modèles V16 — sélection et gestion des LLM."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ModelsPageV16")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.MD)

        title = QLabel("🧠  Modèles")
        title.setStyleSheet(
            f"color: {_PAL['text']}; font-size: {Typography.SIZE_HEADING_1}pt; "
            f"font-family: {Typography.FAMILY_DISPLAY}; font-weight: {Typography.WEIGHT_BOLD};"
        )
        layout.addWidget(title)

        # Modèle actif
        active_card = QFrame()
        active_card.setObjectName("ActiveModelCard")
        active_card.setFixedHeight(80)
        card_layout = QHBoxLayout(active_card)
        card_layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)

        icon = QLabel("⚡")
        icon.setStyleSheet(f"font-size: 24pt;")
        card_layout.addWidget(icon)

        info = QVBoxLayout()
        name = QLabel("Modèle actif")
        name.setStyleSheet(f"color: {Color.TEXT_SECONDARY}; font-size: 9pt;")
        info.addWidget(name)
        model_name = QLabel("deepseek-v4-flash-free")
        model_name.setStyleSheet(
            f"color: {_PAL['text']}; font-size: 13pt; "
            f"font-family: {Typography.FAMILY_DISPLAY}; font-weight: {Typography.WEIGHT_BOLD};"
        )
        info.addWidget(model_name)
        card_layout.addLayout(info)
        card_layout.addStretch()

        provider = QLabel("OpenCode Zen")
        provider.setStyleSheet(f"color: {Color.CYAN}; font-size: 10pt;")
        card_layout.addWidget(provider)

        layout.addWidget(active_card)

        # Liste des modèles disponibles (placeholder)
        models_list = [
            ("deepseek-v4-flash-free", "OpenCode Zen", "Gratuit", True),
            ("claude-sonnet-4", "Anthropic", "Premium", False),
            ("gpt-4o", "OpenAI", "Premium", False),
            ("llama-3.3-70b", "Groq", "Gratuit", False),
            ("mixtral-8x22b", "Together", "Gratuit", False),
        ]

        for m_name, m_provider, m_tier, active in models_list:
            row = QFrame()
            row.setObjectName("ModelRow")
            row.setFixedHeight(48)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(Spacing.MD, 0, Spacing.MD, 0)

            status_icon = "●" if active else "○"
            status_color = Color.CYAN if active else Color.TEXT_MUTED
            icon_lbl = QLabel(status_icon)
            icon_lbl.setStyleSheet(f"color: {status_color}; font-size: 12pt;")
            row_layout.addWidget(icon_lbl)

            name_lbl = QLabel(m_name)
            name_lbl.setStyleSheet(f"color: {_PAL['text']}; font-size: 10pt; font-weight: {Typography.WEIGHT_SEMIBOLD};")
            row_layout.addWidget(name_lbl)

            provider_lbl = QLabel(m_provider)
            provider_lbl.setStyleSheet(f"color: {Color.TEXT_SECONDARY}; font-size: 9pt;")
            row_layout.addWidget(provider_lbl)

            row_layout.addStretch()

            tier_lbl = QLabel(m_tier)
            tier_lbl.setStyleSheet(f"color: {Color.TEXT_MUTED}; font-size: 8pt;")
            row_layout.addWidget(tier_lbl)

            layout.addWidget(row)

        layout.addStretch()
