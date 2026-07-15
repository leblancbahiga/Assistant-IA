"""
NURU V16 — Agents Page.
Wrapper autour de agent_task_page.py existante + agent_status.py.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from src.ui.tokens import Color, Spacing, Typography

logger = logging.getLogger(__name__)

_PAL = Color.DARK


class AgentsPage(QWidget):
    """Page Agents V16 — état agent + liste des tâches."""

    def __init__(self, agent_service=None, parent=None):
        super().__init__(parent)
        self.setObjectName("AgentsPageV16")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.MD)

        title = QLabel("🤖  Agents")
        title.setStyleSheet(
            f"color: {_PAL['text']}; font-size: {Typography.SIZE_HEADING_1}pt; "
            f"font-family: {Typography.FAMILY_DISPLAY}; font-weight: {Typography.WEIGHT_BOLD};"
        )
        layout.addWidget(title)

        try:
            from src.ui.components.agent_task_page import AgentTaskPage
            self._inner = AgentTaskPage()
            layout.addWidget(self._inner, stretch=1)
        except Exception as e:
            logger.warning(f"Impossible de charger AgentTaskPage: {e}")
            placeholder = QLabel("Agents — module non disponible")
            placeholder.setStyleSheet(f"color: {Color.TEXT_MUTED};")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(placeholder, stretch=1)
