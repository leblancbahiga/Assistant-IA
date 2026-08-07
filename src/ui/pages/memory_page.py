"""
NURU V16 — Memory Page.
Fusion de memory_page + memory_explorer + performance_memory_page avec onglets.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTabWidget,
)

from src.ui.tokens import Color, Spacing, Typography

logger = logging.getLogger(__name__)

_PAL = Color.DARK


class MemoryPage(QWidget):
    """Page Mémoire V16 — onglets Épisodique / Sémantique / Utilisateur / Erreurs."""

    def __init__(self, engine=None, parent=None):
        super().__init__(parent)
        self.setObjectName("MemoryPageV16")

        # Extraire le service MemoryStore du backend
        # V17 P0-C : utiliser kernel.get("memory") ou engine.memory (pas engine.memory_store)
        memory_store = None
        if engine:
            try:
                from src.kernel import NuruKernel
                kernel = NuruKernel()
                if kernel.has("memory"):
                    memory_store = kernel.get("memory")
            except Exception:
                pass
        if memory_store is None and engine and hasattr(engine, 'memory'):
            memory_store = engine.memory
        elif memory_store is None and engine and hasattr(engine, 'memory_store'):
            memory_store = engine.memory_store

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.MD)

        # Header
        header = QHBoxLayout()
        title = QLabel("🧠  Mémoire")
        title.setStyleSheet(
            f"color: {_PAL['text']}; font-size: {Typography.SIZE_HEADING_1}pt; "
            f"font-family: {Typography.FAMILY_DISPLAY}; font-weight: {Typography.WEIGHT_BOLD};"
        )
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        # Onglets
        tabs = QTabWidget()
        tabs.setObjectName("MemoryTabs")
        tabs.setDocumentMode(True)
        tabs.setTabPosition(QTabWidget.TabPosition.North)

        try:
            from src.ui.components.memory_page import MemoryPage as LegacyMemPage
            from src.ui.components.memory_explorer import MemoryExplorer

            # Onglet 1 : Mémoire épisodique (page existante)
            self._episodic_tab = LegacyMemPage(memory_store=memory_store)
            tabs.addTab(self._episodic_tab, "Épisodique")

            # Onglet 2 : Exploration sémantique
            # V17 P0-C : appeler set_data() après création pour alimenter l'explorateur
            self._semantic_tab = MemoryExplorer()
            if memory_store is not None:
                try:
                    # Tentative de récupération des faits sémantiques
                    if hasattr(memory_store, 'get_semantic_memories'):
                        facts = memory_store.get_semantic_memories(limit=100)
                        self._semantic_tab.set_data({"semantic": facts})
                    elif hasattr(memory_store, 'get_user_facts'):
                        facts = memory_store.get_user_facts(limit=100)
                        self._semantic_tab.set_data({"semantic": facts})
                    elif hasattr(memory_store, 'get_facts'):
                        facts = memory_store.get_facts()
                        self._semantic_tab.set_data({"semantic": facts})
                except Exception:
                    logger.debug("Impossible de charger les faits mémoire", exc_info=True)
            tabs.addTab(self._semantic_tab, "Sémantique")
        except Exception as e:
            logger.warning(f"Impossible de charger les composants mémoire: {e}")
            placeholder = QLabel("Mémoire — module non disponible")
            placeholder.setStyleSheet(f"color: {Color.TEXT_MUTED};")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tabs.addTab(placeholder, "Épisodique")

        try:
            from src.ui.components.performance_memory_page import PerformanceMemoryPage
            # V17 P0-C : passer memory_store à l'onglet d'erreurs
            self._errors_tab = PerformanceMemoryPage(memory_store=memory_store)
            tabs.addTab(self._errors_tab, "Erreurs")
        except Exception as e:
            logger.debug(f"PerformanceMemoryPage non disponible: {e}")

        layout.addWidget(tabs, stretch=1)
