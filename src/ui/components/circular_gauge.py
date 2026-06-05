from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QRadialGradient
from PySide6.QtCore import Qt, QRectF


class CircularGauge(QWidget):
    """Jauge circulaire V4.0 avec gradient et texte centré."""
    
    def __init__(self, size=60, track_color="#1F2937", progress_color="#00F2FF", thickness=5, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.value = 0.0
        self.text = "0%"
        self.track_color = QColor(track_color)
        self.progress_color = QColor(progress_color)
        self.thickness = thickness

    def set_value(self, value: float, text: str = None):
        self.value = max(0.0, min(1.0, value))
        self.text = text if text is not None else f"{int(self.value * 100)}%"
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = QRectF(
            self.thickness / 2,
            self.thickness / 2,
            self.width() - self.thickness,
            self.height() - self.thickness
        )

        # Track
        pen_track = QPen(self.track_color)
        pen_track.setWidth(self.thickness)
        pen_track.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_track)
        painter.drawArc(rect, 0, 360 * 16)

        # Progress avec gradient
        pen_progress = QPen(self.progress_color)
        pen_progress.setWidth(self.thickness)
        pen_progress.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_progress)
        
        span_angle = int(-self.value * 360 * 16)
        start_angle = 90 * 16
        painter.drawArc(rect, start_angle, span_angle)

        # Texte central
        painter.setPen(QColor("#F3F4F6"))
        font = QFont("Inter", int(self.height() / 4.5))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, self.text)
