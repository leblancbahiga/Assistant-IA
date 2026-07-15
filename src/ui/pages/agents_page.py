"""NURU V16 — Agents Page.
Vue interactive des agents proactifs, routines, et historique.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from PySide6.QtCore import Qt, QTimer  # noqa: F401 — QTimer used in _refresh
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QScrollArea, QTextEdit,
    QSplitter, QCheckBox,
)

from src.ui.tokens import Color, Spacing, Typography, Radius

logger = logging.getLogger(__name__)

_PAL = Color.DARK


class RoutineCard(QFrame):
    """Carte routine interactive."""

    def __init__(self, name: str, interval: str = "", active: bool = True,
                 engine_ref: Any = None, parent=None):
        super().__init__(parent)
        self._name = name
        self._engine = engine_ref
        self.setObjectName("RoutineCard")
        self.setFixedHeight(64)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)

        status = "●" if active else "○"
        color = Color.CYAN if active else Color.TEXT_MUTED
        icon = QLabel(status)
        icon.setStyleSheet(f"color: {color}; font-size: 14pt;")
        layout.addWidget(icon)

        info = QVBoxLayout()
        info.setSpacing(2)
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"color: {_PAL['text']}; font-size: 11pt; "
            f"font-family: {Typography.FAMILY_DISPLAY}; font-weight: {Typography.WEIGHT_SEMIBOLD};"
        )
        info.addWidget(name_lbl)

        if interval:
            int_lbl = QLabel(f"⏱ {interval}")
            int_lbl.setStyleSheet(f"color: {Color.TEXT_MUTED}; font-size: 8pt;")
            info.addWidget(int_lbl)

        layout.addLayout(info, stretch=1)

        # Bouton Exécuter
        run_btn = QPushButton("▶ Exécuter")
        run_btn.setStyleSheet(
            f"background: rgba(0,240,255,0.15); color: {Color.CYAN}; "
            f"border: 1px solid {Color.CYAN}; border-radius: {Radius.SMALL}; "
            f"padding: 4px 12px; font-size: 9pt;"
        )
        run_btn.clicked.connect(self._run_now)
        layout.addWidget(run_btn)

        status_lbl = QLabel("Actif" if active else "Inactif")
        status_lbl.setStyleSheet(
            f"color: {Color.CYAN if active else Color.TEXT_MUTED}; font-size: 9pt; "
            f"font-weight: {Typography.WEIGHT_SEMIBOLD};"
        )
        layout.addWidget(status_lbl)

    def _run_now(self) -> None:
        """Exécute cette routine immédiatement."""
        if not self._engine:
            return
        try:
            # Cherche la routine dans le scheduler
            routines = self._engine.routine_scheduler
            if routines and hasattr(routines, 'run'):
                routines.run(self._name)
                logger.info(f"Routine '{self._name}' déclenchée")
        except Exception as e:
            logger.warning(f"Impossible d'exécuter '{self._name}': {e}")


class ActionLog(QFrame):
    """Entrée d'historique d'action."""

    def __init__(self, text: str, time_str: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, 2, Spacing.SM, 2)

        if time_str:
            t = QLabel(time_str)
            t.setStyleSheet(f"color: {Color.TEXT_MUTED}; font-size: 8pt; min-width: 60px;")
            layout.addWidget(t)

        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {Color.TEXT_MUTED}; font-size: 9pt;")
        layout.addWidget(lbl, stretch=1)


class AgentsPage(QWidget):
    """Page Agents V16 — routines proactives interactives."""

    def __init__(self, engine=None, parent=None):
        super().__init__(parent)
        self.setObjectName("AgentsPageV16")
        self._engine = engine

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.MD)

        # ── Header ──
        header = QHBoxLayout()
        title = QLabel("🤖  Agents")
        title.setStyleSheet(
            f"color: {_PAL['text']}; font-size: {Typography.SIZE_HEADING_1}pt; "
            f"font-family: {Typography.FAMILY_DISPLAY}; font-weight: {Typography.WEIGHT_BOLD};"
        )
        header.addWidget(title)

        self._status = QLabel("• Agent inactif")
        self._status.setStyleSheet(f"color: {Color.TEXT_MUTED}; font-size: 10pt;")
        header.addStretch()
        header.addWidget(self._status)

        # Toggle ProactiveEngine
        self._toggle_btn = QPushButton("▶ Démarrer")
        self._toggle_btn.setStyleSheet(
            f"background: rgba(0,240,255,0.15); color: {Color.CYAN}; "
            f"border: 1px solid {Color.CYAN}; border-radius: {Radius.SMALL}; "
            f"padding: 6px 18px; font-weight: bold; font-size: 9pt;"
        )
        self._toggle_btn.clicked.connect(self._toggle_proactive)
        header.addWidget(self._toggle_btn)

        layout.addLayout(header)

        # ── Splitter: contenu principal ──
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Haut : Routines
        routines_widget = QWidget()
        routines_layout = QVBoxLayout(routines_widget)
        routines_layout.setContentsMargins(0, 0, 0, 0)
        routines_layout.setSpacing(Spacing.SM)

        routines_title = QLabel("Routines programmées")
        routines_title.setStyleSheet(
            f"color: {Color.TEXT_SECONDARY}; font-size: 10pt; "
            f"font-weight: {Typography.WEIGHT_SEMIBOLD};"
        )
        routines_layout.addWidget(routines_title)

        self._routines_list = QVBoxLayout()
        self._routines_list.setSpacing(Spacing.SM)
        routines_layout.addLayout(self._routines_list)
        routines_layout.addStretch()

        splitter.addWidget(routines_widget)

        # Bas : Journal d'actions
        journal_widget = QWidget()
        journal_layout = QVBoxLayout(journal_widget)
        journal_layout.setContentsMargins(0, 0, 0, 0)
        journal_layout.setSpacing(4)

        journal_title = QLabel("Journal des actions")
        journal_title.setStyleSheet(
            f"color: {Color.TEXT_SECONDARY}; font-size: 10pt; "
            f"font-weight: {Typography.WEIGHT_SEMIBOLD};"
        )
        journal_layout.addWidget(journal_title)

        self._journal = QTextEdit()
        self._journal.setReadOnly(True)
        self._journal.setStyleSheet(
            f"background: rgba(0,0,0,0.3); border: 1px solid {Color.BORDER}; "
            f"border-radius: {Radius.SMALL}; color: {Color.TEXT_SECONDARY}; "
            f"padding: 8px; font-size: 9pt; font-family: 'SF Mono', monospace;"
        )
        journal_layout.addWidget(self._journal, stretch=1)

        splitter.addWidget(journal_widget)
        splitter.setSizes([250, 150])
        layout.addWidget(splitter, stretch=1)

        # ── Timer ──
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

        # Premier chargement
        self._refresh()

    def _toggle_proactive(self) -> None:
        """Démarre/arrête le ProactiveEngine."""
        if not self._engine:
            return
        proactive = self._engine.proactive_engine
        if not proactive:
            return

        try:
            if hasattr(proactive, 'is_running') and proactive.is_running:
                if hasattr(proactive, 'stop'):
                    proactive.stop()
                self._toggle_btn.setText("▶ Démarrer")
                self._status.setText("● Agent arrêté")
            else:
                if hasattr(proactive, 'start'):
                    proactive.start()
                self._toggle_btn.setText("⏹ Arrêter")
                self._status.setText("● Agent actif")
        except Exception as e:
            logger.warning(f"Toggle ProactiveEngine: {e}")

    def _refresh(self) -> None:
        """Rafraîchit l'affichage."""
        if not self._engine:
            return

        proactive = self._engine.proactive_engine
        routines = self._engine.routine_scheduler

        # ── Routines ──
        self._clear_layout(self._routines_list)
        has_routines = False

        if routines:
            try:
                if hasattr(routines, 'get_active'):
                    active = routines.get_active()
                    for r in active:
                        name = getattr(r, 'name', str(r))
                        interval = getattr(r, 'interval', '')
                        card = RoutineCard(name, interval=str(interval),
                                           active=True, engine_ref=self._engine)
                        self._routines_list.addWidget(card)
                        has_routines = True

                if not has_routines and hasattr(routines, 'presets'):
                    for p in routines.presets:
                        name = getattr(p, 'name', str(p))
                        interval = getattr(p, 'interval', '')
                        card = RoutineCard(name, interval=str(interval),
                                           active=False, engine_ref=self._engine)
                        self._routines_list.addWidget(card)
                        has_routines = True
            except Exception as e:
                logger.debug(f"Routines refresh: {e}")

        if not has_routines:
            placeholder = QLabel("Aucune routine configurée")
            placeholder.setStyleSheet(f"color: {Color.TEXT_MUTED}; font-size: 10pt;")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._routines_list.addWidget(placeholder)

        # ── État ──
        running = False
        if proactive and hasattr(proactive, 'is_running'):
            running = proactive.is_running

        self._status.setText(f"{'●' if running else '○'} Agent {'actif' if running else 'inactif'}")
        if not running:
            self._toggle_btn.setText("▶ Démarrer")

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
