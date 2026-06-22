"""
NURU V12 — Presence Orb Component
Design System DM-1 "Deep Cyan"
PySide6 / QPainter / QPropertyAnimation
Target: macOS M1 8GB

Specs extraites du mockup board V12:
  - Background: #0A0E17, dot grid at 4% opacity
  - Orb: Cyan sphere #00D4FF with radial gradient (white center → cyan edge)
  - GlowRing: 3 concentric rings, 30%/15%/5% opacity, QPainter radialGradient
  - Shadows: single-level only (M1 8GB constraint)
  - Animations: QPropertyAnimation, max 5% CPU
"""

from enum import Enum, auto

from PySide6.QtCore import (
    Qt, QRectF, QPointF, QTimer, QPropertyAnimation, Property, QEasingCurve, Signal
)
from PySide6.QtGui import (
    QPainter, QColor, QRadialGradient, QPen, QBrush, QFont, QPainterPath, QPolygonF
)
from PySide6.QtWidgets import QWidget


class OrbState(Enum):
    """États de l'orb — DM-1."""
    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()
    ACTING = auto()
    ERROR = auto()


# Couleurs DM-1 par état
STATE_COLORS = {
    OrbState.IDLE:     QColor(0, 212, 255),    # Cyan
    OrbState.LISTENING: QColor(0, 229, 153),   # Green
    OrbState.THINKING: QColor(255, 184, 0),    # Amber
    OrbState.SPEAKING: QColor(0, 212, 255),    # Cyan
    OrbState.ACTING:   QColor(0, 212, 255),    # Cyan
    OrbState.ERROR:    QColor(255, 77, 106),   # Rose
}

STATE_GLOW_ALPHA = {
    OrbState.IDLE:      40,
    OrbState.LISTENING: 80,
    OrbState.THINKING:  30,
    OrbState.SPEAKING:  60,
    OrbState.ACTING:    60,
    OrbState.ERROR:     90,
}

STATE_RING_COUNT = {
    OrbState.IDLE:      1,
    OrbState.LISTENING: 3,
    OrbState.THINKING:  2,
    OrbState.SPEAKING:  2,
    OrbState.ACTING:    2,
    OrbState.ERROR:     1,
}


