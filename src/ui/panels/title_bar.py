"""
NURU V16 — CustomTitleBar.
Barre de titre frameless macOS : wordmark + traffic lights.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QPoint, Signal, QTimer
from PySide6.QtGui import QMouseEvent, QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QApplication

from src.ui.tokens import Color, Typography, Spacing

logger = logging.getLogger(__name__)

_BTN_SIZE = 12
_TRAFFIC_GAP = 8


class TitleBarButton(QPushButton):
    """Bouton de fenêtre macOS style traffic light."""

    def __init__(self, color: str, hover_color: str, action: str, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._hover_color = QColor(hover_color)
        self._is_hovered = False
        self._action = action
        self.setFixedSize(_BTN_SIZE, _BTN_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent; border: none;")

    def enterEvent(self, event) -> None:
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = self._hover_color if self._is_hovered else self._color
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, _BTN_SIZE, _BTN_SIZE)

        if self._is_hovered:
            painter.setPen(QPen(QColor(0, 0, 0, 80), 1))
            cx, cy = _BTN_SIZE // 2, _BTN_SIZE // 2
            if self._action == "close":
                painter.drawLine(cx - 3, cy - 3, cx + 3, cy + 3)
                painter.drawLine(cx + 3, cy - 3, cx - 3, cy + 3)
            elif self._action == "minimize":
                painter.drawLine(cx - 3, cy, cx + 3, cy)
            elif self._action == "maximize":
                painter.drawRect(cx - 3, cy - 3, 6, 6)


class CustomTitleBar(QWidget):
    """Barre de titre frameless : wordmark NURU + traffic lights macOS."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CustomTitleBar")
        self.setFixedHeight(38)
        self.setStyleSheet(
            f"#CustomTitleBar {{"
            f"  background-color: {Color.BG_DEEP};"
            f"  border-bottom: 1px solid {Color.BORDER};"
            f"}}"
        )

        self._parent = parent  # MainWindow reference for window operations
        self._drag_pos = QPoint()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, 0, Spacing.MD, 0)
        layout.setSpacing(_TRAFFIC_GAP)

        # Traffic lights (macOS)
        self._close_btn = TitleBarButton("#FF5F57", "#FF3333", "close", self)
        self._close_btn.clicked.connect(self._on_close)
        layout.addWidget(self._close_btn)

        self._min_btn = TitleBarButton("#FEBC2E", "#FFAA00", "minimize", self)
        self._min_btn.clicked.connect(self._on_minimize)
        layout.addWidget(self._min_btn)

        self._max_btn = TitleBarButton("#2AC840", "#00CC33", "maximize", self)
        self._max_btn.clicked.connect(self._on_maximize)
        layout.addWidget(self._max_btn)

        layout.addSpacing(Spacing.MD)

        # Wordmark
        self._title = QLabel("NURU  V16")
        self._title.setStyleSheet(
            f"color: {Color.CYAN}; font-size: 13pt; "
            f"font-family: {Typography.FAMILY_DISPLAY}; font-weight: {Typography.WEIGHT_BOLD};"
            "letter-spacing: 3px; background: transparent;"
        )
        layout.addWidget(self._title)

        layout.addStretch()

    # ── Window actions ──

    def _on_close(self) -> None:
        if self._parent:
            self._parent.close()

    def _on_minimize(self) -> None:
        if self._parent:
            self._parent.showMinimized()

    def _on_maximize(self) -> None:
        if self._parent:
            if self._parent.isMaximized():
                self._parent.showNormal()
            else:
                self._parent.showMaximized()

    # ── Window dragging ──

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() == Qt.MouseButton.LeftButton and self._parent:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self._parent.move(self._parent.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()

    # ── Sous-titre (focus mode) ──

    def set_subtitle(self, text: str) -> None:
        """Ajoute ou modifie le sous-titre du wordmark."""
        current = self._title.text()
        if text:
            self._title.setText(f"NURU  V16  ·  {text}")
        else:
            self._title.setText("NURU  V16")
