"""
NURU V12 — AmbientApp (Z.ai design exact).

Application tray-first, sans fenêtre principale persistante.
"Pas de fenêtre principale, pas de cockpit 3 colonnes."

Architecture :
  - Tray icon (QSystemTrayIcon) — diamant cyan dans menu bar macOS
  - FloatingWidget 220×160 — verre dépoli, always-on-top
  - VoiceOverlay — frameless, WaveformRings + Transcript
  - ChatOverlay — conversation temporaire (⌘N)
  - Raccourcis globaux : ⌥␣ vocal, ⌘⇧N widget, ⌘N chat

Cycle de vie :
  Start → Tray + FloatingWidget (ambient)
  ⌥␣ → VoiceOverlay apparition (scale+opacity 250ms)
  ⌘N → ChatOverlay (transcription + réponse)
  Inactivité 30s → FloatingWidget opacity 0.4
"""

import logging
import os

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QIcon, QAction, QKeySequence, QShortcut, QColor, QPainter, QPixmap, QFont
from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QLineEdit, QFrame, QSizePolicy,
)

from src.ui.tokens import Color, Typography, Radius, Spacing, OrbSizes, AnimDuration, WidgetSizes
from src.ui.presence_orb import NuruPresenceOrb, OrbState
from src.ui.floating_widget import NuruFloatingWidget
from src.ui.voice_overlay import VoiceOverlay

logger = logging.getLogger(__name__)

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


