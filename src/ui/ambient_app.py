"""
NURU V12 — AmbientApp (DM-1 "Deep Cyan") — CORRIGÉ.

Architecture complète DM-1 V12 :
  - NuruWindow (QMainWindow 720×860) — fenêtre principale chat, fond gradient bleu
  - NURUTrayIcon (menu bar macOS) — diamant cyan, toujours accessible, sync OrbState
  - NuruFloatingWidget 260×180 — verre dépoli, always-on-top
  - VoiceOverlay (⌥␣) — mode vocal frameless (optionnel, graceful fallback)
  - ChatOverlay (⌘N) — nouvelle conversation
  - Raccourcis : ⌥␣ ⌘⇧N ⌘N ⎋

Corrections V12 :
  - Import NURUTrayIcon depuis src.ui.tray_icon (nouveau module, compatible OrbState)
  - VoiceOverlay : import optionnel (try/except) si non encore implémenté
  - Tray icon sync automatique avec orb state
  - Tous les imports préservent NuruPresenceOrb, NuruFloatingWidget, OrbState

Imports compatibles :
  from src.ui.tokens import Color, Typography, Radius, Spacing, OrbSizes, AnimDuration, WindowSizes
  from src.ui.presence_orb import NuruPresenceOrb, OrbState
  from src.ui.floating_widget import NuruFloatingWidget
  from src.ui.nuru_window import NuruWindow
  from src.ui.tray_icon import NURUTrayIcon
"""

import logging
import os

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPointF
from PySide6.QtGui import (
    QIcon, QAction, QKeySequence, QShortcut, QColor, QPainter,
    QPixmap, QFont, QLinearGradient,
)
from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QLineEdit, QFrame, QSizePolicy,
)

from src.ui.tokens import Color, Typography, Radius, Spacing, OrbSizes, AnimDuration, WindowSizes
from src.ui.presence_orb import NuruPresenceOrb, OrbState
from src.ui.floating_widget import NuruFloatingWidget
from src.ui.nuru_window import NuruWindow
from src.ui.tray_icon import NURUTrayIcon
from src.core.conversation_engine import ConversationEngine

logger = logging.getLogger(__name__)

# ── VoiceOverlay : import optionnel ──
# Si le module n'existe pas encore, on crée un stub silencieux
try:
    from src.ui.voice_overlay import VoiceOverlay
    _HAS_VOICE_OVERLAY = True
except ImportError:
    _HAS_VOICE_OVERLAY = False
    logger.info("VoiceOverlay non disponible — mode vocal désactivé")


