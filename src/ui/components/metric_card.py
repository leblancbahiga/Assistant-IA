from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt


class MetricCard(QFrame):
    """Carte de métrique V4.0 avec sparkline."""
    
    def __init__(self, title: str, initial_value: str, parent=None):
        super().__init__(parent)
        self.setObjectName("MetricCard")
        self.setFixedHeight(65)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        
        # Titre
        header = QHBoxLayout()
        self.title_label = QLabel(title.upper())
        self.title_label.setObjectName("MetricTitle")
        header.addWidget(self.title_label)
        header.addStretch()
        layout.addLayout(header)
        
        # Valeur
        self._value_label = QLabel(initial_value)
        self._value_label.setObjectName("MetricValue")
        layout.addWidget(self._value_label)
        
        self._spark_label = QLabel("▁▁▁▁")
        self._spark_label.setObjectName("MetricSparkline")
        layout.addWidget(self._spark_label)
        
        layout.addStretch()

    def set_value(self, value: str):
        self._value_label.setText(value)

    def set_value_color(self, color_hex: str):
        self._value_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {color_hex};")
