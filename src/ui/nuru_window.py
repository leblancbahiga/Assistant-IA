"""
NURU V12 — NuruWindow (DM-1 "Deep Cyan").

QMainWindow minimal — pas de cockpit.

DM-1 spec :
  - resize(720, 860), minimumSize(480, 600)
  - Frameless (WA_TranslucentBackground)
  - Fond #0A0E17 avec grille de points DM-1
  - PresenceOrb (120px) — point focal visuel, centré en haut
  - ConversationSurface (bulles chat) au centre
  - Input bar + micro en bas — bordure cyan au focus
  - ContextStrip optionnel

Trois modes : chat (défaut) | voice | action
"""

import logging

from PySide6.QtCore import Qt, QTimer, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QIcon, QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QApplication, QMenu,
)

from src.ui.tokens import Color, Typography, Radius, Spacing, OrbSizes, AnimDuration, WindowSizes
from src.ui.presence_orb import NuruPresenceOrb, OrbState
from src.ui.conversation_surface import ConversationSurface
from src.ui.preferences_dialog import PreferencesDialog

logger = logging.getLogger(__name__)


class NuruInputBar(QWidget):
    """Barre de saisie DM-1 : input + micro. Bordure cyan au focus."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, 0, Spacing.LG, 0)
        layout.setSpacing(Spacing.SM)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Message NURU…")
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {Color.BG_SURFACE1};
                color: {Color.TEXT_PRIMARY};
                border: 1px solid {Color.BORDER};
                border-radius: {Radius.MEDIUM}px;
                padding: 10px 14px;
                font-size: {Typography.SIZE_BODY}pt;
                font-family: {Typography.FAMILY_BODY};
                selection-background-color: rgba(0, 212, 255, 0.25);
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
                background: {Color.BG_SURFACE1};
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
    Fenêtre principale NURU V12 (DM-1 "Deep Cyan").

    Architecture :
      - QMainWindow 720×860, frameless (WA_TranslucentBackground)
      - Fond #0A0E17 avec grille de points subtile DM-1
      - PresenceOrb (120px) centré en haut — point focal visuel
      - ConversationSurface (bulles) — zone centrale
      - NuruInputBar (saisie + micro) — bas
    """

    theme_change_requested = Signal(str)  # 'dark' | 'light'

    def __init__(self):
        super().__init__()
        self._current_mode = "chat"  # chat | voice | action
        self._current_theme = "dark"

        self._setup_window()
        self._build_ui()

    # ── Fenêtre ──

    def _setup_window(self):
        """DM-1 : resize(720, 860), WA_TranslucentBackground."""
        self.setWindowTitle("NURU")
        self.resize(WindowSizes.WINDOW_WIDTH, WindowSizes.WINDOW_HEIGHT)
        self.setMinimumSize(WindowSizes.WINDOW_MIN_WIDTH, WindowSizes.WINDOW_MIN_HEIGHT)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowIcon(QIcon("src/ui/assets/Gemini_Generated_Image_35cdt735cdt735cd_transparent.png"))

    # ── UI ──

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("NuruCentral")
        self._central = central
        central.setStyleSheet(f"""
            #NuruCentral {{
                background: {Color.BG_DEEP};
                border-radius: {Radius.WIDGET}px;
            }}
        """)
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.SM)

        # ── Wordmark NURU + Menu ──
        logo_row = QWidget()
        logo_row.setStyleSheet("background: transparent;")
        logo_layout = QHBoxLayout(logo_row)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setSpacing(0)

        self._logo = QLabel()
        logo_pixmap = QPixmap("src/ui/assets/Gemini_Generated_Image_35cdt735cdt735cd_transparent.png")
        self._logo.setPixmap(logo_pixmap.scaledToWidth(160, Qt.TransformationMode.SmoothTransformation))
        self._logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo.setStyleSheet("background: transparent;")
        logo_layout.addWidget(self._logo, stretch=1)

        # Bouton menu ☰
        self._menu_btn = QPushButton("☰")
        self._menu_btn.setFixedSize(32, 32)
        self._menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Color.TEXT_SECONDARY};
                border: none;
                border-radius: 6px;
                font-size: 18px;
            }}
            QPushButton:hover {{
                background: {Color.CYAN_GLOW};
                color: {Color.CYAN};
            }}
        """)
        self._menu = QMenu(self._menu_btn)
        self._menu.setStyleSheet(f"""
            QMenu {{
                background: {Color.BG_SURFACE1};
                color: {Color.TEXT_PRIMARY};
                border: 1px solid {Color.BORDER};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 20px;
                border-radius: 4px;
                font-size: 12px;
            }}
            QMenu::item:selected {{
                background: {Color.CYAN_GLOW};
                color: {Color.CYAN};
            }}
            QMenu::separator {{
                height: 1px;
                background: {Color.BORDER};
                margin: 4px 8px;
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

        logo_layout.addWidget(self._menu_btn)
        layout.addWidget(logo_row)

        # ── PresenceOrb centré en haut — DM-1 ──
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
        layout.addWidget(self._conversation, stretch=1)

        # Separator discret DM-1
        sep = QWidget()
        sep.setFixedHeight(1)
        self._sep = sep
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
        self._conversation.add_message(f"**Vous** : {text}", is_user=True)
        QTimer.singleShot(500, lambda: self._add_response(f"Reçu : {text}"))

    def _add_response(self, text: str):
        self._conversation.add_message(f"NURU : {text}", is_user=False)
        self._orb.set_state(OrbState.IDLE)

    def _on_mic_click(self):
        self._orb.set_state(OrbState.LISTENING)
        logger.info("Micro cliqué — mode vocal")

    def _open_preferences(self):
        """Ouvre la fenêtre modale des préférences."""
        dlg = PreferencesDialog(self)
        dlg.exec()

    # ── Menu ──

    def _show_menu(self):
        """Affiche le menu déroulant sous le bouton ☰."""
        self._menu.exec(self._menu_btn.mapToGlobal(
            self._menu_btn.rect().bottomRight()
        ))

    def _toggle_theme(self):
        """Inverse le thème courant et émet le signal."""
        new_theme = "light" if self._current_theme == "dark" else "dark"
        self.theme_change_requested.emit(new_theme)

    def set_theme(self, theme: str):
        """Applique un thème (dark/light) et met à jour tous les styles inline."""
        self._current_theme = theme

        # Mettre à jour le fond du central widget
        bg = Color.LIGHT["bg"] if theme == "light" else Color.BG_DEEP
        border_color = Color.LIGHT["border"] if theme == "light" else Color.BORDER
        self._central.setStyleSheet(f"""
            #NuruCentral {{
                background: {bg};
                border-radius: {Radius.WIDGET}px;
            }}
        """)

        # Mettre à jour le séparateur
        self._sep.setStyleSheet(f"background: {border_color};")

        # Repeindre
        self.update()

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
            self.setWindowOpacity(0.3)
        else:
            self.setWindowOpacity(1.0)

    # ── Render DM-1 — coins arrondis + fond ──

    def _bg_color(self) -> QColor:
        """Couleur de fond selon le thème courant."""
        return QColor(
            Color.LIGHT["bg"] if self._current_theme == "light" else Color.BG_DEEP
        )

    def _dot_color(self) -> QColor:
        """Couleur de la grille de points selon le thème."""
        if self._current_theme == "light":
            return QColor(200, 210, 220, 20)  # grille subtile claire
        return QColor(26, 34, 52, 12)  # grille sombre

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(self._bg_color())
        painter.setPen(Qt.NoPen)
        r = Radius.WIDGET
        painter.drawRoundedRect(self.rect(), r, r)

        # Grille de points subtile DM-1
        painter.setBrush(self._dot_color())
        spacing = 20
        dot_r = 1
        w, h = self.width(), self.height()
        for x in range(spacing, w, spacing):
            for y in range(spacing, h, spacing):
                painter.drawEllipse(QPointF(x, y), dot_r, dot_r)

        painter.end()
