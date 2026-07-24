"""
NURU V16 — Documents Page.
Wrapper autour de documents_page.py existant, re-thémé via tokens.py.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from src.ui.tokens import Color, Spacing, Typography

logger = logging.getLogger(__name__)

_PAL = Color.DARK


class DocumentsPage(QWidget):
    """Page Documents V16 — importe le composant existant et applique le thème."""

    def __init__(self, engine=None, parent=None):
        super().__init__(parent)
        self.setObjectName("DocumentsPageV16")

        # Extraire les services du backend
        # V17 P0-C : utiliser engine.ingestion (propriété ConversationEngine)
        # au lieu de rag_engine._ingestion qui n'existe pas dans RAGEngine
        rag_engine = engine.rag_engine if engine and hasattr(engine, 'rag_engine') else None
        ingestion_engine = engine.ingestion if engine and hasattr(engine, 'ingestion') else None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.MD)

        # Titre
        title = QLabel("📄  Documents")
        title.setStyleSheet(
            f"color: {_PAL['text']}; font-size: {Typography.SIZE_HEADING_1}pt; "
            f"font-family: {Typography.FAMILY_DISPLAY}; font-weight: {Typography.WEIGHT_BOLD};"
        )
        layout.addWidget(title)

        # Page existante
        try:
            from src.ui.components.documents_page import DocumentsPage as LegacyDocsPage

            self._inner = LegacyDocsPage(
                rag_engine=rag_engine,
                ingestion_engine=ingestion_engine,
            )
            layout.addWidget(self._inner, stretch=1)
        except Exception as e:
            logger.warning(f"Impossible de charger DocumentsPage existante: {e}")
            placeholder = QLabel("Documents — module non disponible")
            placeholder.setStyleSheet(f"color: {Color.TEXT_MUTED};")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(placeholder, stretch=1)
            self._inner = None

    def set_ingestion(self, ingestion) -> None:
        if self._inner is not None and hasattr(self._inner, "set_ingestion"):
            self._inner.set_ingestion(ingestion)
