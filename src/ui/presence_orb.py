"""
NURU V15 — Presence Orb "NEON COGNITIVE"
——————————————————————————————
Orb cybernétique multicouche avec particules orbitales.

Architecture visuelle (du fond au premier plan) :
  Layer 7 : Fond espace profond #05080F
  Layer 6 : Grille de points dynamique (pulsing)
  Layer 5 : Champ de particules orbitales (cercles lumineux)
  Layer 4 : Aura — gradient radial doux
  Layer 3 : Anneaux rotatifs (halo rings) — 1 à 3 selon état
  Layer 2 : Orb principale — gradient radial 4 stops
  Layer 1 : Specular highlight (réflexion source lumineuse)
  Layer 0 : Core flash — point lumineux central

Contraintes M1 8 Go :
  - Single QTimer 50ms (20 FPS)
  - Particules limitées (~30)
  - QPainter uniquement (pas de QGraphicsBlurEffect)
  - Cache QPixmap pour fond statique
"""

import math
import random
from enum import Enum, auto

from PySide6.QtCore import (
    Qt, QRectF, QPointF, QTimer, QPropertyAnimation, Property,
    QEasingCurve, Signal, QSize
)
from PySide6.QtGui import (
    QPainter, QColor, QRadialGradient, QConicalGradient, QLinearGradient,
    QPen, QBrush, QFont, QPainterPath, QPolygonF, QPixmap, QTransform
)
from PySide6.QtWidgets import QWidget


class OrbState(Enum):
    """États de l'orb — NEON COGNITIVE."""
    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()
    ACTING = auto()
    ERROR = auto()
    SLEEP = auto()


# ── Palette NEON COGNITIVE par état ────────────────────────────────

STATE_COLORS = {
    OrbState.IDLE:      QColor(0, 240, 255),    # Cyan néon
    OrbState.LISTENING: QColor(0, 255, 170),    # Vert cyber
    OrbState.THINKING:  QColor(255, 184, 0),    # Ambre
    OrbState.SPEAKING:  QColor(0, 240, 255),    # Cyan néon
    OrbState.ACTING:    QColor(124, 58, 237),   # Violet néon
    OrbState.ERROR:     QColor(255, 51, 102),   # Rose néon
    OrbState.SLEEP:     QColor(60, 70, 100),    # Bleu-gris dim
}

STATE_SECONDARY = {
    OrbState.IDLE:      QColor(124, 58, 237),   # Violet
    OrbState.LISTENING: QColor(0, 240, 255),    # Cyan
    OrbState.THINKING:  QColor(255, 120, 0),    # Orange
    OrbState.SPEAKING:  QColor(124, 58, 237),   # Violet
    OrbState.ACTING:    QColor(0, 240, 255),    # Cyan
    OrbState.ERROR:     QColor(255, 180, 0),    # Ambre
    OrbState.SLEEP:     QColor(40, 50, 80),     # Gris bleu
}

STATE_GLOW_ALPHA = {
    OrbState.IDLE:      60,
    OrbState.LISTENING: 100,
    OrbState.THINKING:  45,
    OrbState.SPEAKING:  85,
    OrbState.ACTING:    75,
    OrbState.ERROR:     110,
    OrbState.SLEEP:     20,
}

STATE_RING_COUNT = {
    OrbState.IDLE:      2,
    OrbState.LISTENING: 3,
    OrbState.THINKING:  2,
    OrbState.SPEAKING:  3,
    OrbState.ACTING:    3,
    OrbState.ERROR:     1,
    OrbState.SLEEP:     1,
}

STATE_PARTICLE_COUNT = {
    OrbState.IDLE:      20,
    OrbState.LISTENING: 30,
    OrbState.THINKING:  25,
    OrbState.SPEAKING:  25,
    OrbState.ACTING:    20,
    OrbState.ERROR:     15,
    OrbState.SLEEP:     8,
}

STATE_ROTATION_SPEED = {
    OrbState.IDLE:      0.15,
    OrbState.LISTENING: 0.30,
    OrbState.THINKING:  0.60,
    OrbState.SPEAKING:  0.40,
    OrbState.ACTING:    0.50,
    OrbState.ERROR:     0.20,
    OrbState.SLEEP:     0.05,
}

STATE_PULSE_AMPLITUDE = {
    OrbState.IDLE:      0.025,
    OrbState.LISTENING: 0.050,
    OrbState.THINKING:  0.080,
    OrbState.SPEAKING:  0.040,
    OrbState.ACTING:    0.035,
    OrbState.ERROR:     0.060,
    OrbState.SLEEP:     0.010,
}


