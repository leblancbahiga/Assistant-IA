"""Jauge RAM circulaire avec gradient violet→cyan et texte centré X.XG + RAM."""
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QBrush, QConicalGradient
from PySide6.QtCore import Qt, QRectF, QPropertyAnimation, QEasingCurve, Property


class CircularGauge(QWidget):
    """Jauge circulaire type Aether — gradient #a855f7 → #00d4ff, texte X.XG + RAM."""

    def __init__(self, size=130, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._value = 0.0          # 0.0 → 1.0
        self._value_gb = "0.0"
        self._total_gb = "0.0"
        self._anim_value = 0.0

        # Animation de progression
        self._animation = QPropertyAnimation(self, b"anim_value")
        self._animation.setDuration(600)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)

    # ── Property animée ──
    def _get_anim_value(self):
        return self._anim_value

    def _set_anim_value(self, val):
        self._anim_value = val
        self.update()

    anim_value = Property(float, _get_anim_value, _set_anim_value)

    def set_value(self, value: float, used_gb: str = None, total_gb: str = None):
        self._value = max(0.0, min(1.0, value))
        if used_gb is not None:
            self._value_gb = used_gb
        if total_gb is not None:
            self._total_gb = total_gb

        self._animation.stop()
        self._animation.setStartValue(self._anim_value)
        self._animation.setEndValue(self._value)
        self._animation.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        s = self.width()
        thickness = 8
        margin = thickness / 2 + 6
        rect = QRectF(margin, margin, s - 2 * margin, s - 2 * margin)
        center = self.rect().center()

        # ── Track (cercle gris foncé) ──
        pen_track = QPen(QColor("#1e1e3a"))
        pen_track.setWidth(thickness)
        pen_track.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_track)
        painter.drawArc(rect, 0, 360 * 16)

        # ── Arc de progression avec gradient conique ──
        gradient = QConicalGradient(center, 90)
        gradient.setColorAt(0.0, QColor("#a855f7"))   # violet
        gradient.setColorAt(0.5, QColor("#d946ef"))   # magenta
        gradient.setColorAt(1.0, QColor("#00d4ff"))   # cyan

        pen_progress = QPen(QBrush(gradient), thickness)
        pen_progress.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_progress)

        span_angle = int(-self._anim_value * 360 * 16)
        start_angle = 90 * 16
        painter.drawArc(rect, start_angle, span_angle)

        # ── Texte central : "3.1G" ──
        font_main = QFont("SF Mono", max(14, int(s / 5.2)))
        font_main.setBold(True)
        painter.setFont(font_main)
        painter.setPen(QColor("#FFFFFF"))

        fm = painter.fontMetrics()
        text_h = fm.height()

        value_rect = QRectF(0, s / 2 - text_h - 2, s, text_h + 4)
        painter.drawText(value_rect, Qt.AlignCenter, f"{self._value_gb}G")

        # ── "RAM" en gris ──
        font_sub = QFont("SF Mono", max(10, int(s / 11)))
        font_sub.setBold(False)
        painter.setFont(font_sub)
        painter.setPen(QColor("#6b7280"))

        sub_rect = QRectF(0, s / 2 + 4, s, int(s / 8))
        painter.drawText(sub_rect, Qt.AlignCenter, "RAM")
