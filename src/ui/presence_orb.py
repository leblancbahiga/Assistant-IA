"""
NURU V12 — NuruPresenceOrb (Z.ai design).

Cœur visuel de l'interface. 7 états animés via QPainter :
idle → listening → thinking → respond → speaking → acting → error

Contrainte M1 8 Go : QPainter only, pas de QGraphicsBlurEffect,
pas de 3D, CPU < 5% par animation, single-level shadows.
"""

import math
import logging
from enum import Enum

from PySide6.QtCore import (
    Qt, QTimer, QPointF, QRectF, QPropertyAnimation, QEasingCurve,
    Property, Signal,
)
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QRadialGradient, QPen, QFont,
    QLinearGradient, QConicalGradient,
)
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from src.ui.tokens import Color, OrbSizes, AnimDuration, Typography

logger = logging.getLogger(__name__)


class OrbState(str, Enum):
    """Les 7 états du PresenceOrb — cycle voix + action."""
    IDLE = "idle"           # Respiration lente
    LISTENING = "listening"  # Ondes sonores (3 cercles concentriques)
    THINKING = "thinking"   # Halo rotatif cyan
    RESPOND = "respond"     # Pulse accéléré
    SPEAKING = "speaking"   # Particules volume TTS
    ACTING = "acting"       # Anneau de progression
    ERROR = "error"         # Clignotant rouge


