"""
NURU V16 — RightInspectorPanel.
Panneau latéral droit : LLM, CPU, RAM, GPU, RAG, Mémoire, Logs.
Masquable, redimensionnable.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QVBoxLayout,
    QWidget,
    QLabel,
    QScrollArea,
    QPushButton,
    QFrame,
)

from src.ui.tokens import Color, Spacing, Typography, Radius


def _section(title: str) -> QWidget:
    """Crée une section du panneau droit."""
    frame = QFrame()
    frame.setObjectName("InspectorSection")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
    layout.setSpacing(4)

    label = QLabel(title)
    label.setObjectName("InspectorLabel")
    layout.addWidget(label)

    value = QLabel("—")
    value.setObjectName("InspectorValue")

    @property  # noqa: B021
    def set_text(t):
        value.setText(t)

    value.set_text = lambda t: value.setText(t)
    layout.addWidget(value)

    return frame


class RightInspectorPanel(QWidget):
    """Panneau d'inspection droite — état NURU en temps réel."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("RightInspectorPanel")
        self.setFixedWidth(280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.LG, Spacing.SM, Spacing.LG)
        layout.setSpacing(Spacing.MD)

        # Titre
        title = QLabel("Inspecteur")
        title.setStyleSheet(
            f"color: {Color.CYAN}; font-size: {Typography.SIZE_CAPTION}pt; "
            f"font-family: {Typography.FAMILY_DISPLAY}; font-weight: {Typography.WEIGHT_BOLD}; "
            "letter-spacing: 2px; text-transform: uppercase;"
        )
        layout.addWidget(title)

        # Sections dans un scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(Spacing.SM)

        sections = [
            ("state", "État NURU"),
            ("model", "Modèle actif"),
            ("cpu", "CPU"),
            ("ram", "RAM"),
            ("gpu", "GPU"),
            ("rag", "RAG"),
            ("memory", "Mémoire"),
            ("logs", "Logs"),
        ]

        self._section_labels: dict[str, QLabel] = {}
        for key, label_text in sections:
            section = _section(label_text)
            label = section.findChild(QLabel, "InspectorValue")
            self._section_labels[key] = label
            content_layout.addWidget(section)

        content_layout.addStretch()
        scroll.setWidget(content)

        layout.addWidget(scroll, stretch=1)

        # Bouton masquer
        self._hide_btn = QPushButton("◀ Masquer")
        self._hide_btn.setObjectName("GhostButton")
        self._hide_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hide_btn.setStyleSheet(
            f"color: {Color.TEXT_MUTED}; font-size: {Typography.SIZE_CAPTION}pt; "
            "border: none; padding: 4px;"
        )

        layout.addWidget(self._hide_btn)

    def update_value(self, key: str, value: str) -> None:
        """Met à jour une valeur affichée."""
        label = self._section_labels.get(key)
        if label:
            label.setText(value)

    def update_snapshot(self, snap: dict[str, str]) -> None:
        """Met à jour toutes les valeurs depuis un snapshot."""
        for key, value in snap.items():
            self.update_value(key, value)

    def set_hide_callback(self, callback) -> None:
        """Associe le bouton masquer à la fonction de callback."""
        self._hide_btn.clicked.connect(callback)
