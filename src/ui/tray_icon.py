"""
NURU V12 — Tray Icon (DM-1 "Deep Cyan").

Directive design V12 (design/tray_icon.py) :
  - QSystemTrayIcon exposé via l'attribut .tray
  - Diamant cyan lumineux dessiné programmatiquement (64×64 Retina)
  - Couleurs par OrbState (idle/listening/thinking/speaking/acting/error/sleep)
  - Menu contextuel DM-1
  - Sync automatique avec self._current_state
  - La couleur d'état est portée par le diamant dessiné ET par une lueur
    dans le menu.

API consommée par AmbientApp :
  - tray.show_action / voice_action / widget_action / pref_action / quit_action
  - tray.widget_action (checkable, état initial checked=True)
  - tray.tray.activated.connect(...)
  - tray.set_state(OrbState.X)
  - tray.show()
"""

import logging

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QPen, QPolygonF,
    QBrush, QRadialGradient, QLinearGradient,
)
from PySide6.QtWidgets import QSystemTrayIcon, QMenu

from src.ui.presence_orb import OrbState

logger = logging.getLogger(__name__)


# ── Couleurs DM-1 par état de l'orb ──────────────────────────────────────────
_STATE_COLORS = {
    OrbState.IDLE:      QColor(0, 212, 255),    # #00D4FF — Cyan
    OrbState.LISTENING: QColor(0, 229, 153),    # #00E599 — Green
    OrbState.THINKING:  QColor(255, 184, 0),    # #FFB800 — Amber
    OrbState.SPEAKING:  QColor(0, 212, 255),    # #00D4FF — Cyan
    OrbState.ACTING:    QColor(0, 212, 255),    # #00D4FF — Cyan
    OrbState.ERROR:     QColor(255, 77, 106),   # #FF4D6A — Rose
    OrbState.SLEEP:     QColor(75, 85, 120),    # Bleu-gris dim
}


class NURUTrayIcon:
    """
    Diamant cyan lumineux pour la barre macOS + menu contextuel DM-1.

    Usage :
        tray = NURUTrayIcon(app)
        tray.set_state(OrbState.IDLE)
        tray.show()

    Attributs publics :
        tray   : QSystemTrayIcon (sous-jacent)
        menu   : QMenu (alias de .tray.contextMenu())
        show_action / voice_action / widget_action /
        pref_action / quit_action : QAction exposés pour signaux
    """

    def __init__(self, app):
        self.app = app
        self.tray = QSystemTrayIcon(app)
        self._state = OrbState.IDLE
        self._update_icon()

        # ── Menu contextuel DM-1 ─────────────────────────────────────
        self.menu = QMenu()
        self.menu.setStyleSheet("""
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

        # Actions exposées à AmbientApp
        self.show_action = self.menu.addAction("  Afficher NURU")
        self.menu.addSeparator()
        self.voice_action = self.menu.addAction("  Mode vocal \u2325\u2423")
        self.menu.addSeparator()
        self.widget_action = self.menu.addAction("  Afficher Widget")
        self.widget_action.setCheckable(True)
        self.widget_action.setChecked(True)
        self.menu.addSeparator()
        self.pref_action = self.menu.addAction("  Préférences\u2026")
        self.menu.addSeparator()
        self.quit_action = self.menu.addAction("  Quitter")

        self.tray.setContextMenu(self.menu)
        self.tray.setToolTip("NURU V12 \u2014 Assistant IA")

    # ── API état ────────────────────────────────────────────────────

    def set_state(self, state: OrbState):
        """Met à jour la couleur du diamant selon l'état de l'orb."""
        self._state = state
        self._update_icon()

    def show(self):
        self.tray.show()

    def hide(self):
        self.tray.hide()

    # ── Rendu du diamant cyan ───────────────────────────────────────

    def _update_icon(self):
        """Génère l'icône diamant cyan selon OrbState (64×64 Retina)."""
        size = 64  # High-res pour Retina
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(0, 0, 0, 0))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)

        cx, cy = size / 2, size / 2
        diamond_size = size * 0.32

        color = _STATE_COLORS.get(self._state, QColor(0, 212, 255))

        # Glow derrière le diamant
        glow = QRadialGradient(cx, cy, diamond_size * 1.8)
        glow.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 60))
        glow.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QPointF(cx, cy), diamond_size * 1.8, diamond_size * 1.8)

        # Forme diamant (carré rotatif)
        diamond = QPolygonF([
            QPointF(cx, cy - diamond_size),
            QPointF(cx + diamond_size * 0.7, cy),
            QPointF(cx, cy + diamond_size),
            QPointF(cx - diamond_size * 0.7, cy),
        ])

        # Remplissage gradient
        grad = QLinearGradient(cx, cy - diamond_size, cx, cy + diamond_size)
        grad.setColorAt(0.0, color.lighter(130))
        grad.setColorAt(1.0, color.darker(120))
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(color.lighter(150), 1))
        painter.drawPolygon(diamond)

        # Highlight intérieur
        inner = QPolygonF([
            QPointF(cx, cy - diamond_size * 0.5),
            QPointF(cx + diamond_size * 0.3, cy),
            QPointF(cx, cy + diamond_size * 0.5),
            QPointF(cx - diamond_size * 0.3, cy),
        ])
        painter.setBrush(QColor(255, 255, 255, 40))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(inner)

        painter.end()
        self.tray.setIcon(QIcon(pixmap))
