"""
NURU V11.2 — Toast Notification System (P1-B).

Système de notifications non-bloquantes 4 niveaux :
- Success (✅) — opération réussie
- Info    (ℹ️) — information neutre
- Warning (⚠️) — avertissement
- Error   (❌) — erreur

Chaque toast s'auto-détruit après 4s. L'utilisateur peut cliquer pour fermer.
Le ToastManager est un overlay positionné en bas à droite du dashboard.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QPoint, QTimer, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

TOAST_ICONS = {
    "success": "✅",
    "info": "ℹ️",
    "warning": "⚠️",
    "error": "❌",
}

TOAST_COLORS = {
    "success": "#1B6B3A",
    "info": "#2A6A9A",
    "warning": "#8A6A1A",
    "error": "#9A2A2A",
}


class ToastNotification(QFrame):
    """Toast individuel : icône + message + bouton fermeture."""

    def __init__(self, message: str, level: str = "info", duration: int = 4000):
        super().__init__()
        self._level = level
        self._duration = duration
        self._build_ui(message, level)
        self._setup_dismiss()

    def _build_ui(self, message: str, level: str) -> None:
        icon = TOAST_ICONS.get(level, "ℹ️")
        color = TOAST_COLORS.get(level, "#2A6A9A")

        self.setObjectName(f"Toast_{level}")
        self.setFixedHeight(42)
        self.setMinimumWidth(280)
        self.setMaximumWidth(420)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 8, 8)
        layout.setSpacing(8)

        # Icône
        icon_label = QLabel(icon)
        icon_label.setFixedWidth(20)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setObjectName("ToastIcon")
        layout.addWidget(icon_label)

        # Message
        msg_label = QLabel(message)
        msg_label.setObjectName("ToastMessage")
        msg_label.setWordWrap(True)
        msg_label.setAlignment(Qt.AlignVCenter)
        layout.addWidget(msg_label, stretch=1)

        # Bouton fermeture
        close_btn = QPushButton("✕")
        close_btn.setObjectName("ToastCloseBtn")
        close_btn.setFixedSize(18, 18)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self._dismiss)
        layout.addWidget(close_btn)

        self.setStyleSheet(f"""
            #Toast_{level} {{
                background-color: rgba(20, 20, 30, 0.92);
                border: 1px solid {color};
                border-radius: 8px;
            }}
            #ToastIcon {{
                font-size: 14px;
            }}
            #ToastMessage {{
                color: #D0D0DC;
                font-size: 12px;
            }}
            #ToastCloseBtn {{
                background-color: transparent;
                border: none;
                color: #5A5A6E;
                font-size: 11px;
            }}
            #ToastCloseBtn:hover {{
                color: #D0D0DC;
            }}
        """)

    def _setup_dismiss(self) -> None:
        """Auto-dismiss après duration ms."""
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._dismiss)
        self._dismiss_timer.start(self._duration)

        # Animation d'entrée
        self._fade_in = QPropertyAnimation(self, b"windowOpacity")
        self._fade_in.setDuration(200)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_in.start()

    def _dismiss(self) -> None:
        """Animation de sortie puis suppression."""
        self._dismiss_timer.stop()
        fade_out = QPropertyAnimation(self, b"windowOpacity")
        fade_out.setDuration(200)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.InCubic)
        fade_out.finished.connect(self.deleteLater)
        fade_out.start()


class ToastManager(QWidget):
    """Overlay de toasts positionné en bas à droite du dashboard.

    Empile les toasts du bas vers le haut.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ToastManager")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 16, 16)
        self._layout.setSpacing(8)
        self._layout.setAlignment(Qt.AlignBottom | Qt.AlignRight)
        self._layout.addStretch()

        self.setStyleSheet("""
            #ToastManager {
                background-color: transparent;
            }
        """)

    def show_toast(self, message: str, level: str = "info", duration: int = 4000) -> None:
        """Ajoute un toast dans la pile.

        Args:
            message: Texte du toast
            level: success / info / warning / error
            duration: ms avant auto-dismiss (défaut 4000)
        """
        toast = ToastNotification(message, level, duration)
        # Insérer avant le stretch (avant-dernière position)
        self._layout.insertWidget(self._layout.count() - 1, toast)

        # Nettoyer les toasts supprimés
        toast.destroyed.connect(lambda: None)

        logger.debug("Toast %s: %s", level, message)

    def success(self, message: str, duration: int = 4000) -> None:
        self.show_toast(message, "success", duration)

    def info(self, message: str, duration: int = 4000) -> None:
        self.show_toast(message, "info", duration)

    def warning(self, message: str, duration: int = 5000) -> None:
        self.show_toast(message, "warning", duration)

    def error(self, message: str, duration: int = 6000) -> None:
        self.show_toast(message, "error", duration)
