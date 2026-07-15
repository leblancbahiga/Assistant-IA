"""
NURU V16 — RightInspectorPanel.
Panneau latéral droit : sections repliables, données temps réel.
"""

from __future__ import annotations

import logging
from typing import Optional

import psutil
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QWidget, QLabel, QScrollArea,
    QPushButton, QFrame,
)

from src.ui.tokens import Color, Typography, Spacing, Radius
from src.ui.presence_orb import OrbState

logger = logging.getLogger(__name__)


# ── Section repliable ──────────────────────────────────────────

class CollapsibleSection(QFrame):
    """Section avec header cliquable et contenu masquable."""

    def __init__(self, title: str, icon: str = "", expanded: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("CollapsibleSection")
        self.setStyleSheet(
            f"#CollapsibleSection {{"
            f"  background-color: {Color.BG_SURFACE2};"
            f"  border-radius: {Radius.SM}px;"
            f"  border: 1px solid {Color.BORDER};"
            f"}}"
        )

        self._expanded = expanded

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)
        layout.setSpacing(2)

        # Header cliquable
        self._header = QPushButton(f"{icon} {title}")
        self._header.setObjectName("CollapsibleHeader")
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setFlat(True)
        self._header.setStyleSheet(
            f"#CollapsibleHeader {{"
            f"  color: {Color.TEXT_PRIMARY};"
            f"  font-size: {Typography.SIZE_CAPTION}pt;"
            f"  font-weight: {Typography.WEIGHT_SEMIBOLD};"
            f"  text-align: left; padding: 4px; border: none; background: transparent;"
            f"}}"
            f"#CollapsibleHeader:hover {{ color: {Color.CYAN}; }}"
        )
        self._header.clicked.connect(self._toggle)
        layout.addWidget(self._header)

        # Contenu
        self._content = QWidget()
        self._content.setObjectName("SectionContent")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(4, 0, 4, 2)
        self._content_layout.setSpacing(2)
        layout.addWidget(self._content)

        self._update_arrow()

    @property
    def content_layout(self) -> QVBoxLayout:
        return self._content_layout

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._update_arrow()

    def _update_arrow(self) -> None:
        arrow = "▼" if self._expanded else "▶"
        self._header.setText(
            self._header.text().replace("▶", "▼").replace("▼", "▶")
            if "▶" in self._header.text() or "▼" in self._header.text()
            else f"{self._header.text()}  {arrow}"
        )

    def add_row(self, key: str, label: str, value: str = "—") -> QLabel:
        """Ajoute une ligne clé: valeur."""
        row = QFrame()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4, 1, 4, 1)
        row_layout.setSpacing(8)

        lbl = QLabel(label)
        lbl.setFixedWidth(60)
        lbl.setStyleSheet(
            f"color: {Color.TEXT_MUTED}; font-size: {Typography.SIZE_SMALL}pt;"
        )
        row_layout.addWidget(lbl)

        val = QLabel(value)
        val.setObjectName(f"InspVal_{key}")
        val.setStyleSheet(
            f"color: {Color.TEXT_SECONDARY}; font-size: {Typography.SIZE_SMALL}pt;"
            f"font-family: 'SF Mono', 'Menlo', monospace;"
        )
        val.setWordWrap(True)
        row_layout.addWidget(val, stretch=1)

        self._content_layout.addWidget(row)
        return val

    def set_value(self, key: str, value: str) -> None:
        """Met à jour la valeur d'une ligne."""
        val = self.findChild(QLabel, f"InspVal_{key}")
        if val:
            val.setText(value)


# ── Panneau principal ──────────────────────────────────────────

