"""
NURU V12 — AmbientApp (Z.ai design exact).

Architecture complète Z.ai :
  - NuruWindow (QMainWindow 720×860) — fenêtre principale chat
  - TrayIcon (menu bar macOS) — toujours accessible
  - FloatingWidget 160×160 — verre dépoli, always-on-top
  - VoiceOverlay (⌥␣) — mode vocal frameless
  - ChatOverlay (⌘N) — nouvelle conversation
  - Raccourcis : ⌥␣ ⌘⇧N ⌘N ⎋

Cycle de vie Z.ai (doc §163-164) :
  - Mode Chat Texte (défaut) : fenêtre avec PresenceOrb, ConversationSurface, InputBar
  - Mode Vocal (⌥␣) : VoiceOverlay + fenêtre opacity 0.3
  - Mode Action (transitoire) : Orb progression + carte inline
"""

import logging
import os

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPointF
from PySide6.QtGui import QIcon, QAction, QKeySequence, QShortcut, QColor, QPainter, QPixmap, QFont
from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QLineEdit, QFrame, QSizePolicy,
)

from src.ui.tokens import Color, Typography, Radius, Spacing, OrbSizes, AnimDuration, WindowSizes
from src.ui.presence_orb import NuruPresenceOrb, OrbState
from src.ui.floating_widget import NuruFloatingWidget
from src.ui.voice_overlay import VoiceOverlay
from src.ui.nuru_window import NuruWindow

logger = logging.getLogger(__name__)

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


class ChatOverlay(QWidget):
    """
    Overlay de nouvelle conversation (⌘N — Z.ai).

    Fenêtre temporaire frameless pour démarrer un nouveau fil.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        screen = QApplication.primaryScreen()
        w, h = 480, 500
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - w) // 2
            y = geo.y() + (geo.height() - h) // 2
            self.move(x, y)
        self.setFixedSize(w, h)

        self.setStyleSheet(f"""
            ChatOverlay {{
                background: rgba(13, 17, 23, 0.95);
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

        title = QLabel("Nouveau fil")
        title.setStyleSheet(f"""
            color: {Color.TEXT_PRIMARY};
            font-size: {Typography.SIZE_HEADING_2}pt;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            background: transparent;
        """)
        top_layout.addWidget(title)
        top_layout.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Color.TEXT_MUTED};
                border: none; font-size: 14px;
                border-radius: 12px;
            }}
            QPushButton:hover {{ background: rgba(248,81,73,0.2); color: {Color.ERROR}; }}
        """)
        close_btn.clicked.connect(self.hide)
        top_layout.addWidget(close_btn)
        layout.addWidget(top)

        # Zone messages
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
                background: {Color.BG_DEEP};
                color: {Color.TEXT_PRIMARY};
                border: 1px solid {Color.BORDER};
                border-radius: {Radius.MEDIUM}px;
                padding: 10px 14px;
                font-size: {Typography.SIZE_BODY}pt;
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
            QPushButton:hover {{ background: rgba(88,213,227,0.8); }}
        """)
        send_btn.clicked.connect(self._send)
        input_layout.addWidget(send_btn)
        layout.addWidget(input_row)

        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(AnimDuration.OVERLAY_SHOW)
        self._opacity_anim.setEasingCurve(QEasingCurve.OutCubic)

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
        bubble = QLabel(f"<b style='color:{Color.TEXT_PRIMARY}'>Vous</b> : {text}")
        bubble.setWordWrap(True)
        bubble.setStyleSheet(f"""
            background: rgba(88,213,227,0.1);
            color: {Color.TEXT_PRIMARY};
            border-radius: {Radius.MEDIUM}px;
            padding: 8px 12px;
            font-size: {Typography.SIZE_BODY}pt;
        """)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, bubble)

        QTimer.singleShot(500, lambda: self._respond(f"Reçu : *{text}*"))

    def _respond(self, text: str):
        bubble = QLabel(f"<b style='color:{Color.CYAN}'>NURU</b> : {text}")
        bubble.setWordWrap(True)
        bubble.setStyleSheet(f"""
            background: {Color.BG_ELEVATED};
            color: {Color.TEXT_PRIMARY};
            border-radius: {Radius.MEDIUM}px;
            padding: 8px 12px;
            font-size: {Typography.SIZE_BODY}pt;
        """)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, bubble)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
        super().keyPressEvent(event)


