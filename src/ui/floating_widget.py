"""
NURU V12 — NuruFloatingWidget (Z.ai design).

Widget always-on-top, drag-and-drop, 160×160px.

Comportement :
- Qt.Tool | FramelessWindowHint | WindowStaysOnTopHint
- Opacité → 0.4 après 30s inactivité → 1.0 au hover
- Drag-and-drop libre
- Mini-Orb (80px) qui reflète l'état NURU
"""

import logging

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Property, QPoint
from PySide6.QtGui import QPainter, QColor, QEnterEvent, QMouseEvent
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from src.ui.tokens import Color, Typography, Radius, Spacing, OrbSizes, AnimDuration
from src.ui.presence_orb import NuruPresenceOrb, OrbState

logger = logging.getLogger(__name__)


class NuruFloatingWidget(QWidget):
    """
    Widget flottant always-on-top, drag-and-drop.

    Taille : 160×160 px (mini-Orb 80 px centré)
    Opacité :
      - Active : 1.0
      - Après 30s inactivité : 0.4
      - Retour 1.0 au hover
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_pos = None
        self._inactive = False

        # Fenêtre frameless always-on-top
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(160, 160)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        layout.setAlignment(Qt.AlignCenter)

        # Mini-Orb
        self._orb = NuruPresenceOrb(orb_size=OrbSizes.FLOATING)
        layout.addWidget(self._orb, alignment=Qt.AlignCenter)

        # Label subtil
        label = QLabel("NURU")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(f"""
            color: {Color.TEXT_SECONDARY};
            font-size: {Typography.SIZE_ORB_LABEL}px;
            font-family: {Typography.FAMILY_BODY};
            background: transparent;
        """)
        layout.addWidget(label)

        # Animation d'opacité
        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(500)
        self._opacity_anim.setEasingCurve(QEasingCurve.OutCubic)

        # Timer d'inactivité
        self._inactivity_timer = QTimer(self)
        self._inactivity_timer.setSingleShot(True)
        self._inactivity_timer.setInterval(AnimDuration.FLOATING_FADE)
        self._inactivity_timer.timeout.connect(self._fade_out)

        # Démarrer le timer d'inactivité
        self._reset_inactivity_timer()

    # ── API publique ────────────────────────────────────────────────

    @property
    def orb(self) -> NuruPresenceOrb:
        return self._orb

    def set_orb_state(self, state: OrbState, progress: float = 0.0):
        """Change l'état de l'Orb et réveille le widget."""
        self._orb.set_state(state, progress)
        self._wake()

    def _wake(self):
        """Remet l'opacité à 1.0 et réinitialise le timer."""
        if self._inactive:
            self._inactive = False
            self._opacity_anim.setStartValue(0.4)
            self._opacity_anim.setEndValue(1.0)
            self._opacity_anim.start()
        self._reset_inactivity_timer()

    def _fade_out(self):
        """Opacité → 0.4 après inactivité."""
        self._inactive = True
        self._opacity_anim.setStartValue(1.0)
        self._opacity_anim.setEndValue(0.4)
        self._opacity_anim.start()

    def _reset_inactivity_timer(self):
        self._inactivity_timer.stop()
        self._inactivity_timer.start()

    # ── Drag & Drop ────────────────────────────────────────────────

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

    # ── Hover ──────────────────────────────────────────────────────

    def enterEvent(self, event: QEnterEvent):
        self._wake()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._reset_inactivity_timer()
        super().leaveEvent(event)

    # ── Rendu boîte arrondie ───────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Fond arrondi
        rect = self.rect().adjusted(2, 2, -2, -2)
        painter.setBrush(QColor(Color.BG_OVERLAY))
        painter.setPen(QColor(Color.BORDER))
        painter.drawRoundedRect(rect, Radius.LARGE, Radius.LARGE)

        painter.end()
