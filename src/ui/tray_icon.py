"""
NURU V12 — Tray Icon (DM-1 "Deep Cyan").

Design System DM-1 :
  - Tray icon : diamant cyan lumineux 22×22px
  - Couleurs par état : idle cyan (#00D4FF), listening vert (#00E599),
    thinking ambre (#FFB800), error rose (#FF4D6A)
  - Menu : fond #151B26, bordure rgba(0,212,255,0.2)
"""

import logging

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from src.ui.presence_orb import OrbState

logger = logging.getLogger(__name__)


class NURUTrayIcon(QSystemTrayIcon):
    """Tray icon DM-1 : logo NURU (Gemini), menu déroulant.

    Brand Assets :
      - Icône : Gemini_Generated_Image (fond transparent)
      - Menu : fond #151B26, bordure rgba(0,212,255,0.2)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_state = OrbState.IDLE
        self._base_icon = QIcon("src/ui/assets/Gemini_Generated_Image_35cdt735cdt735cd_transparent.png")
        self.setIcon(self._base_icon)
        self._setup_menu()

    def _setup_icon(self):
        """Icône statique : logo NURU v5 dark."""
        self.setIcon(self._base_icon)

    def _setup_menu(self):
        self._menu = QMenu()
        self._menu.setStyleSheet("""
            QMenu {
                background-color: #151B26;
                color: #E8ECF1;
                border: 1px solid rgba(0, 212, 255, 0.2);
                border-radius: 8px;
                padding: 8px 4px;
                font-family: 'Inter', -apple-system, sans-serif;
                font-size: 13px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: rgba(0, 212, 255, 0.12);
                color: #00D4FF;
            }
            QMenu::separator {
                height: 1px;
                background: rgba(0, 212, 255, 0.1);
                margin: 4px 12px;
            }
        """)
        self.setContextMenu(self._menu)

        # ── Actions ──
        self.show_action = self._menu.addAction("  Ouvrir NURU")
        self.voice_action = self._menu.addAction("  Mode vocal ⌥␣")
        self._menu.addSeparator()
        self.widget_action = self._menu.addAction("  Afficher Widget")
        self.widget_action.setCheckable(True)
        self.widget_action.setChecked(True)
        self._menu.addSeparator()
        self.pref_action = self._menu.addAction("  Préférences…")
        self.quit_action = self._menu.addAction("  Quitter")

        self.setContextMenu(self._menu)

    def set_state(self, state: OrbState):
        """Met à jour l'icône selon l'état de l'orb (DM-1)."""
        self._current_state = state
        # On garde l'icône statique v5 dark — la couleur d'état est
        # communiquée via la lueur du menu et le floating widget.
        # (Le diamant peint était trop petit pour être lisible en 22×22px.)
        self.setIcon(self._base_icon)

    @property
    def tray(self):
        return self

    @property
    def menu(self) -> QMenu:
        return self._menu
