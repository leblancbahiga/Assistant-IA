"""
NURU V12 — NuruPresenceOrb (Z.ai design exact).

Cœur visuel de l'interface. Sphere cyan translucide avec halo radial doux
et GlowRing (anneau lumineux concentrique).

7 états : idle → listening → thinking → respond → speaking → acting → error

Contrainte M1 8 Go : QPainter only, pas de QGraphicsBlurEffect,
pas de 3D, CPU < 5% par animation, single-level shadows.
"""

import math
import logging
from enum import Enum

from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, QPropertyAnimation, QEasingCurve, Property, Signal
from PySide6.QtGui import QPainter, QPainterPath, QColor, QRadialGradient, QPen, QFont
from PySide6.QtWidgets import QWidget

from src.ui.tokens import Color, OrbSizes, AnimDuration

logger = logging.getLogger(__name__)


class OrbState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    RESPOND = "respond"
    SPEAKING = "speaking"
    ACTING = "acting"
    ERROR = "error"


class NuruPresenceOrb(QWidget):
    """
    PresenceOrb — Sphere cyan translucide avec GlowRing.

    Tailles Z.ai :
      - 120 px (ambiance)
      - 200 px (VoiceOverlay)
      - 80 px  (FloatingWidget)

    Composants :
      - GlowRing : anneau lumineux concentrique (QRadialGradient)
      - Core : cercle central cyan translucide
      - Halo externe : soft radial glow
    """

    state_changed = Signal(OrbState)

    # ── Propriétés animables ──

    def _get_pulse(self) -> float:
        return self._pulse_value

    def _set_pulse(self, val: float):
        self._pulse_value = max(0.80, min(1.0, val))
        self.update()

    pulse_value = Property(float, _get_pulse, _set_pulse)

    def _get_halo_angle(self) -> float:
        return self._halo_angle

    def _set_halo_angle(self, val: float):
        self._halo_angle = val % 360.0
        self.update()

    halo_angle = Property(float, _get_halo_angle, _set_halo_angle)

    def __init__(self, parent=None, orb_size: int = OrbSizes.WINDOW):
        super().__init__(parent)
        self._state = OrbState.IDLE
        self._orb_size = orb_size
        self._pulse_value = 1.0
        self._halo_angle = 0.0
        self._progress = 0.0
        self._opacity = 1.0
        self._blink_visible = True

        self.setFixedSize(orb_size, orb_size)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Animations
        self._pulse_anim = QPropertyAnimation(self, b"pulse_value")
        self._pulse_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._pulse_anim.setLoopCount(-1)

        self._halo_anim = QPropertyAnimation(self, b"halo_angle")
        self._halo_anim.setDuration(AnimDuration.ORB_HALO_SPIN)
        self._halo_anim.setStartValue(0.0)
        self._halo_anim.setEndValue(360.0)
        self._halo_anim.setEasingCurve(QEasingCurve.Linear)
        self._halo_anim.setLoopCount(-1)

        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._toggle_blink)

        self._apply_idle()

    # ── API ──

    @property
    def state(self) -> OrbState:
        return self._state

    def set_state(self, new_state: OrbState, progress: float = 0.0):
        if self._state == new_state:
            if new_state == OrbState.ACTING:
                self._progress = progress
                self.update()
            return

        self._stop_all()
        self._state = new_state
        self._progress = progress
        self._opacity = 1.0
        self._blink_visible = True
        self._blink_timer.stop()

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

    def set_progress(self, pct: float):
        self._progress = max(0.0, min(1.0, pct))
        self.update()

    def set_orb_size(self, size: int):
        self._orb_size = size
        self.setFixedSize(size, size)

    # ── États ──

    def _apply_idle(self):
        """Respiration lente 0.85↔1.0 en 4s — Z.ai."""
        self._pulse_anim.setDuration(AnimDuration.ORB_PULSE)
        self._pulse_anim.setStartValue(0.85)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.start()

    def _apply_thinking(self):
        """Halo rotatif 3s + léger pulse."""
        self._halo_anim.setDuration(AnimDuration.ORB_HALO_SPIN)
        self._halo_anim.start()
        self._pulse_anim.setDuration(AnimDuration.ORB_PULSE)
        self._pulse_anim.setStartValue(0.92)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.start()

    def _apply_respond(self):
        """Pulse accéléré 1.5s."""
        self._pulse_anim.setDuration(AnimDuration.ORB_PULSE_ACCEL)
        self._pulse_anim.setStartValue(0.88)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.start()

    def _apply_listening(self):
        """Pulse régulier + halo lent (simule 3 ondes)."""
        self._halo_anim.setDuration(2000)
        self._halo_anim.start()
        self._pulse_anim.setDuration(AnimDuration.ORB_PULSE_ACCEL)
        self._pulse_anim.setStartValue(0.90)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.start()

    def _apply_speaking(self):
        """Pulse rapide irrégulier."""
        self._pulse_anim.setDuration(600)
        self._pulse_anim.setStartValue(0.95)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.start()

    def _apply_acting(self):
        """Scale 0.85 + anneau progression."""
        self._pulse_anim.setDuration(AnimDuration.ORB_PULSE)
        self._pulse_anim.setStartValue(0.85)
        self._pulse_anim.setEndValue(0.90)
        self._pulse_anim.start()

    def _apply_error(self):
        self._blink_timer.start()

    def _stop_all(self):
        self._pulse_anim.stop()
        self._halo_anim.stop()
        self._blink_timer.stop()

    def _toggle_blink(self):
        self._blink_visible = not self._blink_visible
        self.update()

    # ── Rendu QPainter — Z.ai exact ──

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        center = QPointF(self.width() / 2, self.height() / 2)
        radius = self._orb_size / 2 * self._pulse_value

        if self._state == OrbState.ERROR and not self._blink_visible:
            painter.setOpacity(0.2)

        painter.setOpacity(painter.opacity() * self._opacity)

        r = radius

        # ── 1. Halo externe (soft radial glow) ──
        halo = QRadialGradient(center, r * 1.8)
        halo.setColorAt(0.0, QColor(Color.CYAN + "25"))   # ~15% opacity
        halo.setColorAt(0.5, QColor(Color.CYAN + "10"))
        halo.setColorAt(1.0, QColor(Color.CYAN + "00"))
        painter.setBrush(halo)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, r * 1.8, r * 1.8)

        # ── 2. GlowRing — anneau lumineux concentrique (Z.ai) ──
        ring_r = r * 1.15
        ring_pen = QPen(QColor(Color.CYAN + "30"), 2)
        ring_pen.setStyle(Qt.SolidLine)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center, ring_r, ring_r)

        # ── 3. Core — cercle central ──
        core_color = Color.ERROR if self._state == OrbState.ERROR else Color.CYAN
        core_gradient = QRadialGradient(center, r)
        core_gradient.setColorAt(0.0, QColor(Color.CYAN))
        core_gradient.setColorAt(0.6, QColor(core_color))
        core_gradient.setColorAt(1.0, QColor(core_color + "80"))
        painter.setBrush(core_gradient)
        painter.setPen(QPen(QColor(Color.TEXT_PRIMARY + "20"), 1))
        painter.drawEllipse(center, r, r)

        # ── 4. Halo rotatif (thinking / listening) ──
        if self._state in (OrbState.THINKING, OrbState.LISTENING):
            path = QPainterPath()
            arc_r = r * 1.3
            rect = QRectF(
                center.x() - arc_r, center.y() - arc_r,
                arc_r * 2, arc_r * 2,
            )
            path.arcMoveTo(rect, self._halo_angle)
            path.arcTo(rect, self._halo_angle, 270)

            pen = QPen(QColor(Color.CYAN + "50"), 2)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

        # ── 5. Anneau progression (acting) ──
        if self._state == OrbState.ACTING and self._progress > 0:
            prog_r = r * 0.85
            rect = QRectF(
                center.x() - prog_r, center.y() - prog_r,
                prog_r * 2, prog_r * 2,
            )
            angle = int(360 * self._progress * 16)
            pen = QPen(QColor(Color.CYAN), 3)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawArc(rect, 90 * 16, -angle)

        painter.end()
