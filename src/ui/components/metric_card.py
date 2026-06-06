"""Carte métrique compacte avec icône, titre, valeur et couleur d'accent."""
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt


class MetricCard(QFrame):
    """Carte métrique style Aether — icône + titre + valeur colorée."""

    def __init__(self, title: str, value: str, icon: str = "◆", accent_color: str = "#a855f7", parent=None):
        super().__init__(parent)
        self.setObjectName("AetherMetricCard")
        self.setFixedHeight(78)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # Ligne titre avec icône
        header = QHBoxLayout()
        header.setSpacing(6)

        self.icon_label = QLabel(icon)
        self.icon_label.setStyleSheet(
            f"color: {accent_color}; font-size: 12px;"
        )
        header.addWidget(self.icon_label)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            f"color: #6b7280; font-size: 9px; font-weight: bold; letter-spacing: 1px;"
        )
        header.addWidget(self.title_label)
        header.addStretch()
        layout.addLayout(header)

        # Valeur
        self._value_label = QLabel(value)
        self._value_label.setStyleSheet(
            f"color: {accent_color}; font-size: 18px; font-weight: bold;"
        )
        layout.addWidget(self._value_label)

    def set_value(self, value: str):
        self._value_label.setText(value)

    def set_value_color(self, color_hex: str):
        self._value_label.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {color_hex};"
        )

    def set_value_and_color(self, value: str, color_hex: str):
        self._value_label.setText(value)
        self._value_label.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {color_hex};"
        )
