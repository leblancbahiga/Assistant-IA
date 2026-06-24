"""
NURU V12 — Application Principale
Design System DM-1 "Deep Cyan"
Architecture: Ambient Assistant (pas de fenêtre principale)

Specs (extraites mockup board V12):
  - AMBIENT MODE: l'assistant vit en présence ambiante
  - PAS de fenêtre principale, PAS de cockpit 3 colonnes
  - PresenceOrb plein écran (frameless) pour l'état idle
  - FloatingWidget 220x160px qui apparaît au besoin
  - QSystemTrayIcon diamant cyan dans la barre macOS
  - EventBus Flow: wake_detected → transcript_update → thinking_start → response_start → session_end

Utilisation:
  python nuru_v12_app.py
"""

import sys
from PySide6.QtCore import Qt, QTimer, QPoint, Signal
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from nuru_v12_presence_orb import PresenceOrb
from nuru_v12_floating_widget import FloatingWidget
from nuru_v12_tray_icon import NURUTrayIcon


class NURUEventBus:
    """EventBus central — flow: wake → transcript → thinking → response → end."""

    wake_detected = Signal()
    transcript_update = Signal(str)
    thinking_start = Signal()
    response_start = Signal(str)
    session_end = Signal()


class NURUApp:
    """Orchestrateur principal NURU V12."""

    def __init__(self):
        self.app = QApplication(sys.argv)

        # ── Font Setup ──
        QFont.insertSubstitution("Inter", "SF Pro Display")
        self.app.setFont(QFont("Inter", 12))

        # ── Event Bus ──
        self.bus = NURUEventBus()
        self._connect_bus()

        # ── Composants V12 ──

        # 1. Presence Orb (fullscreen frameless, idle state)
        self.orb_window = PresenceOrb()
        self.orb_window.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
        )
        self.orb_window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.orb_window.showFullScreen()
        self.orb_window.setWindowState("idle")

        # 2. Floating Widget (220x160px, top-right)
        self.widget = FloatingWidget()
        self.widget.message_requested.connect(self._on_widget_click)

        # 3. Tray Icon (diamant cyan menu bar)
        self.tray = NURUTrayIcon(self.app)
        self.tray.tray.activated.connect(self._on_tray_activated)
        quit_action = self.tray.get_quit_action()
        if quit_action:
            quit_action.triggered.connect(self._quit)
        self.tray.show()

        # ── Position widget en bas à droite ──
        QTimer.singleShot(100, self._position_widget)

    def _connect_bus(self):
        """Connecte le flow EventBus: wake → transcript → thinking → response → end."""
        self.bus.wake_detected.connect(self._on_wake)
        self.bus.transcript_update.connect(self._on_transcript)
        self.bus.thinking_start.connect(self._on_thinking)
        self.bus.response_start.connect(self._on_response)
        self.bus.session_end.connect(self._on_session_end)

    # ── EventBus Flow Handlers ──

    def _on_wake(self):
        """Step 1: voice.wake_detected → listening state."""
        self.orb_window.setWindowState("listening")
        self.tray.setState("listening")
        self.widget.setStatus("En écoute...", "#00E599")

    def _on_transcript(self, text: str):
        """Step 2: voice.transcript_update → affiche transcription."""
        self.widget.setPreview(text)

    def _on_thinking(self):
        """Step 3: voice.thinking_start → thinking state."""
        self.orb_window.setWindowState("thinking")
        self.tray.setState("thinking")
        self.widget.setStatus("Réflexion...", "#FFB800")
        self.widget.setPreview("NURU réfléchit...")

    def _on_response(self, text: str):
        """Step 4: voice.response_start → speaking state."""
        self.orb_window.setWindowState("speaking")
        self.tray.setState("speaking")
        self.widget.setPreview(text)
        self.widget.setStatus("Parle...", "#00D4FF")

    def _on_session_end(self):
        """Step 5: voice.session_end → back to idle."""
        self.orb_window.setWindowState("idle")
        self.tray.setState("idle")
        self.widget.setStatus("Assistant prêt", "#8B95A5")

    # ── UI Event Handlers ──

    def _on_widget_click(self, event: str):
        """Clic sur le floating widget → toggle orb fullscreen."""
        if self.orb_window.isVisible():
            self.orb_window.hide()
            self.widget.setStatus("Cliquez pour réactiver", "#8B95A5")
        else:
            self.orb_window.showFullScreen()
            self.widget.setStatus("Assistant prêt", "#8B95A5")

    def _on_tray_activated(self, reason):
        """Clic sur l'icône tray → toggle widget visibility."""
        if self.widget.isVisible():
            self.widget.hide()
        else:
            self._position_widget()
            self.widget.show()

    def _position_widget(self):
        """Positionne le widget en bas à droite de l'écran."""
        screen = self.app.primaryScreen().geometry()
        margin = 20
        x = screen.right() - self.widget.width() - margin
        y = screen.bottom() - self.widget.height() - margin - 60  # au-dessus du dock
        self.widget.move(x, y)

    def _quit(self):
        self.tray.tray.hide()
        self.app.quit()

    def run(self):
        sys.exit(self.app.exec())


if __name__ == "__main__":
    nuru = NURUApp()
    nuru.run()