class ChatOverlay(QWidget):
    """
    Overlay de nouvelle conversation (⌘N — DM-1).

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
                background: rgba(10, 14, 23, 0.95);
                border-radius: {Radius.WIDGET}px;
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
            QPushButton:hover {{ background: rgba(255, 77, 106, 0.2); color: {Color.ERROR}; }}
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
            QPushButton:hover {{ background: rgba(0, 180, 200, 0.8); }}
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
            background: rgba(0, 212, 255, 0.10);
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
            background: {Color.BG_SURFACE1};
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
    Application NURU V12 — orchestre tous les composants DM-1.

    Corrigé V12 :
      - NURUTrayIcon : importé depuis src.ui.tray_icon (compatible OrbState)
      - Tray icon sync automatique via orb.state_changed
      - VoiceOverlay : import optionnel (graceful fallback)
      - NuruWindow : fond gradient bleu V12
      - NuruFloatingWidget : 260×180 DM-1
    """

    def __init__(self, app: QApplication):
        self._app = app
        self._current_theme = "dark"
        self._orb_state = OrbState.IDLE

        # 0. ConversationEngine — pont backend (démarré en arrière-plan)
        self._engine = ConversationEngine()
        self._engine.state_changed.connect(self._on_engine_state)
        self._engine.start()

        # 1. Fenêtre principale NURU (DM-1: QMainWindow 720×860)
        self._window = NuruWindow(engine=self._engine)

        # 2. VoiceOverlay (⌥␣) — optionnel
        if _HAS_VOICE_OVERLAY:
            self._voice_overlay = VoiceOverlay()
        else:
            self._voice_overlay = None
            logger.info("VoiceOverlay non chargé — raccourci vocal désactivé")

        # 3. FloatingWidget (⌘⇧N) — DM-1: 260×180
        self._floating_widget = NuruFloatingWidget()

        # 4. ChatOverlay (⌘N)
        self._chat_overlay = ChatOverlay()

        # 5. Tray icon — DM-1: diamant cyan lumineux (module dédié)
        self._tray = NURUTrayIcon(app)
        self._connect_tray_actions()
        self._tray.show()

        # 6. Raccourcis
        self._setup_shortcuts()

        # 7. Sync états Orb → Tray Icon
        self._window.orb.state_changed.connect(self._on_orb_state_changed)

        # 8. Sync thème → window menu
        self._window.theme_change_requested.connect(self._on_theme_change_requested)

        # 9. Charger le QSS initial (dark)
        self._load_qss("styles.qss")

        # Afficher composants initiaux
        self._window.show()
        self._show_floating()

    # ── Tray DM-1: actions connectées ──

    def _connect_tray_actions(self):
        self._tray.show_action.triggered.connect(self._show_window)
        self._tray.voice_action.triggered.connect(self._toggle_voice)
        self._tray.widget_action.triggered.connect(self._toggle_floating)
        self._tray.pref_action.triggered.connect(self._open_preferences)
        self._tray.quit_action.triggered.connect(self._app.quit)
        self._tray.tray.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()

    # ── FloatingWidget ──

    def _show_floating(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self._floating_widget.move(
                geo.right() - WindowSizes.FLOATING_WIDTH - 20,
                geo.bottom() - WindowSizes.FLOATING_HEIGHT - 20 - 60,
            )
        self._floating_widget.show()

    def _toggle_floating(self):
        if self._floating_widget.isVisible():
            self._floating_widget.hide()
            self._tray.widget_action.setText("  Afficher Widget")
            self._tray.widget_action.setChecked(False)
        else:
            self._show_floating()
            self._tray.widget_action.setText("  Masquer Widget")
            self._tray.widget_action.setChecked(True)

    # ── Raccourcis DM-1 ──

    def _setup_shortcuts(self):
        self._shortcut_host = QWidget()
        self._shortcut_host.setWindowFlags(Qt.Tool)

        self._sc_voice = QShortcut(QKeySequence("Alt+Space"), self._shortcut_host)
        self._sc_voice.activated.connect(self._toggle_voice)

        self._sc_widget = QShortcut(QKeySequence("Ctrl+Shift+N"), self._shortcut_host)
        self._sc_widget.activated.connect(self._toggle_floating)

        self._sc_chat = QShortcut(QKeySequence("Ctrl+N"), self._shortcut_host)
        self._sc_chat.activated.connect(self._new_chat)

        self._shortcut_host.show()

    # ── Voice ──

    def _toggle_voice(self):
        if not _HAS_VOICE_OVERLAY or self._voice_overlay is None:
            logger.warning("VoiceOverlay non disponible")
            return

        if self._voice_overlay.isVisible():
            self._voice_overlay.hide_overlay()
        else:
            self._orb_state = OrbState.LISTENING
            self._window.orb.set_state(OrbState.LISTENING)
            self._window.set_mode("voice")
            self._voice_overlay.show_overlay()

    # ── Chat ──

    def _new_chat(self):
        self._orb_state = OrbState.IDLE
        self._window.orb.set_state(OrbState.IDLE)
        self._chat_overlay.show_overlay()

    # ── Window ──

    def _show_window(self):
        self._window.show()
        self._window.raise_()

    def _open_preferences(self):
        from src.ui.preferences_dialog import PreferencesDialog
        dlg = PreferencesDialog(self._window)
        dlg.exec()

    # ── Sync Orb → Tray ──

    def _on_orb_state_changed(self, state: OrbState):
        """Sync automatique : OrbState → tray icon + floating widget."""
        self._orb_state = state
        self._tray.set_state(state)

        # Sync floating widget status text
        state_labels = {
            OrbState.IDLE:      ("Assistant prêt", Color.TEXT_SECONDARY),
            OrbState.LISTENING: ("En écoute...", "#00E599"),
            OrbState.THINKING:  ("Réflexion...", "#FFB800"),
            OrbState.SPEAKING:  ("Parle...", Color.CYAN),
            OrbState.ACTING:    ("Action...", Color.CYAN),
            OrbState.ERROR:     ("Erreur", Color.ROSE),
        }
        label, color = state_labels.get(state, ("Assistant prêt", Color.TEXT_SECONDARY))
        self._floating_widget.setStatus(label, color)

    # ── Engine ──

    def _on_engine_state(self, state: OrbState):
        """Relaye l'état du ConversationEngine → orb."""
        self._window.orb.set_state(state)

    # ── Thème ──

    def _load_qss(self, filename: str):
        """Charge un fichier .qss et l'applique à l'application."""
        path = os.path.join(os.path.dirname(__file__), filename)
        if os.path.exists(path):
            with open(path, "r") as f:
                self._app.setStyleSheet(f.read())
        else:
            logger.warning(f"Fichier QSS introuvable : {path}")

    def _on_theme_change_requested(self, theme: str):
        """Bascule entre thème sombre et clair."""
        self._current_theme = theme
        is_dark = theme == "dark"

        # 1. Appliquer le QSS
        qss_file = "styles.qss" if is_dark else "styles_light.qss"
        self._load_qss(qss_file)

        # 2. Mettre à jour le NuruWindow (fond inline + séparateur)
        self._window.set_theme(theme)
        action_text = "🌙  Mode sombre" if is_dark else "☀️  Mode clair"
        self._window._theme_action.setText(action_text)

        # 3. Floating widget
        self._floating_widget.apply_theme(theme)

        # 4. Redessiner tous les composants
        self._window.update()
        self._floating_widget.update()

        logger.info(f"Thème changé : {theme}")

    # ── API ──

    @property
    def window(self) -> NuruWindow:
        return self._window

    @property
    def floating_widget(self) -> NuruFloatingWidget:
        return self._floating_widget

    @property
    def tray(self) -> NURUTrayIcon:
        return self._tray

    @property
    def voice_overlay(self):
        return self._voice_overlay