class OrbParticle:
    """Particule orbitale autour de l'orb."""

    def __init__(self, index: int, total: int):
        angle = (index / total) * 6.2832 + random.uniform(0, 1.0)
        radius = random.uniform(0.85, 1.40)
        orbit_speed = random.uniform(0.3, 0.8)
        phase_offset = random.uniform(0, 6.2832)

        self.angle = angle
        self.orbit_radius = radius
        self.orbit_speed = orbit_speed
        self.phase_offset = phase_offset
        self.size = random.uniform(1.5, 3.5)
        self.opacity = random.uniform(0.3, 0.8)
        self.z_offset = random.uniform(-0.3, 0.3)  # profondeur 3D simulée


class PresenceOrb(QWidget):
    """Orb cybernétique multicouche avec particules orbitales animées."""

    state_changed = Signal(OrbState)

    def __init__(self, parent=None, orb_size: int = 130):
        super().__init__(parent)
        if orb_size:
            self.setFixedSize(orb_size, orb_size)

        # État
        self._orb_opacity = 1.0
        self._glow_opacity = 0.8
        self._pulse_phase = 0.0
        self._ring_rotation = 0.0
        self._state = OrbState.IDLE
        self._target_orb_opacity = 1.0
        self._target_glow_opacity = 0.6
        self._ring_count = 2
        self._state_color = STATE_COLORS[OrbState.IDLE]
        self._state_secondary = STATE_SECONDARY[OrbState.IDLE]
        self._rotation_speed = 0.15
        self._pulse_amplitude = 0.025

        # Cache pour fond statique
        self._bg_pixmap = None
        self._bg_dirty = True

        # Particules orbitales
        self._particles = self._create_particles(OrbState.IDLE)

        # Timer principal (20 FPS — single timer pour tout)
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._update_pulse)
        self._pulse_timer.start(50)

        self.setState(OrbState.IDLE)

    # ── API publique ──────────────────────────────────────────────

    def set_state(self, state: OrbState):
        self._state = state
        self._apply_state_config()
        self.state_changed.emit(state)
        self.update()

    def setState(self, state: OrbState):
        self.set_state(state)

    def setWindowState(self, state):
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

    def get_state(self) -> OrbState:
        return self._state

    # ── Configuration ─────────────────────────────────────────────

    def _apply_state_config(self):
        state = self._state
        self._target_orb_opacity = 1.0
        self._target_glow_opacity = 1.0  # sera interpolé
        self._state_color = STATE_COLORS.get(state, STATE_COLORS[OrbState.IDLE])
        self._state_secondary = STATE_SECONDARY.get(state, STATE_SECONDARY[OrbState.IDLE])
        self._ring_count = STATE_RING_COUNT.get(state, 2)
        self._rotation_speed = STATE_ROTATION_SPEED.get(state, 0.15)
        self._pulse_amplitude = STATE_PULSE_AMPLITUDE.get(state, 0.025)

        # Limiter glow selon état
        glow = STATE_GLOW_ALPHA.get(state, 60) / 100.0
        self._target_glow_opacity = glow

        # Re-créer les particules si le compte a changé
        target_count = STATE_PARTICLE_COUNT.get(state, 20)
        if len(self._particles) != target_count:
            self._particles = self._create_particles(state)

        # V16 AUDIT FIX QW8 : réduire FPS en IDLE/SLEEP (10 FPS vs 20 FPS)
        # Économise 1-2% GPU sur M1 en continu
        if state in (OrbState.IDLE, OrbState.SLEEP):
            self._pulse_timer.setInterval(100)  # 10 FPS
        else:
            self._pulse_timer.setInterval(50)   # 20 FPS

    def _create_particles(self, state: OrbState) -> list:
        count = STATE_PARTICLE_COUNT.get(state, 20)
        return [OrbParticle(i, count) for i in range(count)]

    # ── Animation ─────────────────────────────────────────────────

    def _update_pulse(self):
        self._pulse_phase += 0.04
        if self._pulse_phase > 6.2832:
            self._pulse_phase -= 6.2832

        # Interpolation douce vers cibles
        self._orb_opacity += (self._target_orb_opacity - self._orb_opacity) * 0.06
        self._glow_opacity += (self._target_glow_opacity - self._glow_opacity) * 0.06

        # Rotation continue des anneaux
        self._ring_rotation += self._rotation_speed
        if self._ring_rotation > 360:
            self._ring_rotation -= 360

        # Mise à jour des particules
        for p in self._particles:
            p.angle += 0.02 * p.orbit_speed
            if p.angle > 6.2832:
                p.angle -= 6.2832

        self.update()

    # ── Dessin ─────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        base_r = min(w, h) * 0.28
        pulse = 1.0 + self._pulse_amplitude * math.sin(self._pulse_phase)
        orb_r = base_r * pulse
        c = self._state_color
        s = self._state_secondary
        alpha_mult = self._orb_opacity
        glow_mult = self._glow_opacity

        # ── Layer 7: Background ──
        painter.fillRect(self.rect(), QColor(5, 8, 15))

        # ── Layer 6: Dot Grid (pulsing) ──
        self._draw_dot_grid(painter, w, h)

        # ── Layer 5: Particules orbitales ──
        self._draw_particles(painter, cx, cy, orb_r, c, s, alpha_mult, glow_mult)

        # ── Layer 4: Aura (glow radial) ──
        self._draw_aura(painter, cx, cy, orb_r, c, glow_mult)

        # ── Layer 3: Anneaux rotatifs ──
        self._draw_rings(painter, cx, cy, orb_r, c, s, alpha_mult, glow_mult)

        # ── Layer 2: Orb principale ──
        self._draw_orb(painter, cx, cy, orb_r, c, alpha_mult)

        # ── Layer 1: Specular ──
        self._draw_specular(painter, cx, cy, orb_r, alpha_mult)

        # ── Layer 0: Core flash ──
        self._draw_core(painter, cx, cy, orb_r, c, alpha_mult, glow_mult)

        painter.end()

    # ── Couches de dessin individuelles ────────────────────────────

    def _draw_dot_grid(self, painter: QPainter, w: int, h: int):
        """Grille de points avec pulsing d'opacité."""
        dot_alpha = int(8 + 4 * math.sin(self._pulse_phase * 0.5))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(30, 40, 80, dot_alpha))

        spacing = 18
        dot_r = 1
        offset = int(self._ring_rotation * 0.1) % spacing
        for x in range(offset, w + spacing, spacing):
            for y in range(offset, h + spacing, spacing):
                painter.drawEllipse(QPointF(x, y), dot_r, dot_r)

    def _draw_particles(self, painter: QPainter, cx: float, cy: float,
                         orb_r: float, c: QColor, s: QColor,
                         alpha: float, glow: float):
        """Particules orbitant autour de l'orb."""
        painter.setPen(Qt.NoPen)

        for p in self._particles:
            # Position 3D simulée avec ellipse (z_offset → excentricité verticale)
            r = orb_r * p.orbit_radius
            x = cx + r * math.cos(p.angle)
            y = cy + r * math.sin(p.angle * 0.7 + p.z_offset) * 0.6

            # Opacité pulsée
            pulse_opacity = 0.3 + 0.5 * (0.5 + 0.5 * math.sin(self._pulse_phase + p.phase_offset))
            particle_alpha = int(p.opacity * pulse_opacity * glow * alpha * 255)

            if particle_alpha < 5:
                continue

            # Couleur: alterner primaire/secondaire
            is_primary = (int(p.angle * 10) % 3) != 0
            col = c if is_primary else s
            color = QColor(col.red(), col.green(), col.blue(), particle_alpha)
            painter.setBrush(color)

            # Taille pulsée
            size_pulse = p.size * (0.8 + 0.4 * (0.5 + 0.5 * math.sin(self._pulse_phase * 0.7 + p.phase_offset)))
            painter.drawEllipse(QPointF(x, y), size_pulse, size_pulse)

    def _draw_aura(self, painter: QPainter, cx: float, cy: float,
                   orb_r: float, c: QColor, glow: float):
        """Aura lumineuse autour de l'orb."""
        glow_radius = orb_r * 2.0
        gradient = QRadialGradient(cx, cy, glow_radius)

        glow_alpha = int(60 * glow)
        gradient.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), glow_alpha))
        gradient.setColorAt(0.3, QColor(c.red(), c.green(), c.blue(), glow_alpha // 2))
        gradient.setColorAt(0.6, QColor(c.red(), c.green(), c.blue(), glow_alpha // 5))
        gradient.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(cx, cy), glow_radius, glow_radius)

    def _draw_rings(self, painter: QPainter, cx: float, cy: float,
                    orb_r: float, c: QColor, s: QColor,
                    alpha: float, glow: float):
        """Anneaux concentriques rotatifs."""
        for i in range(self._ring_count):
            ring_r = orb_r * (1.25 + i * 0.20)
            ring_opacity = int(glow * alpha * (0.20 - i * 0.05))

            if ring_opacity < 3:
                continue

            color = QColor(c.red(), c.green(), c.blue(), ring_opacity)
            pen = QPen(color, max(1.0, 2.0 - i * 0.5))
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)

            # Rotation individuelle par anneau
            rotation = self._ring_rotation * (1.0 + i * 0.5)
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(rotation)

            # Légère excentricité pour effet 3D
            y_offset = ring_r * 0.05 * (i + 1)
            painter.drawEllipse(QPointF(0, y_offset), ring_r, ring_r * 0.80)

            painter.restore()

            # Second anneau (contra-rotatif, couleur secondaire, plus fin)
            if i < 2:
                pen2 = QPen(QColor(s.red(), s.green(), s.blue(), ring_opacity // 2), max(0.5, 1.5 - i * 0.4))
                painter.setPen(pen2)
                rotation2 = -self._ring_rotation * (0.7 + i * 0.3)
                painter.save()
                painter.translate(cx, cy)
                painter.rotate(rotation2)
                painter.drawEllipse(QPointF(0, -y_offset * 0.5), ring_r * 0.95, ring_r * 0.75)
                painter.restore()

        # Fine ligne lumineuse externe (glow)
        glow_pen = QPen(QColor(c.red(), c.green(), c.blue(), int(glow * alpha * 40)), 0.5)
        painter.setPen(glow_pen)
        painter.setBrush(Qt.NoBrush)
        glow_r = orb_r * 1.8
        painter.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

    def _draw_orb(self, painter: QPainter, cx: float, cy: float,
                  orb_r: float, c: QColor, alpha: float):
        """Sphère principale avec gradient radial 4 stops."""
        if alpha < 0.01:
            return

        gradient = QRadialGradient(cx - orb_r * 0.25, cy - orb_r * 0.25, orb_r * 1.3)
        a = int(255 * alpha)

        # Cœur blanc → cyan → violet → foncé (dégradé 4 stops)
        bright = QColor(
            min(255, c.red() + 100),
            min(255, c.green() + 100),
            min(255, c.blue() + 120), a
        )
        mid = QColor(c.red(), c.green(), c.blue(), a)
        dark = QColor(
            max(0, c.red() - 60),
            max(0, c.green() - 60),
            max(0, c.blue() - 40), int(a * 0.85)
        )
        edge = QColor(
            max(0, c.red() - 100),
            max(0, c.green() - 100),
            max(0, c.blue() - 80), int(a * 0.35)
        )

        gradient.setColorAt(0.0, bright)
        gradient.setColorAt(0.25, mid)
        gradient.setColorAt(0.65, dark)
        gradient.setColorAt(1.0, edge)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(cx, cy), orb_r, orb_r)

    def _draw_specular(self, painter: QPainter, cx: float, cy: float,
                       orb_r: float, alpha: float):
        """Réflexion lumineuse haute-gauche (effet verre/globe 3D)."""
        if alpha < 0.01:
            return

        highlight_r = orb_r * 0.40
        hx = cx - orb_r * 0.28
        hy = cy - orb_r * 0.28

        gradient = QRadialGradient(hx, hy, highlight_r)
        gradient.setColorAt(0.0, QColor(255, 255, 255, int(140 * alpha)))
        gradient.setColorAt(0.5, QColor(255, 255, 255, int(40 * alpha)))
        gradient.setColorAt(1.0, QColor(255, 255, 255, 0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(hx, hy), highlight_r, highlight_r)

        # Petit reflet secondaire (bas-droite, très subtil)
        h2_r = orb_r * 0.15
        gradient2 = QRadialGradient(cx + orb_r * 0.35, cy + orb_r * 0.35, h2_r)
        gradient2.setColorAt(0.0, QColor(255, 255, 255, int(30 * alpha)))
        gradient2.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(gradient2))
        painter.drawEllipse(QPointF(cx + orb_r * 0.35, cy + orb_r * 0.35), h2_r, h2_r)

    def _draw_core(self, painter: QPainter, cx: float, cy: float,
                   orb_r: float, c: QColor, alpha: float, glow: float):
        """Point lumineux central (flash core)."""
        if alpha < 0.01:
            return

        core_r = orb_r * 0.12
        core_alpha = int(glow * alpha * 200 * (0.7 + 0.3 * math.sin(self._pulse_phase * 2.0)))

        gradient = QRadialGradient(cx, cy, core_r)
        gradient.setColorAt(0.0, QColor(255, 255, 255, core_alpha))
        gradient.setColorAt(0.5, QColor(
            min(255, c.red() + 150),
            min(255, c.green() + 150),
            min(255, c.blue() + 150), core_alpha // 2
        ))
        gradient.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)


# ── Alias compatibilité ────────────────────────────────────────────
NuruPresenceOrb = PresenceOrb