class NuruPresenceOrb(QWidget):
    """
    Présence animée de NURU.

    Tailles :
      - 120 px (fenêtre principale)
      - 200 px (VoiceOverlay)
      - 80 px  (FloatingWidget)

    Signaux :
      - state_changed(OrbState) — quand l'état change
    """

    state_changed = Signal(OrbState)

    # ── Propriétés animables ────────────────────────────────────────

    def _get_pulse(self) -> float:
        return self._pulse_value

    def _set_pulse(self, val: float):
        self._pulse_value = max(0.8, min(1.0, val))
        self.update()

    pulse_value = Property(float, _get_pulse, _set_pulse)

    def _get_halo_angle(self) -> float:
        return self._halo_angle

    def _set_halo_angle(self, val: float):
        self._halo_angle = val % 360.0
        self.update()

    halo_angle = Property(float, _get_halo_angle, _set_halo_angle)

    # ── Init ────────────────────────────────────────────────────────

    def __init__(self, parent=None, orb_size: int = OrbSizes.WINDOW):
        super().__init__(parent)
        self._state = OrbState.IDLE
        self._orb_size = orb_size
        self._pulse_value = 1.0
        self._halo_angle = 0.0
        self._progress = 0.0       # 0→1.0 pour acting
        self._opacity = 1.0
        self._blink_visible = True

        self.setFixedSize(orb_size, orb_size)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Animations
        self._pulse_anim = QPropertyAnimation(self, b"pulse_value")
        self._pulse_anim.setDuration(AnimDuration.ORB_PULSE)
        self._pulse_anim.setStartValue(0.85)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._pulse_anim.setLoopCount(-1)  # infini

        self._halo_anim = QPropertyAnimation(self, b"halo_angle")
        self._halo_anim.setDuration(AnimDuration.ORB_HALO_SPIN)
        self._halo_anim.setStartValue(0.0)
        self._halo_anim.setEndValue(360.0)
        self._halo_anim.setEasingCurve(QEasingCurve.Linear)
        self._halo_anim.setLoopCount(-1)

        # Clignotement erreur
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._toggle_blink)

        # Démarrer idle
        self._apply_idle()

    # ── API publique ─────────────────────────────────────────────────

    @property
    def state(self) -> OrbState:
        return self._state

    def set_state(self, new_state: OrbState, progress: float = 0.0):
        """Change l'état de l'Orb. Coupe l'animation précédente."""
        if self._state == new_state:
            if new_state == OrbState.ACTING:
                self._progress = progress
                self.update()
            return

        # Stopper tout
        self._stop_all()
        self._state = new_state
        self._progress = progress
        self._opacity = 1.0
        self._blink_visible = True
        self._blink_timer.stop()

        # Appliquer le nouvel état
        handler = {
            OrbState.IDLE: self._apply_idle,
            OrbState.THINKING: self._apply_thinking,
            OrbState.ACTING: self._apply_acting,
            OrbState.ERROR: self._apply_error,
            OrbState.LISTENING: self._apply_listening,
            OrbState.RESPOND: self._apply_respond,
            OrbState.SPEAKING: self._apply_speaking,
        }.get(new_state, self._apply_idle)

        handler()
        self.state_changed.emit(new_state)
        logger.debug(f"Orb → {new_state.value}")

    def set_progress(self, pct: float):
        """Met à jour l'anneau de progression (état acting)."""
        self._progress = max(0.0, min(1.0, pct))
        self.update()

    def set_orb_size(self, size: int):
        self._orb_size = size
        self.setFixedSize(size, size)

    # ── États ────────────────────────────────────────────────────────

    def _apply_idle(self):
        """Respiration lente — pulse 0.85→1.0 en 4s InOutSine."""
        self._pulse_anim.setDuration(AnimDuration.ORB_PULSE)
        self._pulse_anim.setStartValue(0.85)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.start()

    def _apply_thinking(self):
        """Halo rotatif — arc 270° cyan en 3s."""
        self._halo_anim.setDuration(AnimDuration.ORB_HALO_SPIN)
        self._halo_anim.start()
        # Aussi un léger pulse
        self._pulse_anim.setDuration(AnimDuration.ORB_PULSE)
        self._pulse_anim.setStartValue(0.92)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.start()

    def _apply_respond(self):
        """Pulse accéléré — 1.5s au lieu de 4s."""
        self._pulse_anim.setDuration(AnimDuration.ORB_PULSE_ACCEL)
        self._pulse_anim.setStartValue(0.88)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.start()

    def _apply_listening(self):
        """Écoute — pulse régulier + 3 ondes (simulé par halo lent)."""
        self._halo_anim.setDuration(2000)
        self._halo_anim.start()
        self._pulse_anim.setDuration(AnimDuration.ORB_PULSE_ACCEL)
        self._pulse_anim.setStartValue(0.90)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.start()

    def _apply_speaking(self):
        """Parole — pulse rapide irrégulier simulé."""
        self._pulse_anim.setDuration(600)
        self._pulse_anim.setStartValue(0.95)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.start()

    def _apply_acting(self):
        """Action — scale 0.85 + anneau progression."""
        self._pulse_anim.setDuration(AnimDuration.ORB_PULSE)
        self._pulse_anim.setStartValue(0.85)
        self._pulse_anim.setEndValue(0.90)
        self._pulse_anim.start()

    def _apply_error(self):
        """Clignotant rouge — alternance 500ms."""
        self._blink_timer.start()

    def _stop_all(self):
        self._pulse_anim.stop()
        self._halo_anim.stop()
        self._blink_timer.stop()

    def _toggle_blink(self):
        self._blink_visible = not self._blink_visible
        self.update()

    # ── Rendu QPainter ───────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        center = QPointF(self.width() / 2, self.height() / 2)
        radius = self._orb_size / 2 * self._pulse_value

        if self._state == OrbState.ERROR and not self._blink_visible:
            painter.setOpacity(0.2)

        painter.setOpacity(painter.opacity() * self._opacity)

        # ── Glow externe (ombre single-level) ──
        glow = QRadialGradient(center, radius * 1.3)
        glow.setColorAt(0.0, QColor(Color.CYAN + "40"))  # 25% opacity
        glow.setColorAt(1.0, QColor(Color.CYAN + "00"))
        painter.setBrush(glow)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, radius * 1.3, radius * 1.3)

        # ── Cercle principal ──
        base_color = Color.ERROR if self._state == OrbState.ERROR else Color.CYAN
        painter.setBrush(QColor(base_color))
        painter.setPen(QPen(QColor(Color.TEXT_PRIMARY + "30"), 1))
        painter.drawEllipse(center, radius, radius)

        # ── Halo rotatif (thinking) ──
        if self._state in (OrbState.THINKING, OrbState.LISTENING):
            self._draw_halo(painter, center, radius)

        # ── Anneau de progression (acting) ──
        if self._state == OrbState.ACTING and self._progress > 0:
            self._draw_progress_ring(painter, center, radius)

        painter.end()

    # ── Sous-rendus ──────────────────────────────────────────────────

    def _draw_halo(self, painter: QPainter, center: QPointF, radius: float):
        """Arc 270° rotatif — dégradé radial cyan."""
        path = QPainterPath()
        arc_radius = radius * 1.15
        rect = QRectF(
            center.x() - arc_radius,
            center.y() - arc_radius,
            arc_radius * 2,
            arc_radius * 2,
        )
        start_angle = int(self._halo_angle * 16)  # QPainter uses 1/16th degree
        span = 270 * 16
        path.arcMoveTo(rect, self._halo_angle)
        path.arcTo(rect, self._halo_angle, 270)

        pen = QPen(QColor(Color.CYAN_LIGHT + "60"), 3)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

    def _draw_progress_ring(self, painter: QPainter, center: QPointF, radius: float):
        """Anneau de progression clockwise — QPainter::drawArc."""
        ring_radius = radius * 0.85
        rect = QRectF(
            center.x() - ring_radius,
            center.y() - ring_radius,
            ring_radius * 2,
            ring_radius * 2,
        )
        angle = int(360 * self._progress * 16)
        pen = QPen(QColor(Color.CYAN), 3)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 90 * 16, -angle)  # start at top, clockwise
