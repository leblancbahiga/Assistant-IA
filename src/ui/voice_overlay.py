"""
NURU V12 — VoiceOverlay (Z.ai design exact).

Fenêtre frameless semi-transparente (60% × 40% écran) pour le mode vocal.

Composants Z.ai :
  - WaveformRings : 3 anneaux concentriques en sinusoïde
  - TranscriptText : transcription temps réel (Inter 300)
  - StatusPill : indicateur d'état (rgba(0,212,255,0.15))

Cycles EventBus :
  voice.wake_detected → voice.transcript_update → voice.thinking_start
  → voice.response_start → voice.session_end

Animations Z.ai :
  - Apparition: scale 0.8→1.0, opacity 0→1, 250ms OutCubic
  - Disparition: scale 1.0→0.8, opacity 1→0, 250ms InCubic
  - Timeout: 8s sans détection vocale
"""

import logging
import math
import random

from PySide6.QtCore import Qt, QTimer, QPointF, QPropertyAnimation, QEasingCurve, Property, Signal
from PySide6.QtGui import QPainter, QColor, QRadialGradient, QPen, QFont, QFontDatabase
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QApplication

from src.ui.tokens import Color, Typography, Radius, WindowSizes, AnimDuration, Spacing

logger = logging.getLogger(__name__)