class AmbientApp:
    """
    Application NURU V12 — orchestre tous les composants Z.ai.

    Gère : NuruWindow, TrayIcon, FloatingWidget, VoiceOverlay, ChatOverlay.
    """

    def __init__(self, app: QApplication):
        self._app = app
        self._orb_state = OrbState.IDLE

        # 1. Fenêtre principale NURU (Z.ai: QMainWindow 720×860)
        self._window = NuruWindow()

        # 2. VoiceOverlay (⌥␣)
        self._voice_overlay = VoiceOverlay()

        # 3. FloatingWidget (⌘⇧N)
        self._floating_widget = NuruFloatingWidget()

        # 4. ChatOverlay (⌘N)
        self._chat_overlay = ChatOverlay()

        # 5. Tray icon
        self._setup_tray()

        # 6. Raccourcis
        self._setup_shortcuts()

        # 7. Sync états Orb
        self._window.orb.state_changed.connect(self._on_orb_state_changed)
        self._floating_widget.orb.state_changed.connect(self._on_orb_state_changed)

        # Afficher composants initiaux
        self._window.show()
        self._show_floating()

    # ── Tray (Z.ai: §199-200) ──

    def _setup_tray(self):
        self._tray = QSystemTrayIcon()
        self._update_tray_icon()
        self._tray.setToolTip("NURU V12")

        menu = QMenu()

        open_action = menu.addAction("Ouvrir NURU")
        open_action.triggered.connect(self._window.show)

        voice_action = menu.addAction("Mode vocal ⌥␣")
        voice_action.triggered.connect(self._toggle_voice)

        menu.addSeparator()

        toggle_widget = menu.addAction("Afficher Widget")
        toggle_widget.triggered.connect(self._toggle_floating)
        toggle_widget.setCheckable(True)
        toggle_widget.setChecked(True)
        self._toggle_widget_action = toggle_widget

        menu.addSeparator()

        pref_action = menu.addAction("Préférences…")
        quit_action = menu.addAction("Quitter")
        quit_action.triggered.connect(self._app.quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _update_tray_icon(self):
        """Icône 22×22px — Z.ai: monochrome selon état."""
        pm = QPixmap(22, 22)
        pm.fill(Qt.transparent)

        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing)

        color_map = {
            OrbState.IDLE: Color.TEXT_MUTED,
            OrbState.LISTENING: Color.CYAN,
            OrbState.THINKING: Color.CYAN,
            OrbState.SPEAKING: Color.CYAN,
            OrbState.ACTING: Color.WARM,
            OrbState.ERROR: Color.ERROR,
        }
        color = color_map.get(self._orb_state, Color.TEXT_MUTED)

        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)
        # Losange/diamant cyan (Z.ai: diamant cyan lumineux)
        cx, cy = 11, 11
        size = 12
        points = [
            QPointF(cx, cy - size // 2),
            QPointF(cx + size // 2, cy),
            QPointF(cx, cy + size // 2),
            QPointF(cx - size // 2, cy),
        ]
        painter.drawPolygon(points)
        painter.end()

        self._tray.setIcon(QIcon(pm))

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._window.show()
            self._window.raise_()

    # ── FloatingWidget ──

    def _show_floating(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            size = WindowSizes.FLOATING_SIZE
            self._floating_widget.move(
                geo.right() - size - 20,
                geo.bottom() - size - 20,
            )
        self._floating_widget.show()

    def _toggle_floating(self):
        if self._floating_widget.isVisible():
            self._floating_widget.hide()
            self._toggle_widget_action.setText("Afficher Widget")
        else:
            self._show_floating()
            self._toggle_widget_action.setText("Masquer Widget")

    # ── Raccourcis (Z.ai: §204-225) ──

    def _setup_shortcuts(self):
        self._shortcut_host = QWidget()
        self._shortcut_host.setWindowFlags(Qt.Tool)

        # ⌥␣ — Voice (global)
        self._sc_voice = QShortcut(QKeySequence("Alt+Space"), self._shortcut_host)
        self._sc_voice.activated.connect(self._toggle_voice)

        # ⌘⇧N — Floating widget (global)
        self._sc_widget = QShortcut(QKeySequence("Ctrl+Shift+N"), self._shortcut_host)
        self._sc_widget.activated.connect(self._toggle_floating)

        # ⌘N — Nouvelle conversation (dans fenêtre active ou overlay)
        self._sc_chat = QShortcut(QKeySequence("Ctrl+N"), self._shortcut_host)
        self._sc_chat.activated.connect(self._new_chat)

        self._shortcut_host.show()

    # ── Voice ──

    def _toggle_voice(self):
        if self._voice_overlay.isVisible():
            self._voice_overlay.hide_overlay()
        else:
            self._orb_state = OrbState.LISTENING
            self._update_tray_icon()
            self._window.orb.set_state(OrbState.LISTENING)
            self._floating_widget.set_orb_state(OrbState.LISTENING)
            self._window.set_mode("voice")
            self._voice_overlay.show_overlay()
            self._voice_overlay.closed.connect(self._on_voice_closed)

    def _on_voice_closed(self):
        self._window.set_mode("chat")
        self._orb_state = OrbState.IDLE
        self._update_tray_icon()
        self._window.orb.set_state(OrbState.IDLE)
        self._floating_widget.set_orb_state(OrbState.IDLE)

    # ── Chat ──

    def _new_chat(self):
        self._orb_state = OrbState.IDLE
        self._window.orb.set_state(OrbState.IDLE)
        self._floating_widget.set_orb_state(OrbState.IDLE)
        self._chat_overlay.show_overlay()

    # ── Sync ──

    def _on_orb_state_changed(self, state: OrbState):
        self._orb_state = state
        self._update_tray_icon()
        # Sync l'autre orb
        if self._window.orb.state != state:
            self._window.orb.set_state(state)
        if self._floating_widget.orb.state != state:
            self._floating_widget.set_orb_state(state)

    # ── API ──

    @property
    def window(self) -> NuruWindow:
        return self._window

    @property
    def floating_widget(self):
        return self._floating_widget

    @property
    def voice_overlay(self):
        return self._voice_overlay