class PresenceOrb(QWidget):
    """Sphère cyan translucide avec halo radial doux et pulsing."""

    state_changed = Signal(OrbState)  # émet OrbState au lieu de str

    def __init__(self, parent=None, orb_size: int = 120):
        super().__init__(parent)
        if orb_size:
            self.setFixedSize(orb_size, orb_size)
        self._orb_opacity = 1.0
        self._glow_opacity = 0.8
        self._pulse_phase = 0.0
        self._state = OrbState.IDLE

        # Design tokens DM-1
        self.COLOR_BG = QColor(10, 14, 23)        # #0A0E17
        self.COLOR_SURFACE1 = QColor(21, 27, 38)  # #151B26
        self.COLOR_CYAN = QColor(0, 212, 255)      # #00D4FF
        self.COLOR_CYAN_DIM = QColor(0, 212, 255, 100)  # 40% alpha
        self.COLOR_TEXT = QColor(232, 236, 241)    # #E8ECF1
        self.COLOR_TEXT_DIM = QColor(139, 149, 165)  # #8B95A5
        self.COLOR_GREEN = QColor(0, 229, 153)     # #00E599
        self.COLOR_AMBER = QColor(255, 184, 0)     # #FFB800
        self.COLOR_ROSE = QColor(255, 77, 106)     # #FF4D6A
        self.COLOR_DOT_GRID = QColor(26, 34, 52, 12)  # #1A2234 at ~5%

        # Pulsing animation timer (low CPU: single timer for all animations)
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._update_pulse)
        self._pulse_timer.start(50)  # 20 FPS — enough for smooth pulsing, low CPU

        # Smooth state transition
        self._target_orb_opacity = 1.0
        self._target_glow_opacity = 0.8
        self._target_rotation = 0.0
        self._current_rotation = 0.0

        self.setState(OrbState.IDLE)

    def set_state(self, state: OrbState):
        """Nouvelle API DM-1 : set_state avec OrbState enum."""
        self._state = state
        self._apply_state_config()
        self.state_changed.emit(state)
        self.update()

    def setState(self, state: OrbState):
        """Alias DM-1 (camelCase) — compatible."""
        self.set_state(state)

    def setWindowState(self, state):
        """API rétrocompatible : accepte str ou OrbState."""
        if isinstance(state, str):
            state_map = {
                "idle": OrbState.IDLE,
                "listening": OrbState.LISTENING,
                "thinking": OrbState.THINKING,
                "speaking": OrbState.SPEAKING,
                "acting": OrbState.ACTING,
                "error": OrbState.ERROR,
            }
            state = state_map.get(state, OrbState.IDLE)
        self.set_state(state)

    def _apply_state_config(self):
        """Applique la configuration visuelle pour l'état actuel."""
        state = self._state
        state_configs = {
            OrbState.IDLE:      {"orb": 1.0, "glow": 0.6, "rot_spd": 0.00},
            OrbState.LISTENING: {"orb": 1.0, "glow": 1.0, "rot_spd": 0.02},
            OrbState.THINKING:  {"orb": 0.9, "glow": 0.5, "rot_spd": 0.06},
            OrbState.SPEAKING:  {"orb": 1.0, "glow": 0.9, "rot_spd": 0.03},
            OrbState.ACTING:    {"orb": 1.0, "glow": 0.9, "rot_spd": 0.04},
            OrbState.ERROR:     {"orb": 0.8, "glow": 0.7, "rot_spd": 0.02},
        }
        config = state_configs.get(state, state_configs[OrbState.IDLE])
        self._target_orb_opacity = config["orb"]
        self._target_glow_opacity = config["glow"]
        self._target_rotation = config["rot_spd"]
        self._ring_count = STATE_RING_COUNT.get(state, 1)
        self._state_color = STATE_COLORS.get(state, QColor(0, 212, 255))

    def _update_pulse(self):
        """Animation frame update — called at 20 FPS."""
        self._pulse_phase += 0.03
        if self._pulse_phase > 6.2832:
            self._pulse_phase -= 6.2832

        # Smooth interpolation toward targets
        self._orb_opacity += (self._target_orb_opacity - self._orb_opacity) * 0.08
        self._glow_opacity += (self._target_glow_opacity - self._glow_opacity) * 0.08
        self._current_rotation += (self._target_rotation - self._current_rotation) * 0.08

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2

        # ── Layer 7: Background #0A0E17 ──
        painter.fillRect(self.rect(), self.COLOR_BG)

        # ── Layer 6: Dot Grid (4% opacity, spacing ~20px) ──
        self._draw_dot_grid(painter, w, h)

        # ── Layer 2: GlowRing — concentric rings ──
        self._draw_glow_rings(painter, cx, cy)

        # ── Layer 1: PresenceOrb — main sphere ──
        self._draw_orb(painter, cx, cy, min(w, h) * 0.28)

        # ── Layer 0: NURU wordmark (via QLabel dans NuruWindow) ──
        # Le texte QPainter est désactivé — le logo brand V3
        # est affiché via QLabel dans NuruWindow._build_ui()

        painter.end()

    def _draw_dot_grid(self, painter: QPainter, w: int, h: int):
        """Grille de points subtile à ~4-5% opacité, espacement ~20px."""
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.COLOR_DOT_GRID)
        spacing = 20
        dot_r = 1
        for x in range(spacing, w, spacing):
            for y in range(spacing, h, spacing):
                painter.drawEllipse(QPointF(x, y), dot_r, dot_r)

    def _draw_glow_rings(self, painter: QPainter, cx: float, cy: float):
        """Anneaux concentriques avec la couleur de l'état actuel."""
        base_radius = min(self.width(), self.height()) * 0.32
        c = self._state_color if hasattr(self, '_state_color') else self.COLOR_CYAN

        ring_configs = [
            {"radius_mult": 1.0,  "opacity": 0.30, "width": 2.0},
            {"radius_mult": 1.15, "opacity": 0.15, "width": 1.5},
            {"radius_mult": 1.30, "opacity": 0.05, "width": 1.0},
        ]

        for i, cfg in enumerate(ring_configs):
            if i >= self._ring_count:
                break

            pulse = 0.02 * (1 + self._pulse_phase) * self._glow_opacity
            radius = base_radius * cfg["radius_mult"] + pulse * base_radius
            opacity = cfg["opacity"] * self._glow_opacity
            rotation = self._current_rotation * (i + 1) * 30  # degrés

            color = QColor(c.red(), c.green(), c.blue(), int(255 * opacity))
            pen = QPen(color, cfg["width"])
            pen.setStyle(Qt.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(rotation)
            painter.drawEllipse(QPointF(0, radius * 0.1), radius, radius * 0.85)
            painter.restore()

        # Soft radial glow behind orb (single-level shadow, M1 friendly)
        glow_radius = base_radius * 1.5
        gradient = QRadialGradient(cx, cy, glow_radius)
        glow_alpha = int(STATE_GLOW_ALPHA.get(self._state, 40) * self._glow_opacity)
        gcolor = self._state_color if hasattr(self, '_state_color') else self.COLOR_CYAN
        gradient.setColorAt(0.0, QColor(gcolor.red(), gcolor.green(), gcolor.blue(), glow_alpha))
        gradient.setColorAt(0.5, QColor(gcolor.red(), gcolor.green(), gcolor.blue(), glow_alpha // 3))
        gradient.setColorAt(1.0, QColor(gcolor.red(), gcolor.green(), gcolor.blue(), 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(cx, cy), glow_radius, glow_radius)

    def _draw_orb(self, painter: QPainter, cx: float, cy: float, radius: float):
        """Sphère avec gradient radial — couleur de l'état actuel."""
        pulse = 1.0 + 0.03 * (1 + self._pulse_phase)
        r = radius * pulse
        c = self._state_color if hasattr(self, '_state_color') else self.COLOR_CYAN

        # Main orb gradient
        gradient = QRadialGradient(cx - r * 0.2, cy - r * 0.2, r * 1.2)
        alpha = int(255 * self._orb_opacity)

        # Couleurs dérivées de l'état
        bright = QColor(min(255, c.red() + 80), min(255, c.green() + 80),
                        min(255, c.blue() + 100), alpha)
        mid = QColor(c.red(), c.green(), c.blue(), alpha)
        dark = QColor(max(0, c.red() - 80), max(0, c.green() - 80),
                      max(0, c.blue() - 60), int(alpha * 0.8))
        edge = QColor(max(0, c.red() - 140), max(0, c.green() - 140),
                      max(0, c.blue() - 120), int(alpha * 0.3))

        gradient.setColorAt(0.0, bright)
        gradient.setColorAt(0.3, mid)
        gradient.setColorAt(0.7, dark)
        gradient.setColorAt(1.0, edge)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(cx, cy), r, r)

        # Specular highlight (top-left refraction)
        highlight_r = r * 0.35
        hx = cx - r * 0.25
        hy = cy - r * 0.25
        highlight = QRadialGradient(hx, hy, highlight_r)
        highlight.setColorAt(0.0, QColor(255, 255, 255, int(120 * self._orb_opacity)))
        highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(highlight))
        painter.drawEllipse(QPointF(hx, hy), highlight_r, highlight_r)

    def _draw_logo(self, painter: QPainter, cx: float, y: float):
        """Texte 'NURU' centré sous l'orb en cyan."""
        font = QFont("Inter", 14, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4)
        painter.setFont(font)
        painter.setPen(QColor(0, 212, 255, int(200 * self._orb_opacity)))
        painter.drawText(QRectF(cx - 60, y, 120, 30), Qt.AlignCenter, "NURU")


# ── Alias DM-1 : NuruPresenceOrb = PresenceOrb ──
# Les imports du projet utilisent NuruPresenceOrb, mais le code V12
# utilise PresenceOrb. Cet alias assure la compatibilité.
NuruPresenceOrb = PresenceOrb
