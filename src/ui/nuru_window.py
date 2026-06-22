"""
NURU V12 — NuruWindow (Z.ai design exact — document concept).

QMainWindow minimal — pas de cockpit.

Z.ai doc :
  - resize(720, 860), minimumSize(480, 600)
  - Frameless (WA_TranslucentBackground)
  - PresenceOrb (120px) en haut
  - ConversationSurface (bulles chat) au centre
  - Input bar + micro en bas
  - ContextStrip optionnel

Trois modes : chat (défaut) | voice | action
"""

import logging
import os

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation
from PySide6.QtGui import QAction, QKeySequence, QShortcut, QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QSizePolicy, QApplication,
)

from src.ui.tokens import Color, Typography, Radius, Spacing, OrbSizes, AnimDuration, WindowSizes
from src.ui.presence_orb import NuruPresenceOrb, OrbState
from src.ui.conversation_surface import ConversationSurface

logger = logging.getLogger(__name__)


class NuruInputBar(QWidget):
    """Barre de saisie Z.ai : input + micro secondaire."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setStyleSheet(f"""
            background: transparent;
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, 0, Spacing.MD, 0)
        layout.setSpacing(Spacing.SM)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Message NURU…")
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {Color.BG_ELEVATED};
                color: {Color.TEXT_PRIMARY};
                border: 1px solid {Color.BORDER};
                border-radius: {Radius.MEDIUM}px;
                padding: 10px 14px;
                font-size: {Typography.SIZE_BODY}pt;
                font-family: {Typography.FAMILY_BODY};
                selection-background-color: {Color.CYAN}40;
            }}
            QLineEdit:focus {{
                border-color: {Color.CYAN};
            }}
        """)
        layout.addWidget(self._input, stretch=1)

        self._mic = QPushButton("🎤")
        self._mic.setFixedSize(38, 38)
        self._mic.setToolTip("Hey NURU — mode vocal")
        self._mic.setStyleSheet(f"""
            QPushButton {{
                background: {Color.BG_ELEVATED};
                color: {Color.TEXT_SECONDARY};
                border: 1px solid {Color.BORDER};
                border-radius: 19px;
                font-size: 16px;
            }}
            QPushButton:hover {{
                background: {Color.CYAN_GLOW};
                border-color: {Color.CYAN};
                color: {Color.CYAN};
            }}
        """)
        layout.addWidget(self._mic)

    @property
    def input(self) -> QLineEdit:
        return self._input

    @property
    def mic_button(self) -> QPushButton:
        return self._mic


class NuruWindow(QMainWindow):
    """
    Fenêtre principale NURU V12 (Z.ai).

    Architecture :
      - QMainWindow 720×860, frameless (WA_TranslucentBackground)
      - PresenceOrb (120px) en haut — point focal visuel
      - ConversationSurface (bulles) — zone centrale
      - NuruInputBar (saisie + micro) — bas
      - TrayIcon intégré
      - Communication via EventBus (signaux/slots)
    """

    def __init__(self):
        super().__init__()
        self._current_mode = "chat"  # chat | voice | action

        self._setup_window()
        self._build_ui()

    # ── Fenêtre ──

    def _setup_window(self):
        """Z.ai : resize(720, 860), WA_TranslucentBackground."""
        self.setWindowTitle("NURU")
        self.resize(WindowSizes.WINDOW_WIDTH, WindowSizes.WINDOW_HEIGHT)
        self.setMinimumSize(WindowSizes.WINDOW_MIN_WIDTH, WindowSizes.WINDOW_MIN_HEIGHT)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Coins arrondis via mask (Z.ai: coins arrondis via QPainter)
        # Utilisation de stylesheet pour le fond
        self.setStyleSheet(f"""
            NuruWindow {{
                background: {Color.BG_DEEP};
                border-radius: {Radius.LARGE}px;
            }}
        """)

    # ── UI ──

    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet(f"""
            background: {Color.BG_DEEP};
            border-radius: {Radius.LARGE}px;
        """)
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.SM)

        # ── PresenceOrb ──
        self._orb = NuruPresenceOrb(orb_size=OrbSizes.WINDOW)
        orb_container = QWidget()
        orb_container.setStyleSheet("background: transparent;")
        orb_layout = QHBoxLayout(orb_container)
        orb_layout.setContentsMargins(0, 0, 0, 0)
        orb_layout.addStretch()
        orb_layout.addWidget(self._orb)
        orb_layout.addStretch()
        layout.addWidget(orb_container)

        # ── ConversationSurface ──
        self._conversation = ConversationSurface()
        self._conversation.setStyleSheet(f"""
            background: transparent;
        """)
        layout.addWidget(self._conversation, stretch=1)

        # Separator discret
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {Color.BORDER};")
        layout.addWidget(sep)

        # ── Input Bar ──
        self._input_bar = NuruInputBar()
        self._input_bar.input.returnPressed.connect(self._on_send)
        self._input_bar.mic_button.clicked.connect(self._on_mic_click)
        layout.addWidget(self._input_bar)

    # ── Actions ──

    def _on_send(self):
        text = self._input_bar.input.text().strip()
        if not text:
            return
        self._input_bar.input.clear()
        # Ajouter bulle utilisateur
        self._conversation.add_message(f"**Vous** : {text}", is_user=True)
        # Simuler réponse
        QTimer.singleShot(500, lambda: self._add_response(f"Reçu : {text}"))

    def _add_response(self, text: str):
        self._conversation.add_message(f"NURU : {text}", is_user=False)
        self._orb.set_state(OrbState.IDLE)

    def _on_mic_click(self):
        """Déclenche le mode vocal."""
        self._orb.set_state(OrbState.LISTENING)
        # Le VoiceOverlay est géré par AmbientApp
        logger.info("Micro cliqué — mode vocal")

    # ── Orb API ──

    @property
    def orb(self) -> NuruPresenceOrb:
        return self._orb

    @property
    def conversation(self) -> ConversationSurface:
        return self._conversation

    @property
    def input_bar(self) -> NuruInputBar:
        return self._input_bar

    # ── Modes ──

    def set_mode(self, mode: str):
        """chat | voice | action"""
        self._current_mode = mode
        if mode == "voice":
            self.setWindowOpacity(0.3)  # Z.ai: fenêtre réduit son opacité à 0.3 en mode vocal
        else:
            self.setWindowOpacity(1.0)

    # ── Render ──

    def paintEvent(self, event):
        """Coins arrondis via QPainter — Z.ai spec."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(Color.BG_DEEP))
        painter.setPen(Qt.NoPen)
        r = Radius.LARGE
        painter.drawRoundedRect(self.rect(), r, r)
        painter.end()
