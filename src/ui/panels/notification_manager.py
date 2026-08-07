"""
NURU V16 — NotificationManager.
File d'événements système + popup de notification.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QWidget, QScrollArea,
)

from src.ui.tokens import Color, Typography, Spacing, Radius

logger = logging.getLogger(__name__)


class Severity(Enum):
    INFO = auto()
    SUCCESS = auto()
    WARNING = auto()
    ERROR = auto()


_SEVERITY_COLORS = {
    Severity.INFO: Color.CYAN,
    Severity.SUCCESS: Color.GREEN,
    Severity.WARNING: Color.AMBER,
    Severity.ERROR: Color.ROSE,
}


@dataclass
class NotificationEvent:
    """Un événement de notification."""
    message: str
    severity: Severity = Severity.INFO
    source: str = "système"
    timestamp: float = field(default_factory=time.time)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.timestamp


class NotificationManager(QObject):
    """Gère la file de notifications et expose une popup UI."""

    new_notification = Signal(object)  # NotificationEvent

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._events: list[NotificationEvent] = []
        self._max_events = 50

    # ── API ──

    def notify(
        self,
        message: str,
        severity: Severity = Severity.INFO,
        source: str = "système",
    ) -> None:
        """Ajoute une notification."""
        event = NotificationEvent(message=message, severity=severity, source=source)
        self._events.append(event)
        if len(self._events) > self._max_events:
            self._events.pop(0)
        self.new_notification.emit(event)
        logger.debug(f"🔔 {severity.name}: {message}")

    @property
    def recent(self) -> list[NotificationEvent]:
        return list(self._events)

    def build_popup(self, parent: QWidget) -> NotificationPopup:
        """Construit le widget popup attaché à un parent."""
        popup = NotificationPopup(parent, self)
        return popup


class NotificationPopup(QFrame):
    """Popup flottant listant les notifications récentes."""

    def __init__(self, parent: QWidget, manager: NotificationManager):
        super().__init__(parent)
        self._manager = manager
        self.setObjectName("NotificationPopup")
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(320, 350)
        self.setStyleSheet(
            f"#NotificationPopup {{"
            f"  background-color: {Color.BG_SURFACE1};"
            f"  border: 1px solid {Color.BORDER};"
            f"  border-radius: {Radius.MEDIUM}px;"
            f"}}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.SM)

        header = QLabel("🔔 Notifications")
        header.setStyleSheet(
            f"color: {Color.TEXT_PRIMARY}; font-size: {Typography.SIZE_CAPTION}pt;"
            f"font-weight: {Typography.WEIGHT_BOLD};"
        )
        layout.addWidget(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._inner = QWidget()
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.setSpacing(4)
        self._inner_layout.addStretch()
        self._scroll.setWidget(self._inner)

        layout.addWidget(self._scroll, stretch=1)

        clear_btn = QPushButton("Tout effacer")
        clear_btn.setStyleSheet(
            f"color: {Color.TEXT_MUTED}; font-size: {Typography.SIZE_CAPTION}pt; "
            f"border: none; padding: 4px;"
        )
        clear_btn.clicked.connect(self._clear)
        layout.addWidget(clear_btn)

        self._rebuild()

        # Se met à jour automatiquement
        manager.new_notification.connect(self._on_new)

    def _rebuild(self) -> None:
        """Reconstruit la liste des notifications dans le scroll."""
        # Vider (garder le stretch final)
        while self._inner_layout.count() > 1:
            item = self._inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for evt in reversed(self._manager.recent[-20:]):
            row = QFrame()
            row.setStyleSheet("background: transparent;")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(Spacing.XS, 2, Spacing.XS, 2)

            dot = QLabel("●")
            dot_color = _SEVERITY_COLORS.get(evt.severity, Color.TEXT_MUTED)
            dot.setStyleSheet(f"color: {dot_color}; font-size: 6pt;")
            row_layout.addWidget(dot)

            msg = QLabel(evt.message)
            msg.setWordWrap(True)
            msg.setStyleSheet(
                f"color: {Color.TEXT_SECONDARY}; font-size: {Typography.SIZE_CAPTION}pt;"
            )
            row_layout.addWidget(msg, stretch=1)

            self._inner_layout.insertWidget(self._inner_layout.count() - 1, row)

    def _on_new(self, event: NotificationEvent) -> None:
        self._rebuild()

    def _clear(self) -> None:
        self._manager._events.clear()
        self._rebuild()
