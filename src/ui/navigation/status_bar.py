"""
NURU V16 — StatusBar.
Barre d'état en bas : mode, latence, version.
"""

from __future__ import annotations

from PySide6.QtWidgets import QStatusBar, QLabel
from PySide6.QtCore import Qt

from src.ui.tokens import Typography


class StatusBar(QStatusBar):
    """Barre de statut unifiée — mode + latence + version."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusBar")

        self._mode_label = QLabel("● local_only")
        self._mode_label.setObjectName("StatusBarLabel")

        self._latency_label = QLabel("réponse moy. —")
        self._latency_label.setObjectName("StatusBarLabel")

        self._version_label = QLabel("v16.0")
        self._version_label.setObjectName("StatusBarLabel")

        # Alignement
        self._mode_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._latency_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._version_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.addWidget(self._mode_label, 1)
        self.addWidget(self._latency_label, 2)
        self.addPermanentWidget(self._version_label)

        self._mode_label.setStyleSheet(f"color: #00FFAA; font-size: {Typography.SIZE_CAPTION}pt;")
        self._latency_label.setStyleSheet(
            f"color: {Typography.SIZE_CAPTION if False else '#8BA0C8'}; font-size: {Typography.SIZE_CAPTION}pt;"
        )
        self._version_label.setStyleSheet(f"color: rgba(139, 160, 200, 0.45); font-size: {Typography.SIZE_CAPTION}pt;")

    def set_mode(self, mode: str) -> None:
        self._mode_label.setText(f"● {mode}")

    def set_latency(self, latency_s: float) -> None:
        self._latency_label.setText(f"réponse moy. {latency_s:.1f}s")

    def set_version(self, version: str) -> None:
        self._version_label.setText(version)
