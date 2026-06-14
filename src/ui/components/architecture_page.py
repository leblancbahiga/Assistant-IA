"""
NURU V10 — ArchitecturePage : schéma des composants NURU et état des modules.

Remplace l'ancien placeholder "Nuru Brain" par un aperçu concret.
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)


class ModuleCard(QFrame):
    """Carte représentant un module NURU avec son statut."""

    def __init__(self, name: str, description: str, status: str = "✓",
                 status_color: str = "#34d399", parent=None):
        super().__init__(parent)
        self.setObjectName("ModuleCard")
        self.setStyleSheet(f"""
            ModuleCard {{
                background: rgba(20, 30, 50, 0.7);
                border: 1px solid {status_color}40;
                border-radius: 8px;
                padding: 14px;
            }}
            ModuleCard:hover {{
                border-color: {status_color}80;
                background: rgba(25, 38, 60, 0.8);
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setSpacing(14)
        # Statut
        badge = QLabel(status)
        badge.setStyleSheet(
            f"font-size:22px;color:{status_color};font-weight:700")
        badge.setFixedWidth(30)
        layout.addWidget(badge, alignment=Qt.AlignTop)
        # Infos
        info = QVBoxLayout()
        info.setSpacing(4)
        title = QLabel(f"<span style='font-size:15px;font-weight:600;color:#e2e8f0'>{name}</span>")
        info.addWidget(title)
        desc = QLabel(
            f"<span style='font-size:12px;color:#8899b0'>{description}</span>")
        desc.setWordWrap(True)
        info.addWidget(desc)
        layout.addLayout(info, stretch=1)


class ArchitecturePage(QWidget):
    """Page architecture NURU."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Titre
        title = QLabel("🏗️ Architecture NURU V10")
        title.setStyleSheet("font-size:22px;font-weight:700;color:#e2e8f0")
        layout.addWidget(title)

        subtitle = QLabel(
            "Composants découplés — orchestrateur, RAG, LLM, cache, mémoire"
        )
        subtitle.setStyleSheet("font-size:13px;color:#64748b;margin-bottom:8px")
        layout.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background:transparent;border:none")
        container = QWidget()
        grid = QVBoxLayout(container)
        grid.setSpacing(10)

        modules = [
            ("🎛️ Orchestrateur", "NuruOrchestrator — pipeline complet : RAG → LLM → "
             "FactCheck → Réflexion → Mémoire. Découplé V10.3.", "✓"),
            ("📚 Pipeline RAG", "RAGOrchestrator — retrieval, décomposition, "
             "Spotlight, scoring, vérification citations.", "✓"),
            ("🧠 Générateur LLM", "LLMGenerator — cloud/local fallback, "
             "température adaptative, stratégie Archon.", "✓"),
            ("💾 Cache LLM", "Multi-niveau : L1 RAM (256 entrées, TTL 5 min) "
             "+ L2 SQLite persistante. Promotion des hits.", "✓"),
            ("🔎 Recherche macOS", "Spotlight V2 — plein texte kMDItemTextContent, "
             "scoring par terme, 5 sous-termes max.", "✓"),
            ("📊 Collecteur de traces", "TraceCollector — enregistrement asynchrone "
             "de chaque query, mode, confiance, latence.", "✓"),
            ("💬 Feedback", "FeedbackCollector — thumbs up/down, corrections, "
             "notes 1–5, stockage SQLite.", "✓"),
            ("🛡️ Guardrails", "PromptGuard — RAG_KEYWORDS, FallbackGuard, "
             "ResponseGuard, vérification evidence.", "⚠️"),
            ("🧠 Mémoire", "MemoryManager V9 — 6 types de mémoire persistante. "
             "Requêtes récentes + contexte.", "✓"),
        ]

        for name, desc, status in modules:
            color = "#34d399" if status == "✓" else "#fbbf24"
            grid.addWidget(ModuleCard(name, desc, status, color))

        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)
