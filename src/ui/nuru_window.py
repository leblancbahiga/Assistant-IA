"""
NURU V12 — NuruWindow (Z.ai design).

Conteneur principal sombre, coins arrondis, routeur d'événements.
Remplace l'ancien CyberDashboard 3 colonnes.

Composants :
  - NuruPresenceOrb (120px) — cœur visuel en haut à droite
  - ConversationSurface — zone de chat centrale
  - NuruInputBar — barre de saisie en bas
  - Raccourcis clavier V12
"""

import logging
import os
import sys

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QShortcut, QKeySequence, QIcon, QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QLineEdit, QPushButton, QApplication, QMenu, QSystemTrayIcon,
    QSizePolicy, QSpacerItem,
)

from src.ui.tokens import Color, Typography, Radius, Spacing, OrbSizes
from src.ui.presence_orb import NuruPresenceOrb, OrbState
from src.ui.conversation_surface import ConversationSurface
from src.ui.floating_widget import NuruFloatingWidget

logger = logging.getLogger(__name__)

# ── Chemin assets ──
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


class NuruInputBar(QFrame):
    """Barre de saisie V12 — sombre, arrondie, avec bouton d'envoi."""

    message_submitted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(56)
        self.setStyleSheet(f"""
            NuruInputBar {{
                background: {Color.BG_SURFACE};
                border-radius: {Radius.MEDIUM}px;
                border: 1px solid {Color.BORDER};
                margin: {Spacing.SM}px {Spacing.MD}px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.SM, Spacing.SM)
        layout.setSpacing(Spacing.SM)

        # Champ de saisie
        self._input = QLineEdit()
        self._input.setPlaceholderText("Message NURU…")
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {Color.TEXT_PRIMARY};
                font-size: {Typography.SIZE_BODY}px;
                font-family: {Typography.FAMILY_BODY};
                padding: {Spacing.XS}px 0;
                selection-background-color: {Color.CYAN}40;
            }}
            QLineEdit:focus {{ outline: none; }}
        """)
        self._input.returnPressed.connect(self._submit)
        layout.addWidget(self._input)

        # Bouton envoi
        self._send_btn = QPushButton("→")
        self._send_btn.setFixedSize(36, 36)
        self._send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Color.CYAN};
                color: #FFFFFF;
                border: none;
                border-radius: 18px;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {Color.CYAN_LIGHT}; }}
            QPushButton:pressed {{ background: {Color.CYAN_DIM}; }}
        """)
        self._send_btn.clicked.connect(self._submit)
        layout.addWidget(self._send_btn)

    def _submit(self):
        text = self._input.text().strip()
        if text:
            self.message_submitted.emit(text)
            self._input.clear()

    def focus_input(self):
        self._input.setFocus()


class NuruWindow(QMainWindow):
    """
    Fenêtre principale V12 — sombre, coins arrondis, Orb en haut.

    Remplace l'ancien CyberDashboard.
    """

    def __init__(self, event_bus=None):
        super().__init__()
        self._event_bus = event_bus
        self._floating_widget = None
        self._setup_window()
        self._build_ui()
        self._setup_shortcuts()
        self._setup_system_tray()
        self._setup_floating_widget()

    # ── Config fenêtre ──────────────────────────────────────────────

    def _setup_window(self):
        self.setWindowTitle("NURU V12")
        self.setMinimumSize(800, 600)
        self.resize(1100, 750)

        # Style global
        self.setStyleSheet(f"""
            QMainWindow {{
                background: {Color.BG_DEEP};
            }}
            QWidget {{
                font-family: {Typography.FAMILY_BODY};
            }}
        """)

        # Logo dans la barre de titre (si assets existent)
        icon_path = os.path.join(ASSETS_DIR, "nuru_logo_v5.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

    # ── UI ──────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet(f"background: {Color.BG_DEEP};")
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.SM)
        main_layout.setSpacing(Spacing.MD)

        # ── Top bar (titre + Orb) ──
        top_bar = QWidget()
        top_bar.setStyleSheet("background: transparent;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(0, 0, 0, 0)

        # Titre / wordmark
        wordmark_path = os.path.join(ASSETS_DIR, "nuru_logo_v5_wordmark.png")
        if os.path.exists(wordmark_path):
            title_label = QLabel()
            pixmap = __import__('PySide6.QtGui', fromlist=['QPixmap']).QPixmap(wordmark_path)
            title_label.setPixmap(pixmap.scaledToWidth(160, __import__('PySide6.QtCore', fromlist=['Qt']).Qt.SmoothTransformation))
        else:
            title_label = QLabel("NURU")
            title_label.setStyleSheet(f"""
                color: {Color.TEXT_PRIMARY};
                font-size: {Typography.SIZE_TITLE}px;
                font-weight: {Typography.WEIGHT_BOLD};
            """)
        top_layout.addWidget(title_label)
        top_layout.addStretch()

        # PresenceOrb
        self._orb = NuruPresenceOrb(orb_size=OrbSizes.WINDOW)
        top_layout.addWidget(self._orb)
        main_layout.addWidget(top_bar)

        # ── Zone de séparation subtile ──
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet(f"border: none; background: {Color.BORDER}; max-height: 1px;")
        main_layout.addWidget(separator)

        # ── Conversation ──
        self._conversation = ConversationSurface()
        main_layout.addWidget(self._conversation, stretch=1)

        # ── Barre de saisie ──
        self._input_bar = NuruInputBar()
        self._input_bar.message_submitted.connect(self._on_user_message)
        main_layout.addWidget(self._input_bar)

        self.setCentralWidget(central)

        # Welcome message
        self._conversation.add_message(
            "👋 Bonjour, je suis **NURU V12**. Comment puis-je t'aider aujourd'hui ?\n\n"
            "Utilise *⌥␣* pour le mode vocal, *⌘N* pour une nouvelle conversation.",
            is_user=False
        )

    # ── Raccourcis clavier ──────────────────────────────────────────

    def _setup_shortcuts(self):
        # ⌘N — Nouvelle conversation
        self._shortcut_new = QShortcut(QKeySequence("Ctrl+N"), self)
        self._shortcut_new.activated.connect(self._new_conversation)

        # ⎋ — Fermer / reset
        self._shortcut_escape = QShortcut(QKeySequence("Escape"), self)
        self._shortcut_escape.activated.connect(self._on_escape)

    # ── Floating widget ───────────────────────────────────────────

    def _setup_floating_widget(self):
        """Crée et affiche le widget flottant."""
        self._floating_widget = NuruFloatingWidget()
        # Sync Orb state avec le widget
        self._orb.state_changed.connect(self._on_orb_state_changed)
        # Position : coin bas-droit
        screen = QApplication.primaryScreen()
        if screen:
            geometry = screen.availableGeometry()
            x = geometry.right() - 180
            y = geometry.bottom() - 180
            self._floating_widget.move(x, y)
        self._floating_widget.show()

    # ── System tray ─────────────────────────────────────────────────

    def _setup_system_tray(self):
        self._tray = QSystemTrayIcon(self)
        icon_path = os.path.join(ASSETS_DIR, "nuru_logo_v5_dark.png")
        if os.path.exists(icon_path):
            self._tray.setIcon(QIcon(icon_path))
        self._tray.setToolTip("NURU V12")

        tray_menu = QMenu()
        show_action = tray_menu.addAction("Afficher")
        show_action.triggered.connect(self.show)
        new_action = tray_menu.addAction("Nouvelle conversation")
        new_action.triggered.connect(self._new_conversation)
        self._toggle_widget_action = tray_menu.addAction("Masquer widget")
        self._toggle_widget_action.triggered.connect(self._toggle_floating_widget)
        tray_menu.addSeparator()
        quit_action = tray_menu.addAction("Quitter")
        quit_action.triggered.connect(QApplication.instance().quit)

        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    # ── Handlers ────────────────────────────────────────────────────

    def _on_user_message(self, text: str):
        """Message utilisateur envoyé via la barre de saisie."""
        self._conversation.add_message(text, is_user=True)
        self._orb.set_state(OrbState.THINKING)

        # Réponse simulée pour test visuel
        QTimer.singleShot(800, lambda: self._simulate_response(text))

    def _simulate_response(self, user_text: str):
        """Réponse de test — à remplacer par l'appel LLM réel."""
        reply = f"Tu as dit : *{user_text}*\n\nJe suis la nouvelle interface **NURU V12** — design par Z.ai. Le cœur LLM n'est pas encore branché sur cette UI."
        self._conversation.add_message(reply, is_user=False)
        self._orb.set_state(OrbState.IDLE)

    def _new_conversation(self):
        self._conversation.clear()
        self._orb.set_state(OrbState.IDLE)
        self._input_bar.focus_input()

    def _on_escape(self):
        self._orb.set_state(OrbState.IDLE)

    def _toggle_floating_widget(self):
        """Affiche/masque le widget flottant."""
        if self._floating_widget and self._floating_widget.isVisible():
            self._floating_widget.hide()
            self._toggle_widget_action.setText("Afficher widget")
        else:
            if self._floating_widget:
                self._floating_widget.show()
            else:
                self._setup_floating_widget()
            self._toggle_widget_action.setText("Masquer widget")

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()
            self.raise_()
            self.activateWindow()

    def orb(self) -> NuruPresenceOrb:
        """Accès à l'Orb pour les événements externes."""
        return self._orb

    def floating_widget(self):
        return self._floating_widget

    def _on_orb_state_changed(self, state):
        """Sync l'état de l'Orb vers le widget flottant."""
        if self._floating_widget:
            self._floating_widget.set_orb_state(state)

    def conversation(self) -> ConversationSurface:
        return self._conversation
