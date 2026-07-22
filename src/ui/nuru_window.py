"""
NURU V15 — NuruWindow "NEON COGNITIVE"
——————————————————————————————
Fenêtre principale en verre morphique avec orb cybernétique.

Architecture visuelle :
  - Fond espace profond #05080F avec gradient 4 stops
  - Wordmark "NURU" en gradient néon cyan→violet
  - PresenceOrb (130px) — point focal avec particules orbitales
  - ConversationSurface (bulles verre morphique)
  - Input bar verre morphique avec glow cyan au focus
  - Menu intégré avec glass-morphism

Modes : chat (défaut) | voice | action
"""

import logging

from PySide6.QtCore import Qt, QTimer, QPointF, Signal
from PySide6.QtGui import (
    QColor, QPainter, QIcon, QPixmap, QLinearGradient, QRadialGradient,
    QConicalGradient, QFont, QKeySequence, QShortcut, QFontDatabase
)
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QApplication, QMenu,
)

from src.ui.tokens import Color, Typography, Radius, Spacing, OrbSizes, AnimDuration, WindowSizes
from src.ui.presence_orb import NuruPresenceOrb, OrbState
from src.ui.conversation_surface import ConversationSurface
from src.ui.preferences_dialog import PreferencesDialog
from src.ui.components.command_palette import CommandPalette, CommandItem

logger = logging.getLogger(__name__)