class WaveformRings(QWidget):
    """
    3 anneaux waveform concentriques en sinusoïde (Z.ai).

    Chaque anneau pulse à un rythme différent pour créer
    une ambiance d'écoute organique.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(30)  # ~33 fps
        self._timer.timeout.connect(self._tick)
        # V16 AUDIT FIX QW2 : ne PAS démarrer le timer ici — VoiceOverlay le gère
        # self._timer.start()

    def start(self):
        """Démarre l'animation (appelé quand l'overlay est visible)."""
        self._timer.start()

    def stop(self):
        """Arrête l'animation (appelé quand l'overlay est caché)."""
        self._timer.stop()
        self._phase = 0.0
        self.update()

    def _tick(self):
        self._phase += 0.04
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        center = QPointF(self.width() / 2, self.height() / 2)
        max_r = min(self.width(), self.height()) * 0.4

        # 3 anneaux avec phases décalées
        for i in range(3):
            phase_offset = i * 2.094  # 120° décalage
            r = max_r * (0.5 + 0.3 * math.sin(self._phase + phase_offset) + 0.2)
            opacity = 0.25 + 0.2 * math.sin(self._phase * 0.7 + phase_offset)

            pen = QPen(QColor(f"rgba(0, 212, 255, {opacity})"))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, r, r)

        # Onde interne (4e anneau subtil)
        r4 = max_r * (0.3 + 0.15 * math.sin(self._phase * 0.5))
        pen4 = QPen(QColor(f"rgba(0, 212, 255, 0.15)"))
        pen4.setWidth(1)
        painter.setPen(pen4)
        painter.drawEllipse(center, r4, r4)

        painter.end()


class VoiceOverlay(QWidget):
    """
    VoiceOverlay — Fenêtre frameless pour le mode vocal.

    Z.ai design :
      - Taille : 60% × 40% écran
      - Frameless, semi-transparent
      - Animation scale/opacity 250ms

    Signaux :
      - closed() — quand l'overlay est fermé
    """

    closed = Signal()

    # Propriété animable pour opacity
    def _get_overlay_opacity(self) -> float:
        return self._overlay_opacity

    def _set_overlay_opacity(self, val: float):
        self._overlay_opacity = val
        self.setWindowOpacity(val)

    overlay_opacity = Property(float, _get_overlay_opacity, _set_overlay_opacity)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._overlay_opacity = 1.0
        self._visible = False
        self._timeout_seconds = 60  # temps max d'une session vocale
        self._silence_threshold = 4.0  # secondes de silence avant coupure

        # Fenêtre frameless
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Taille : 60% × 40% écran
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            w = int(geo.width() * WindowSizes.OVERLAY_WIDTH_PCT)
            h = int(geo.height() * WindowSizes.OVERLAY_HEIGHT_PCT)
            self.setFixedSize(w, h)
            # Centrer
            x = geo.x() + (geo.width() - w) // 2
            y = geo.y() + (geo.height() - h) // 2
            self.move(x, y)

        # Animations
        self._show_anim = QPropertyAnimation(self, b"overlay_opacity")
        self._show_anim.setDuration(AnimDuration.OVERLAY_SHOW)
        self._show_anim.setStartValue(0.0)
        self._show_anim.setEndValue(1.0)
        self._show_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._hide_anim = QPropertyAnimation(self, b"overlay_opacity")
        self._hide_anim.setDuration(AnimDuration.OVERLAY_HIDE)
        self._hide_anim.setStartValue(1.0)
        self._hide_anim.setEndValue(0.0)
        self._hide_anim.setEasingCurve(QEasingCurve.InCubic)
        self._hide_anim.finished.connect(self._on_hidden)

        # Timeout session max 60s
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.setInterval(self._timeout_seconds * 1000)
        self._timeout_timer.timeout.connect(self._on_timeout)

        # Timer silence 4s — se déclenche quand aucun audio utile n'est reçu
        self._silence_timer = QTimer(self)
        self._silence_timer.setSingleShot(True)
        self._silence_timer.setInterval(int(self._silence_threshold * 1000))
        self._silence_timer.timeout.connect(self._on_silence_timeout)

        # Layout
        self._build_ui()

    def _on_timeout(self):
        """Temps max de session atteint."""
        self.update_state("⏱ Temps écoulé")
        self.hide_overlay()

    def _on_silence_timeout(self):
        """Silence prolongé détecté — on coupe l'écoute."""
        self.update_state("🔇 Silence — fermeture")
        self.hide_overlay()

    def _build_ui(self):
        """Construit les composants overlay."""
        # Fond
        self.setStyleSheet(f"""
            VoiceOverlay {{
                background: {Color.BG_OVERLAY};
                border-radius: {Radius.LARGE}px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(24)

        # ── WaveformRings ──
        self._waveform = WaveformRings()
        self._waveform.setFixedHeight(120)
        layout.addWidget(self._waveform, alignment=Qt.AlignCenter)

        # ── Transcript ──
        self._transcript = QLabel("")
        self._transcript.setAlignment(Qt.AlignCenter)
        self._transcript.setWordWrap(True)
        self._transcript.setMaximumWidth(500)
        self._transcript.setStyleSheet(f"""
            QLabel {{
                color: {Color.TEXT_PRIMARY};
                font-size: {Typography.SIZE_OVERLAY}px;
                font-weight: {Typography.WEIGHT_LIGHT};
                font-family: {Typography.FAMILY_BODY};
                background: transparent;
                padding: 0;
            }}
        """)
        layout.addWidget(self._transcript, alignment=Qt.AlignCenter)

        # ── StatusPill ──
        self._status_pill = QLabel("En écoute…")
        self._status_pill.setAlignment(Qt.AlignCenter)
        self._status_pill.setStyleSheet(f"""
            QLabel {{
                color: {Color.CYAN};
                font-size: {Typography.SIZE_CAPTION}px;
                font-family: {Typography.FAMILY_CODE};
                background: {Color.CYAN_GLOW};
                border: 1px solid {Color.BORDER};
                border-radius: {Radius.SM}px;
                padding: 6px 16px;
            }}
        """)
        layout.addWidget(self._status_pill, alignment=Qt.AlignCenter)

    # ── API ──

    def show_overlay(self):
        """Apparition animée — scale + opacity 250ms."""
        self._timeout_timer.stop()
        self._silence_timer.stop()
        self.show()
        self.raise_()
        self._show_anim.start()
        self._visible = True
        self._timeout_timer.start()  # session max 60s
        # V16 AUDIT FIX QW2 : démarrer l'animation waveform
        self._waveform.start()

    def hide_overlay(self):
        """Disparition animée."""
        self._timeout_timer.stop()
        self._silence_timer.stop()
        if not self._visible:
            return
        self._hide_anim.start()

    def _on_hidden(self):
        self.hide()
        self._visible = False
        self._timeout_timer.stop()
        self._silence_timer.stop()
        self.closed.emit()
        # V16 AUDIT FIX QW2 : arrêter l'animation waveform
        self._waveform.stop()

    def update_transcript(self, text: str):
        """Met à jour la transcription temps réel.
        
        Si le texte est non-vide (parole détectée), on réarme
        le timer silence. Si vide, on le laisse courir.
        """
        self._transcript.setText(text)
        if text.strip():
            self._reset_silence_timer()

    def update_state(self, state_label: str):
        """Met à jour la StatusPill."""
        self._status_pill.setText(state_label)

    def _reset_silence_timer(self):
        """Réinitialise le timer silence 4s (parole détectée)."""
        self._silence_timer.stop()
        self._silence_timer.start()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide_overlay()
        super().keyPressEvent(event)
