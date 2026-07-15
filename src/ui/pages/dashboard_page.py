"""
NURU V16 — Dashboard Page.
Fusion KPI + Stats + Performance en mode Essentiel / Avancé.
Phase 2a : mode essentiel uniquement.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame,
)

from src.ui.tokens import Color, Spacing, Typography, Radius

logger = logging.getLogger(__name__)

_PAL = Color.DARK


class MiniStatCard(QFrame):
    """Carte métrique style Arc — utilisée dans le dashboard."""

    def __init__(self, label: str, value: str = "—", parent=None):
        super().__init__(parent)
        self.setObjectName("MiniStatCard")
        self.setFixedSize(180, 90)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        layout.setSpacing(4)

        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"color: {Color.TEXT_SECONDARY}; font-size: 9pt; "
            f"font-family: {Typography.FAMILY_BODY}; font-weight: {Typography.WEIGHT_SEMIBOLD}; "
            "text-transform: uppercase; letter-spacing: 1px;"
        )
        layout.addWidget(lbl)

        self._value = QLabel(value)
        self._value.setStyleSheet(
            f"color: {_PAL['text']}; font-size: 15pt; "
            f"font-family: {Typography.FAMILY_DISPLAY}; font-weight: {Typography.WEIGHT_BOLD};"
        )
        layout.addWidget(self._value)
        layout.addStretch()

    def set_value(self, text: str):
        self._value.setText(text)


class DashboardPage(QWidget):
    """Dashboard V16 — mode essentiel par défaut, détail avancé à la demande."""

    _DEFAULT_FIELDS = [
        ("state", "État général"),
        ("model", "Modèle actif"),
        ("docs", "Documents indexés"),
        ("memory", "Mémoire"),
        ("latency", "Temps réponse moy."),
        ("cpu", "CPU"),
        ("ram", "RAM"),
        ("version", "Version"),
    ]

    def __init__(self, engine=None, parent=None):
        super().__init__(parent)
        self.setObjectName("DashboardPageV16")
        self._engine = engine
        self._advanced = False

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        root.setSpacing(Spacing.MD)

        # Header
        header = QHBoxLayout()
        title = QLabel("📊  Dashboard")
        title.setStyleSheet(
            f"color: {_PAL['text']}; font-size: {Typography.SIZE_HEADING_1}pt; "
            f"font-family: {Typography.FAMILY_DISPLAY}; font-weight: {Typography.WEIGHT_BOLD};"
        )
        header.addWidget(title)
        header.addStretch()

        self.toggle_btn = QPushButton("Voir mode avancé →")
        self.toggle_btn.setObjectName("GhostButton")
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._toggle_advanced)
        header.addWidget(self.toggle_btn)

        root.addLayout(header)

        # Grille de cartes
        self.grid = QGridLayout()
        self.grid.setSpacing(Spacing.MD)
        root.addLayout(self.grid)

        self._cards: dict[str, MiniStatCard] = {}
        self._build_essential_cards()
        self._refresh()

        # Refresh timer (si engine disponible)
        if self._engine is not None:
            self._timer = QTimer(self)
            self._timer.setInterval(5000)
            self._timer.timeout.connect(self._refresh)
            self._timer.start()

        root.addStretch()

    def _build_essential_cards(self):
        for i, (key, label) in enumerate(self._DEFAULT_FIELDS):
            card = MiniStatCard(label)
            self._cards[key] = card
            self.grid.addWidget(card, i // 4, i % 4)

    def _refresh(self):
        """Rafraîchit les cartes avec les données réelles du backend."""
        import psutil
        data = {}
        try:
            # Contexte système
            cpu = psutil.cpu_percent(interval=0)
            mem = psutil.virtual_memory()
            data["cpu"] = f"{cpu:.0f}%"
            data["ram"] = f"{mem.percent:.0f}% ({mem.used/1e9:.1f}/{mem.total/1e9:.0f} GiB)"

            # Contexte backend
            if self._engine:
                data["model"] = self._engine.current_model_name
                rag = self._engine.rag_engine
                if rag:
                    try:
                        docs = len(rag.get_all_doc_meta()) if hasattr(rag, 'get_all_doc_meta') else 0
                        data["docs"] = f"{docs} docs"
                    except Exception:
                        data["docs"] = "—"
                mem_store = self._engine.memory_store
                if mem_store:
                    try:
                        facts = mem_store.get_total_facts_count()
                        data["memory"] = f"{facts} faits"
                    except Exception:
                        data["memory"] = "—"
                data["state"] = "Prêt ✓" if self._engine.is_ready else "Initialisation…"
        except Exception:
            pass

        for key, card in self._cards.items():
            card.set_value(str(data.get(key, "—")))

    def _toggle_advanced(self):
        self._advanced = not self._advanced
        text = "← Mode essentiel" if self._advanced else "Voir mode avancé →"
        self.toggle_btn.setText(text)
        if self._advanced:
            self._load_advanced_mode()

    def _load_advanced_mode(self):
        """Lazy-load des pages de performance/diagnostics existantes."""
        try:
            from src.ui.components.kpi_dashboard_page import KpiDashboardPage as LegacyKpi
            self._advanced_widget = LegacyKpi()
            parent_layout = self.grid.parent().layout()
            if parent_layout:
                parent_layout.addWidget(self._advanced_widget)
        except Exception as e:
            logger.debug(f"Mode avancé non disponible: {e}")