class NuruWordmark(QLabel):
    """Wordmark NURU en gradient néon cyan→violet avec badge version."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText("NURU  v15")
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background: transparent;")
        font = QFont(Typography.FAMILY_DISPLAY, 22, Typography.WEIGHT_BOLD)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 5)
        self.setFont(font)
        self.setFixedHeight(50)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Gradient cyan → violet pour "NURU"
        grad = QLinearGradient(0, 0, self.width() * 0.55, 0)
        grad.setColorAt(0.0, QColor(0, 240, 255))
        grad.setColorAt(0.7, QColor(124, 58, 237))
        grad.setColorAt(1.0, QColor(124, 58, 237, 200))
        painter.setPen(QColor(0, 240, 255))

        font = QFont(Typography.FAMILY_DISPLAY, 22, Typography.WEIGHT_BOLD)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 6)
        painter.setFont(font)

        # "NURU" en gradient
        painter.setPen(Qt.NoPen)
        painter.setBrush(grad)
        text_rect = self.rect().adjusted(0, 0, -60, 0)
        painter.drawText(text_rect, Qt.AlignCenter, "NURU")

        # "v15" en plus petit, violet
        v15_font = QFont(Typography.FAMILY_BODY, 9, Typography.WEIGHT_SEMIBOLD)
        painter.setFont(v15_font)
        painter.setPen(QColor(124, 58, 237, 180))
        v15_rect = self.rect().adjusted(self.width() - 50, 0, -4, -4)
        painter.drawText(v15_rect, Qt.AlignBottom | Qt.AlignRight, "v15")

        painter.end()


class NuruInputBar(QWidget):
    """Barre de saisie NEON COGNITIVE : input verre morphique + micro."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(60)
        self.setObjectName("InputBar")
        self.setStyleSheet("""
            QWidget#InputBar {
                background: transparent;
                border-top: 1px solid rgba(0, 240, 255, 0.06);
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.SM, Spacing.LG, Spacing.SM)
        layout.setSpacing(Spacing.SM)

        # Champ de saisie
        self._input = QLineEdit()
        self._input.setPlaceholderText("  Message NURU…")
        self._input.setMinimumHeight(40)
        layout.addWidget(self._input, stretch=1)

        # Bouton envoi
        self._send_btn = QPushButton("➤")
        self._send_btn.setObjectName("SendButton")
        self._send_btn.setFixedSize(40, 40)
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setToolTip("Envoyer")
        layout.addWidget(self._send_btn)

        # Bouton micro
        self._mic = QPushButton("🎤")
        self._mic.setObjectName("MicButton")
        self._mic.setToolTip("Hey NURU — mode vocal")
        self._mic.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self._mic)

    @property
    def input(self) -> QLineEdit:
        return self._input

    @property
    def mic_button(self) -> QPushButton:
        return self._mic

    @property
    def send_button(self) -> QPushButton:
        return self._send_btn


class NuruCentralWidget(QWidget):
    """
    Central widget NEON COGNITIVE — gradient espace profond + grille dynamique
    + ambient glow bicouleur (cyan + violet) derrière l'orb.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NuruCentral")
        self._current_theme = "dark"
        self._orb_y = Spacing.LG + OrbSizes.WINDOW

    def set_theme(self, theme: str):
        self._current_theme = theme
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r = Radius.WIDGET

        # ── 1. Fond gradient profond 4 stops ──
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(5, 8, 15))
        grad.setColorAt(0.25, QColor(8, 14, 28))
        grad.setColorAt(0.60, QColor(7, 12, 24))
        grad.setColorAt(1.0, QColor(5, 8, 15))
        painter.setBrush(grad)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), r, r)

        if self._current_theme == "dark":
            # ── 2. Ambient glow cyan (côté gauche) ──
            cyan_glow = QRadialGradient(w * 0.25, self._orb_y, OrbSizes.WINDOW * 1.8)
            cyan_glow.setColorAt(0.0, QColor(0, 240, 255, 12))
            cyan_glow.setColorAt(0.5, QColor(0, 240, 255, 4))
            cyan_glow.setColorAt(1.0, QColor(0, 240, 255, 0))
            painter.setBrush(cyan_glow)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(w * 0.25, self._orb_y), OrbSizes.WINDOW * 1.8, OrbSizes.WINDOW * 1.8)

            # ── 3. Ambient glow violet (côté droit) ──
            violet_glow = QRadialGradient(w * 0.75, self._orb_y + 60, OrbSizes.WINDOW * 1.6)
            violet_glow.setColorAt(0.0, QColor(124, 58, 237, 10))
            violet_glow.setColorAt(0.5, QColor(124, 58, 237, 3))
            violet_glow.setColorAt(1.0, QColor(124, 58, 237, 0))
            painter.setBrush(violet_glow)
            painter.drawEllipse(QPointF(w * 0.75, self._orb_y + 60), OrbSizes.WINDOW * 1.6, OrbSizes.WINDOW * 1.6)

        # ── 4. Grille de points subtile ──
        dot_alpha = 10 if self._current_theme == "dark" else 20
        painter.setBrush(QColor(255, 255, 255, dot_alpha // 2))
        spacing = 20
        dot_r = 1
        for x in range(spacing, w, spacing):
            for y in range(spacing, h, spacing):
                painter.drawEllipse(QPointF(x, y), dot_r, dot_r)

        painter.end()


class NuruWindow(QMainWindow):
    """
    Fenêtre principale NURU V15 (NEON COGNITIVE).

    Architecture :
      - 760×900, frameless (WA_TranslucentBackground)
      - Fond #05080F avec gradient 4 stops + grille de points + ambient glow bicouleur
      - Wordmark "NURU" en gradient néon
      - PresenceOrb (130px) centré — point focal
      - ConversationSurface — zone centrale
      - NuruInputBar verre morphique — bas
    """

    theme_change_requested = Signal(str)

    def __init__(self, engine=None):
        super().__init__()
        self._current_mode = "chat"
        self._current_theme = "dark"
        self._engine = engine

        self._setup_window()
        self._build_ui()

    # ── Fenêtre ──

    def _setup_window(self):
        self.setObjectName("NuruWindow")
        self.setWindowTitle("NURU v15")
        self.resize(WindowSizes.WINDOW_WIDTH, WindowSizes.WINDOW_HEIGHT)
        self.setMinimumSize(WindowSizes.WINDOW_MIN_WIDTH, WindowSizes.WINDOW_MIN_HEIGHT)
        self.setAttribute(Qt.WA_TranslucentBackground)
        try:
            self.setWindowIcon(QIcon("src/ui/assets/Gemini_Generated_Image_35cdt735cdt735cd_transparent.png"))
        except Exception:
            pass

    # ── UI ──

    def _build_ui(self):
        self._central = NuruCentralWidget(self)
        self.setCentralWidget(self._central)
        central = self._central

        layout = QVBoxLayout(central)
        layout.setContentsMargins(Spacing.LG, Spacing.SM, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.SM)

        # ── Title bar (glass) ──
        title_bar = QWidget()
        title_bar.setObjectName("TitleBar")
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(Spacing.XS, 0, Spacing.XS, 0)
        title_bar_layout.setSpacing(0)

        # Wordmark NURU + badge version
        self._wordmark = NuruWordmark()
        title_bar_layout.addWidget(self._wordmark, stretch=1)

        # Menu bouton
        self._menu_btn = QPushButton("☰")
        self._menu_btn.setFixedSize(34, 34)
        self._menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(12, 20, 40, 0.5);
                color: rgba(139, 160, 200, 0.6);
                border: 1px solid rgba(0, 240, 255, 0.08);
                border-radius: 8px;
                font-size: 16px;
            }}
            QPushButton:hover {{
                background: rgba(0, 240, 255, 0.10);
                color: {Color.CYAN};
                border-color: rgba(0, 240, 255, 0.20);
            }}
        """)
        self._build_menu()
        title_bar_layout.addWidget(self._menu_btn)
        layout.addWidget(title_bar)

        # ── PresenceOrb centré ──
        self._orb = NuruPresenceOrb(orb_size=OrbSizes.WINDOW)
        orb_container = QWidget()
        orb_container.setStyleSheet("background: transparent;")
        orb_layout = QHBoxLayout(orb_container)
        orb_layout.setContentsMargins(0, Spacing.SM, 0, Spacing.SM)
        orb_layout.addStretch()
        orb_layout.addWidget(self._orb)
        orb_layout.addStretch()
        layout.addWidget(orb_container)

        # ── ConversationSurface ──
        self._conversation = ConversationSurface()
        layout.addWidget(self._conversation, stretch=1)

        # Séparateur discret
        sep = QWidget()
        sep.setFixedHeight(1)
        self._sep = sep
        sep.setStyleSheet(f"background: {Color.BORDER};")
        layout.addWidget(sep)

        # ── Input Bar ──
        self._input_bar = NuruInputBar()
        self._input_bar.input.returnPressed.connect(self._on_send)
        self._input_bar.send_button.clicked.connect(self._on_send)
        self._input_bar.mic_button.clicked.connect(self._on_mic_click)
        layout.addWidget(self._input_bar)

        # ── Command Palette (Ctrl+K) ──
        self._palette = CommandPalette(self._central)
        self._palette.register_commands(self._build_palette_commands())
        self._sc_palette = QShortcut(QKeySequence("Ctrl+K"), self)
        self._sc_palette.activated.connect(self._palette.toggle)

    # ── Menu ──

    def _build_menu(self):
        self._menu = QMenu(self._menu_btn)
        self._menu.setStyleSheet(f"""
            QMenu {{
                background: rgba(10, 16, 30, 0.92);
                color: {Color.TEXT_PRIMARY};
                border: 1px solid {Color.BORDER};
                border-radius: 12px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 24px;
                border-radius: 6px;
                font-size: 12px;
            }}
            QMenu::item:selected {{
                background: rgba(0, 240, 255, 0.10);
                color: {Color.CYAN};
            }}
            QMenu::separator {{
                height: 1px;
                background: {Color.BORDER};
                margin: 4px 12px;
            }}
        """)
        self._theme_action = self._menu.addAction("🌙  Mode sombre")
        self._theme_action.triggered.connect(self._toggle_theme)
        self._menu.addSeparator()
        pref_action = self._menu.addAction("⚙  Préférences…")
        pref_action.triggered.connect(self._open_preferences)
        self._menu.addSeparator()
        quit_action = self._menu.addAction("  Quitter")
        quit_action.triggered.connect(QApplication.instance().quit)
        self._menu_btn.clicked.connect(self._show_menu)

    # ── Actions ──

    def _on_send(self):
        text = self._input_bar.input.text().strip()
        if not text:
            return
        self._input_bar.input.clear()
        self._conversation.add_message(text, is_user=True)

        if self._engine:
            self._engine.token_received.connect(
                self._on_engine_token, Qt.ConnectionType.UniqueConnection
            )
            self._engine.response_complete.connect(
                self._on_engine_done, Qt.ConnectionType.UniqueConnection
            )
            self._engine.error_occurred.connect(
                self._on_engine_error, Qt.ConnectionType.UniqueConnection
            )
            self._engine.strategy_changed.connect(
                self._on_strategy, Qt.ConnectionType.UniqueConnection
            )
            self._engine.response_metadata.connect(
                self._on_engine_metadata, Qt.ConnectionType.UniqueConnection
            )
            # V17 FIX : glue spaces seulement pour les providers cloud
            self._conversation._glue_spaces = (self._engine.current_provider != "local")
            self._conversation.start_stream()
            self._engine.send_message(text)
        else:
            QTimer.singleShot(500, lambda: self._add_response(f"Reçu : {text}"))

    def _on_engine_token(self, token: str):
        self._conversation.append_to_stream(token)

    def _on_engine_done(self, full_response: str):
        self._conversation.end_stream()
        self._conversation.hide_strategy()
        self._orb.set_state(OrbState.IDLE)

    def _on_engine_error(self, code: str, message: str):
        self._conversation.append_to_stream(f"\n\n[⚠️ {message}]")
        self._conversation.end_stream()
        self._conversation.hide_strategy()
        self._orb.set_state(OrbState.ERROR)

    def _on_strategy(self, key: str):
        if key == "completed":
            self._conversation.hide_strategy()
        else:
            self._conversation.set_strategy(key)

    def _on_engine_metadata(self, metadata: dict):
        self._conversation.set_metadata(metadata)

    def _build_palette_commands(self) -> list:
        def _new_chat():
            self._conversation.clear()
            self._input_bar.input.setFocus()
        def _toggle_theme_cmd():
            new_theme = "light" if self._current_theme == "dark" else "dark"
            self.theme_change_requested.emit(new_theme)
        def _open_prefs():
            dlg = PreferencesDialog(self)
            dlg.exec()
        def _quit():
            QApplication.instance().quit()
        def _clear_chat():
            self._conversation.clear()
            self._input_bar.input.clear()
        return [
            CommandItem("new_chat", "Nouvelle conversation", icon="💬", shortcut="⌘N",
                        category="Navigation", action=_new_chat),
            CommandItem("clear_chat", "Effacer le chat", icon="🗑", shortcut="",
                        category="Navigation", action=_clear_chat),
            CommandItem("toggle_theme", "Basculer le thème", icon="🌓", shortcut="",
                        category="Affichage", action=_toggle_theme_cmd),
            CommandItem("preferences", "Préférences…", icon="⚙", shortcut="",
                        category="Affichage", action=_open_prefs),
            CommandItem("quit", "Quitter NURU", icon="⎔", shortcut="⌘Q",
                        category="Système", action=_quit),
        ]

    def _add_response(self, text: str):
        self._conversation.add_message(text, is_user=False)
        self._orb.set_state(OrbState.IDLE)

    def _on_mic_click(self):
        self._orb.set_state(OrbState.LISTENING)
        logger.info("Micro cliqué — mode vocal")

    def _open_preferences(self):
        dlg = PreferencesDialog(self)
        dlg.exec()

    # ── Menu ──

    def _show_menu(self):
        self._menu.exec(self._menu_btn.mapToGlobal(
            self._menu_btn.rect().bottomRight()
        ))

    def _toggle_theme(self):
        new_theme = "light" if self._current_theme == "dark" else "dark"
        self.theme_change_requested.emit(new_theme)

    def set_theme(self, theme: str):
        self._current_theme = theme
        border_color = Color.LIGHT["border"] if theme == "light" else Color.BORDER
        self._sep.setStyleSheet(f"background: {border_color};")
        self._central.set_theme(theme)
        self.update()

    # ── Propriétés ──

    @property
    def orb(self) -> NuruPresenceOrb:
        return self._orb

    @property
    def conversation(self) -> ConversationSurface:
        return self._conversation

    @property
    def input_bar(self) -> NuruInputBar:
        return self._input_bar

    def set_mode(self, mode: str):
        self._current_mode = mode
        if mode == "voice":
            self.setWindowOpacity(0.3)
        else:
            self.setWindowOpacity(1.0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_palette') and self._palette.is_visible:
            self._palette.setGeometry(self._central.rect())