class ChatOverlay(QWidget):
    """
    Overlay de conversation temporaire (Z.ai).

    Apparaît sur ⌘N, se ferme sur ⎋.
    Pas de panneau persistant — juste quand nécessaire.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._setup_shortcuts()

    def _build_ui(self):
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Taille
        screen = QApplication.primaryScreen()
        w, h = 480, 500
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - w) // 2
            y = geo.y() + (geo.height() - h) // 2
            self.move(x, y)
        self.setFixedSize(w, h)

        # Fond
        self.setStyleSheet(f"""
            ChatOverlay {{
                background: rgba(7, 10, 16, 0.95);
                border-radius: {Radius.LARGE}px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.SM)

        # Top bar
        top = QWidget()
        top.setStyleSheet("background: transparent;")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("NURU")
        title.setStyleSheet(f"""
            color: {Color.TEXT_PRIMARY};
            font-size: {Typography.SIZE_BODY}px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            background: transparent;
        """)
        top_layout.addWidget(title)
        top_layout.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Color.TEXT_DIM};
                border: none; font-size: 14px;
                border-radius: 12px;
            }}
            QPushButton:hover {{ background: rgba(255,77,106,0.2); color: {Color.ERROR}; }}
        """)
        close_btn.clicked.connect(self.hide)
        top_layout.addWidget(close_btn)
        layout.addWidget(top)

        # Zone conversation
        self._messages = QWidget()
        self._messages.setStyleSheet("background: transparent;")
        self._msg_layout = QVBoxLayout(self._messages)
        self._msg_layout.setContentsMargins(0, 0, 0, 0)
        self._msg_layout.setSpacing(Spacing.SM)
        self._msg_layout.addStretch()
        layout.addWidget(self._messages, stretch=1)

        # Input
        input_row = QWidget()
        input_row.setStyleSheet("background: transparent;")
        input_layout = QHBoxLayout(input_row)
        input_layout.setContentsMargins(0, 0, 0, 0)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Message NURU…")
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {Color.BG_CARD};
                color: {Color.TEXT_PRIMARY};
                border: 1px solid {Color.BORDER};
                border-radius: {Radius.MEDIUM}px;
                padding: 10px 14px;
                font-size: {Typography.SIZE_BODY}px;
                font-family: {Typography.FAMILY_BODY};
            }}
            QLineEdit:focus {{ border-color: {Color.CYAN}; }}
        """)
        self._input.returnPressed.connect(self._send)
        input_layout.addWidget(self._input, stretch=1)

        send_btn = QPushButton("→")
        send_btn.setFixedSize(36, 36)
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Color.CYAN}; color: #FFF;
                border: none; border-radius: 18px;
                font-size: 16px;
            }}
            QPushButton:hover {{ background: {Color.CYAN_DIM}; }}
        """)
        send_btn.clicked.connect(self._send)
        input_layout.addWidget(send_btn)
        layout.addWidget(input_row)

        # Opacité animation
        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(AnimDuration.OVERLAY_SHOW)
        self._opacity_anim.setEasingCurve(QEasingCurve.OutCubic)

    def _setup_shortcuts(self):
        # Pour les événements clavier
        pass  # géré via keyPressEvent

    def show_overlay(self):
        self._opacity_anim.setStartValue(0.0)
        self._opacity_anim.setEndValue(1.0)
        self.show()
        self.raise_()
        self._opacity_anim.start()
        self._input.setFocus()

    def _send(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()

        # Bulle utilisateur
        user_bubble = QLabel(f"<b style='color:{Color.TEXT_PRIMARY}'>Vous</b> : {text}")
        user_bubble.setWordWrap(True)
        user_bubble.setStyleSheet(f"""
            background: rgba(0, 212, 255, 0.1);
            color: {Color.TEXT_PRIMARY};
            border-radius: {Radius.MEDIUM}px;
            padding: 8px 12px;
            font-size: {Typography.SIZE_BODY}px;
        """)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, user_bubble)

        # Simuler réponse NURU
        QTimer.singleShot(500, lambda: self._respond(f"Reçu : *{text}*"))

    def _respond(self, text: str):
        bubble = QLabel(f"<b style='color:{Color.CYAN}'>NURU</b> : {text}")
        bubble.setWordWrap(True)
        bubble.setStyleSheet(f"""
            background: {Color.BG_CARD};
            color: {Color.TEXT_PRIMARY};
            border-radius: {Radius.MEDIUM}px;
            padding: 8px 12px;
            font-size: {Typography.SIZE_BODY}px;
        """)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, bubble)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
        super().keyPressEvent(event)


class AmbientApp:
    """
    Application NURU V12 — mode ambiant (Z.ai).

    Pas de main window. Juste tray + floating widget + overlays.
    """

    def __init__(self, app: QApplication):
        self._app = app
        self._orb_state = OrbState.IDLE

        # Composants
        self._setup_tray()
        self._floating_widget = NuruFloatingWidget()
        self._voice_overlay = VoiceOverlay()
        self._chat_overlay = ChatOverlay()
        self._setup_shortcuts()

        # Sync états
        self._floating_widget.orb.state_changed.connect(self._on_orb_state_changed)

        # Afficher floating widget
        self._show_floating()

    # ── Tray ──

    def _setup_tray(self):
        self._tray = QSystemTrayIcon()

        # Icône dynamique diamant cyan
        self._update_tray_icon()

        self._tray.setToolTip("NURU V12")

        menu = QMenu()

        voice_action = menu.addAction("Mode vocal ⌥␣")
        voice_action.triggered.connect(self._toggle_voice)

        chat_action = menu.addAction("Nouvelle conversation ⌘N")
        chat_action.triggered.connect(self._toggle_chat)

        menu.addSeparator()

        toggle_widget = menu.addAction("Masquer widget")
        toggle_widget.triggered.connect(self._toggle_floating)

        menu.addSeparator()

        quit_action = menu.addAction("Quitter")
        quit_action.triggered.connect(self._app.quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _update_tray_icon(self):
        """Génère une icône diamant cyan dynamique selon l'état."""
        pm = QPixmap(22, 22)
        pm.fill(Qt.transparent)

        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing)

        center_x, center_y = 11, 11
        size = 14

        # Cercle selon état
        color_map = {
            OrbState.IDLE: Color.TEXT_DIM,
            OrbState.LISTENING: Color.CYAN,
            OrbState.THINKING: Color.CYAN,
            OrbState.SPEAKING: Color.CYAN,
            OrbState.ACTING: Color.WARNING,
            OrbState.ERROR: Color.ERROR,
            OrbState.RESPOND: Color.CYAN,
        }
        color = color_map.get(self._orb_state, Color.TEXT_DIM)

        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(
            (22 - size) // 2, (22 - size) // 2, size, size, 4, 4
        )
        painter.end()

        self._tray.setIcon(QIcon(pm))

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._toggle_voice()

    # ── Floating widget ──

    def _show_floating(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self._floating_widget.move(
                geo.right() - WidgetSizes.FLOATING_WIDTH - 20,
                geo.bottom() - WidgetSizes.FLOATING_HEIGHT - 20,
            )
        self._floating_widget.show()

    def _toggle_floating(self):
        if self._floating_widget.isVisible():
            self._floating_widget.hide()
        else:
            self._show_floating()

    # ── Raccourcis ──

    def _setup_shortcuts(self):
        # On utilise QShortcut sur une fenêtre invisible comme réceptacle
        self._shortcut_host = QWidget()
        self._shortcut_host.setWindowFlags(Qt.Tool)

        # ⌥␣ — Voice overlay
        self._sc_voice = QShortcut(QKeySequence("Alt+Space"), self._shortcut_host)
        self._sc_voice.activated.connect(self._toggle_voice)

        # ⌘⇧N — Toggle floating widget
        self._sc_widget = QShortcut(QKeySequence("Ctrl+Shift+N"), self._shortcut_host)
        self._sc_widget.activated.connect(self._toggle_floating)

        # ⌘N — Chat overlay
        self._sc_chat = QShortcut(QKeySequence("Ctrl+N"), self._shortcut_host)
        self._sc_chat.activated.connect(self._toggle_chat)

        self._shortcut_host.show()

    # ── Voice Overlay ──

    def _toggle_voice(self):
        if self._voice_overlay.isVisible():
            self._voice_overlay.hide_overlay()
        else:
            self._orb_state = OrbState.LISTENING
            self._update_tray_icon()
            self._floating_widget.set_orb_state(OrbState.LISTENING)
            self._voice_overlay.show_overlay()
            self._voice_overlay.closed.connect(self._on_voice_closed)
            # Simuler transcription
            QTimer.singleShot(1500, lambda: self._voice_overlay.update_transcript("Bonjour NURU"))
            QTimer.singleShot(3000, lambda: self._voice_overlay.update_state("Analyse…"))
            QTimer.singleShot(4000, lambda: self._voice_overlay.update_state("Terminé"))

    def _on_voice_closed(self):
        self._orb_state = OrbState.IDLE
        self._update_tray_icon()
        self._floating_widget.set_orb_state(OrbState.IDLE)

    # ── Chat ──

    def _toggle_chat(self):
        if self._chat_overlay.isVisible():
            self._chat_overlay.hide()
        else:
            self._orb_state = OrbState.THINKING
            self._update_tray_icon()
            self._floating_widget.set_orb_state(OrbState.THINKING)
            self._chat_overlay.show_overlay()

    # ── Sync ──

    def _on_orb_state_changed(self, state: OrbState):
        self._orb_state = state
        self._update_tray_icon()

    # ── API externe ──

    @property
    def floating_widget(self):
        return self._floating_widget

    @property
    def voice_overlay(self):
        return self._voice_overlay
