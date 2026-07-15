"""
NURU V16 — Tools Page.
Wrapper autour de tool_tester.py existant.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from src.ui.tokens import Color, Spacing, Typography

logger = logging.getLogger(__name__)

_PAL = Color.DARK


class ToolsPage(QWidget):
    """Page Outils V16 — test des outils NURU."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ToolsPageV16")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.MD)

        title = QLabel("🔧  Outils")
        title.setStyleSheet(
            f"color: {_PAL['text']}; font-size: {Typography.SIZE_HEADING_1}pt; "
            f"font-family: {Typography.FAMILY_DISPLAY}; font-weight: {Typography.WEIGHT_BOLD};"
        )
        layout.addWidget(title)

        try:
            from src.ui.components.tool_tester import ToolTester
            self._inner = ToolTester()
            layout.addWidget(self._inner, stretch=1)
        except Exception as e:
            logger.warning(f"Impossible de charger ToolTester: {e}")
            placeholder = QLabel("Outils — module non disponible")
            placeholder.setStyleSheet(f"color: {Color.TEXT_MUTED};")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(placeholder, stretch=1)