class RightInspectorPanel(QWidget):
    """Panneau d'inspection droite — métriques NURU temps réel."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("RightInspectorPanel")
        self.setFixedWidth(280)
        self._engine = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.LG, Spacing.SM, Spacing.LG)
        layout.setSpacing(Spacing.MD)

        # Titre
        title = QLabel("INSPECTEUR")
        title.setStyleSheet(
            f"color: {Color.CYAN}; font-size: {Typography.SIZE_CAPTION}pt; "
            f"font-family: {Typography.FAMILY_DISPLAY}; font-weight: {Typography.WEIGHT_BOLD}; "
            "letter-spacing: 2px;"
        )
        layout.addWidget(title)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        self._scroll_layout = QVBoxLayout(content)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(Spacing.SM)

        # Sections
        self._sections: dict[str, CollapsibleSection] = {}
        self._section_defs = [
            ("state",    "État NURU",      "⚡", True),
            ("model",    "Modèle",         "🧠", True),
            ("cpu",      "CPU",            "💻", True),
            ("ram",      "RAM",            "🧮", True),
            ("gpu",      "GPU",            "🎮", False),
            ("rag",      "RAG",            "📚", True),
            ("memory",   "Mémoire",        "🧬", False),
            ("logs",     "Logs",           "📋", False),
        ]

        for key, label, icon, expanded in self._section_defs:
            section = CollapsibleSection(label, icon=icon, expanded=expanded)
            self._sections[key] = section
            self._scroll_layout.addWidget(section)

        self._scroll_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, stretch=1)

        # Bouton masquer
        self._hide_btn = QPushButton("◀ Masquer")
        self._hide_btn.setObjectName("GhostButton")
        self._hide_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hide_btn.setStyleSheet(
            f"color: {Color.TEXT_MUTED}; font-size: {Typography.SIZE_CAPTION}pt; "
            "border: none; padding: 4px;"
        )
        layout.addWidget(self._hide_btn)

        # Timer système
        self._sys_timer = QTimer(self)
        self._sys_timer.timeout.connect(self._refresh_system)
        self._sys_timer.setInterval(3000)

        # Initialisation des lignes
        self._init_rows()

    def _init_rows(self) -> None:
        """Crée les lignes pour chaque section."""
        rows = {
            "state": [
                ("status", "Statut"),
                ("strategy", "Pipeline"),
                ("uptime", "Uptime"),
            ],
            "model": [
                ("name", "Nom"),
                ("provider", "Provider"),
                ("temp", "Température"),
            ],
            "cpu": [
                ("pct", "Utilisation"),
                ("cores", "Cœurs"),
                ("freq", "Fréquence"),
            ],
            "ram": [
                ("used", "Utilisée"),
                ("total", "Totale"),
                ("pct", "Occupation"),
            ],
            "gpu": [
                ("gpu_model", "Modèle"),
                ("gpu_used", "Utilisation"),
            ],
            "rag": [
                ("documents", "Documents"),
                ("chunks", "Chunks"),
                ("last_search", "Dernière recherche"),
            ],
            "memory": [
                ("episodic", "Épisodique"),
                ("semantic", "Sémantique"),
                ("errors", "Erreurs"),
            ],
            "logs": [
                ("last_msg", "Dernier message"),
                ("tokens", "Tokens"),
                ("duration", "Durée"),
            ],
        }

        for section_key, section_rows in rows.items():
            section = self._sections.get(section_key)
            if section:
                for row_key, label in section_rows:
                    section.add_row(row_key, label)

        # Première mise à jour
        self._refresh_system()

    # ── API publique ──

    def set_engine(self, engine) -> None:
        """Connecte aux signaux du moteur."""
        self._engine = engine
        if engine is None:
            return
        try:
            engine.state_changed.connect(self._on_state_changed)
            engine.strategy_changed.connect(self._on_strategy)
            engine.token_received.connect(self._on_token)
            engine.response_complete.connect(self._on_response)
            engine.error_occurred.connect(self._on_error)
            self._sys_timer.start()
        except Exception as e:
            logger.warning(f"RightInspector: connexion engine: {e}")

    def set_hide_callback(self, callback) -> None:
        self._hide_btn.clicked.connect(callback)

    # ── Mise à jour temps réel ──

    def _on_state_changed(self, state: OrbState) -> None:
        colors = {
            OrbState.IDLE: Color.GREEN,
            OrbState.THINKING: Color.AMBER,
            OrbState.SPEAKING: Color.CYAN,
            OrbState.ERROR: Color.ROSE,
            OrbState.LISTENING: Color.CYAN,
        }
        c = colors.get(state, Color.TEXT_MUTED)
        label = state.name.capitalize() if hasattr(state, 'name') else str(state)
        self.update_value("state", "status", label)
        # Coloration du statut
        val = self.findChild(QLabel, "InspVal_status")
        if val:
            val.setStyleSheet(
                f"color: {c}; font-size: {Typography.SIZE_SMALL}pt; "
                f"font-family: 'SF Mono', 'Menlo', monospace; font-weight: bold;"
            )

    def _on_strategy(self, strategy: str) -> None:
        self.update_value("state", "strategy", strategy)

    def _on_token(self, token: str) -> None:
        self.update_value("logs", "last_msg", token[:40] + ("…" if len(token) > 40 else ""))

    def _on_response(self, text: str) -> None:
        duration = getattr(self, "_last_duration", "—")
        self.update_value("logs", "duration", f"{duration}s")

    def _on_error(self, code: str, message: str) -> None:
        self.update_value("state", "status", f"❌ {message[:30]}")

    def _on_model_changed(self, name: str, provider: str) -> None:
        self.update_value("model", "name", name)
        self.update_value("model", "provider", provider)

    def _refresh_system(self) -> None:
        """Timer CPU/RAM toutes les 3s, plus infos backend si disponible."""
        try:
            cpu = psutil.cpu_percent(interval=0)
            cores = psutil.cpu_count()
            freq = psutil.cpu_freq()
            mem = psutil.virtual_memory()

            self.update_value("cpu", "pct", f"{cpu:.1f}%")
            self.update_value("cpu", "cores", str(cores))
            self.update_value("cpu", "freq", f"{freq.current:.0f} MHz" if freq else "—")

            used_gb = mem.used / 1e9
            total_gb = mem.total / 1e9
            self.update_value("ram", "used", f"{used_gb:.1f} GiB")
            self.update_value("ram", "total", f"{total_gb:.0f} GiB")
            self.update_value("ram", "pct", f"{mem.percent:.1f}%")

            # Coloration RAM
            ram_val = self.findChild(QLabel, "InspVal_pct")
            if ram_val:
                if mem.percent > 85:
                    ram_val.setStyleSheet(
                        f"color: {Color.ROSE}; font-size: {Typography.SIZE_SMALL}pt; "
                        f"font-family: 'SF Mono', 'Menlo', monospace; font-weight: bold;"
                    )
                elif mem.percent > 70:
                    ram_val.setStyleSheet(
                        f"color: {Color.AMBER}; font-size: {Typography.SIZE_SMALL}pt; "
                        f"font-family: 'SF Mono', 'Menlo', monospace;"
                    )

            # ── Modèle ──
            if self._engine:
                self.update_value("model", "name", self._engine.current_model_name)
                self.update_value("model", "provider", self._engine.current_provider)
                self.update_value("model", "temp",
                    f"{getattr(self._engine, '_temperature', 0.7):.1f}")

                # ── RAG ──
                rag = self._engine.rag_engine
                if rag:
                    try:
                        docs = getattr(rag, '_indexed_count', None)
                        if docs is None and hasattr(rag, 'get_all_doc_meta'):
                            docs = len(rag.get_all_doc_meta())
                        chunks = getattr(rag, '_chunks_count', None)
                        self.update_value("rag", "documents", str(docs or "—"))
                        self.update_value("rag", "chunks", str(chunks or "—"))
                    except Exception:
                        pass

                # ── Mémoire ──
                mem_store = self._engine.memory_store
                if mem_store:
                    try:
                        if hasattr(mem_store, 'get_total_facts_count'):
                            facts = mem_store.get_total_facts_count()
                            sessions = mem_store.get_total_history_count()
                            self.update_value("memory", "episodic", f"{sessions} sessions")
                            self.update_value("memory", "semantic", f"{facts} faits")
                    except Exception:
                        pass

        except Exception:
            pass

    def update_value(self, section: str, key: str, value: str) -> None:
        """Met à jour une valeur dans une section."""
        sec = self._sections.get(section)
        if sec:
            sec.set_value(key, value)
