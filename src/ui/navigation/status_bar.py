"""
NURU V16 — StatusBar temps réel.
État engine, CPU/RAM, modèle actif, notifications.
"""

from __future__ import annotations

import logging
from typing import Optional

import psutil
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QStatusBar, QLabel, QPushButton, QHBoxLayout, QWidget

from src.ui.tokens import Color, Typography, Spacing
from src.ui.panels.notification_manager import (
    NotificationManager, NotificationPopup, Severity,
)
from src.ui.presence_orb import OrbState

logger = logging.getLogger(__name__)

# ── Couleurs d'état ──

_STATE_COLORS = {
    OrbState.IDLE: "#00FFAA",
    OrbState.THINKING: "#FFB800",
    OrbState.SPEAKING: "#00F0FF",
    OrbState.ERROR: "#FF3366",
    OrbState.LISTENING: "#00F0FF",
}
_STATE_LABELS = {
    OrbState.IDLE: "🟢 disponible",
    OrbState.THINKING: "🟡 réfléchit",
    OrbState.SPEAKING: "🔵 parle",
    OrbState.ERROR: "🔴 erreur",
    OrbState.LISTENING: "🎤 écoute",
}


class StatusBar(QStatusBar):
    """Barre de statut temps réel — état engine, CPU/RAM, notifications."""

    notification_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusBar")
        self._engine = None
        self._notif_mgr: NotificationManager | None = None
        self._notif_popup: NotificationPopup | None = None

        # ── Indicateur d'état engine ──
        self._state_label = QLabel("● démarrage...")
        self._state_label.setObjectName("StatusBarState")
        self._state_label.setStyleSheet(
            f"color: {Color.AMBER}; font-size: {Typography.SIZE_CAPTION}pt;"
            f"font-family: 'SF Mono', 'Menlo', monospace;"
        )
        self.addWidget(self._state_label, 1)

        # ── Modèle actif ──
        self._model_label = QLabel("modèle —")
        self._model_label.setObjectName("StatusBarModel")
        self._model_label.setStyleSheet(
            f"color: {Color.TEXT_SECONDARY}; font-size: {Typography.SIZE_CAPTION}pt;"
        )
        self.addWidget(self._model_label, 2)

        # ── CPU / RAM ──
        self._sys_label = QLabel("")
        self._sys_label.setObjectName("StatusBarSys")
        self._sys_label.setStyleSheet(
            f"color: {Color.TEXT_MUTED}; font-size: {Typography.SIZE_CAPTION}pt; "
            f"font-family: 'SF Mono', 'Menlo', monospace;"
        )
        self.addPermanentWidget(self._sys_label)

        # ── Bouton notifications ──
        self._notif_btn = QPushButton("🔔")
        self._notif_btn.setObjectName("StatusBarNotifBtn")
        self._notif_btn.setFixedWidth(28)
        self._notif_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._notif_btn.setStyleSheet(
            f"color: {Color.TEXT_MUTED}; font-size: 12pt; "
            "border: none; background: transparent; padding: 0 2px;"
        )
        self._notif_btn.clicked.connect(self._toggle_notifications)
        self.addPermanentWidget(self._notif_btn)

        # ── Version ──
        self._version_label = QLabel("v16")
        self._version_label.setObjectName("StatusBarVersion")
        self._version_label.setStyleSheet(
            f"color: {Color.TEXT_MUTED}; font-size: {Typography.SIZE_CAPTION}pt;"
        )
        self.addPermanentWidget(self._version_label)

        # ── Timer CPU/RAM ──
        self._sys_timer = QTimer(self)
        self._sys_timer.timeout.connect(self._refresh_system)
        self._sys_timer.start(3000)  # toutes les 3s
        self._refresh_system()

    # ── API publique ──

    def set_engine(self, engine) -> None:
        """Connecte aux signaux du moteur de conversation."""
        self._engine = engine
        if engine is None:
            return
        try:
            engine.state_changed.connect(self._on_state_changed)
            engine.strategy_changed.connect(self._on_strategy_changed)
            # État initial
            self._on_state_changed(OrbState.IDLE)
        except Exception as e:
            logger.warning(f"StatusBar: impossible de connecter engine: {e}")

    def set_notification_manager(self, mgr: NotificationManager) -> None:
        self._notif_mgr = mgr
        if mgr:
            mgr.new_notification.connect(self._on_notification)

    def set_model(self, name: str) -> None:
        self._model_label.setText(f"🧠 {name}")

    # ── Slots internes ──

    def _on_state_changed(self, state: OrbState) -> None:
        color = _STATE_COLORS.get(state, Color.TEXT_MUTED)
        label = _STATE_LABELS.get(state, "inconnu")
        self._state_label.setStyleSheet(
            f"color: {color}; font-size: {Typography.SIZE_CAPTION}pt;"
            f"font-family: 'SF Mono', 'Menlo', monospace;"
        )
        self._state_label.setText(label)

    def _on_strategy_changed(self, strategy: str) -> None:
        """Met à jour l'indicateur de stratégie."""
        icons = {"routing": "🔀", "rag": "📚", "generation": "⚡", "completed": "✅"}
        icon = icons.get(strategy, "●")
        self._state_label.setText(f"{icon} {strategy}")

    def _refresh_system(self) -> None:
        """Met à jour CPU/RAM via psutil (QTimer 3s)."""
        try:
            cpu = psutil.cpu_percent(interval=0)
            mem = psutil.virtual_memory()
            ram_pct = mem.percent
            ram_gb = mem.used / 1e9
            ram_total = mem.total / 1e9
            self._sys_label.setText(
                f"CPU {cpu:4.0f}%  RAM {ram_gb:.1f}/{ram_total:.0f} GiB"
            )
        except Exception:
            pass

    def _on_notification(self, event) -> None:
        """Flash le bouton notif quand un événement arrive."""
        colors = {
            Severity.INFO: Color.CYAN,
            Severity.SUCCESS: Color.GREEN,
            Severity.WARNING: Color.AMBER,
            Severity.ERROR: Color.ROSE,
        }
        c = colors.get(event.severity, Color.TEXT_MUTED)
        self._notif_btn.setStyleSheet(
            f"color: {c}; font-size: 12pt; "
            "border: none; background: transparent; padding: 0 2px;"
        )
        # Restore après 2s
        QTimer.singleShot(
            2000,
            lambda: self._notif_btn.setStyleSheet(
                f"color: {Color.TEXT_MUTED}; font-size: 12pt; "
                "border: none; background: transparent; padding: 0 2px;"
            ),
        )

    def _toggle_notifications(self) -> None:
        """Ouvre/ferme le popup de notifications."""
        if self._notif_mgr and not self._notif_popup:
            self._notif_popup = self._notif_mgr.build_popup(self)
            self._notif_popup.show()
        elif self._notif_popup:
            self._notif_popup.close()
            self._notif_popup = None
