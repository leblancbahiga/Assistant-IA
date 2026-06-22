"""
NURU V12 — NuruFloatingWidget (Z.ai design exact).

Widget flottant always-on-top, drag-and-drop.
Taille Z.ai : 220×160 px — Frosted glass effect.

Comportement :
  - Qt.Tool | FramelessWindowHint | WindowStaysOnTopHint
  - Opacité → 0.4 après 30s inactivité → 1.0 au hover
  - Mini-Orb (80px) + label NURU
  - Effet verre dépoli simulé (QPainter, pas de QGraphicsBlurEffect)
"""

import logging
import math

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Property, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QLinearGradient, QPen, QEnterEvent, QMouseEvent, QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QApplication

from src.ui.tokens import Color, Typography, Radius, Spacing, OrbSizes, AnimDuration, WindowSizes
from src.ui.presence_orb import NuruPresenceOrb, OrbState

logger = logging.getLogger(__name__)


class NuruFloatingWidget(QWidget):
    """
    FloatingWidget 220×160 — verre dépoli.

    Z.ai spec :
      - 220×160 px
      - Frosted glass effect (QPainter simulated)
      - Qt.Tool | FramelessWindowHint | WindowStaysOnTopHint
      - Opacity 0.4 after 30s → 1.0 on hover
      - Drag-and-drop libre
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_pos = None
        self._inactive = False

        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(WindowSizes.FLOATING_SIZE, WindowSizes.FLOATING_SIZE)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(Spacing.XS)

        # Mini-Orb
        self._orb = NuruPresenceOrb(orb_size=OrbSizes.FLOATING)
        layout.addWidget(self._orb, alignment=Qt.AlignCenter)

        # Label
        label = QLabel("NURU")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(f"""
            color: {Color.TEXT_SECONDARY};
            font-size: {Typography.SIZE_ORB_LABEL}px;
            font-family: {Typography.FAMILY_BODY};
            font-weight: {Typography.WEIGHT_MEDIUM};
            background: transparent;
            letter-spacing: 2px;
        """)
        layout.addWidget(label)

        # Opacité animation
        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(500)
        self._opacity_anim.setEasingCurve(QEasingCurve.OutCubic)

        # Inactivity timer
        self._inactivity_timer = QTimer(self)
        self._inactivity_timer.setSingleShot(True)
        self._inactivity_timer.setInterval(AnimDuration.FLOATING_FADE)
        self._inactivity_timer.timeout.connect(self._fade_out)

        self._reset_timer()

    # ── API ──

    @property
    def orb(self) -> NuruPresenceOrb:
        return self._orb

    def set_orb_state(self, state: OrbState, progress: float = 0.0):
        self._orb.set_state(state, progress)
        self._wake()

    def _wake(self):
        if self._inactive:
            self._inactive = False
            self._opacity_anim.setStartValue(0.4)
            self._opacity_anim.setEndValue(1.0)
            self._opacity_anim.start()
        self._reset_timer()

    def _fade_out(self):
        self._inactive = True
        self._opacity_anim.setStartValue(1.0)
        self._opacity_anim.setEndValue(0.4)
        self._opacity_anim.start()

    def _reset_timer(self):
        self._inactivity_timer.stop()
        self._inactivity_timer.start()

    # ── Drag ──

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._wake()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Double-clic → éveil (placeholder pour action)."""
        self._wake()
        super().mouseDoubleClickEvent(event)

    # ── Hover ──

    def enterEvent(self, event: QEnterEvent):
        self._wake()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._reset_timer()
        super().leaveEvent(event)

    # ── Frosted glass QPainter (pas de QGraphicsBlurEffect) ──

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(2, 2, -2, -2)
        r = Radius.LARGE

        # Fond verre dépoli — gradient semi-transparent
        gradient = QLinearGradient(QPointF(0, 0), QPointF(0, rect.height()))
        gradient.setColorAt(0.0, QColor("rgba(13, 17, 23, 0.75)"))
        gradient.setColorAt(0.5, QColor("rgba(13, 17, 23, 0.85)"))
        gradient.setColorAt(1.0, QColor("rgba(13, 17, 23, 0.90)"))
        painter.setBrush(gradient)

        # Bordure cyan subtile
        border = QPen(QColor(Color.BORDER))
        border.setWidth(1)
        painter.setPen(border)
        painter.drawRoundedRect(rect, r, r)

        # Reflet haut (glass shine)
        shine_rect = QRectF(rect.x() + 8, rect.y() + 4, rect.width() - 16, rect.height() * 0.35)
        shine = QLinearGradient(QPointF(0, shine_rect.top()), QPointF(0, shine_rect.bottom()))
        shine.setColorAt(0.0, QColor("rgba(255, 255, 255, 0.06)"))
        shine.setColorAt(1.0, QColor("rgba(255, 255, 255, 0.00)"))
        painter.setBrush(shine)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(shine_rect, r - 2, r - 2)

        painter.end()
