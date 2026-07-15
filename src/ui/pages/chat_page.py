"""
NURU V16 — ChatPage.
Page de chat principale — wrapper autour de ConversationSurface existant.
Phase 1 : brancher l'existant dans la nouvelle coque.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout

from src.ui.tokens import Spacing


class ChatPage(QWidget):
    """Page de chat — coeur de l'application.

    Phase 1 : intègre ConversationSurface existant tel quel.
    Phase 2 : remplacera le pattern insertWidget par QAbstractListModel.
    """

    def __init__(
        self,
        conversation_surface=None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("ChatPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if conversation_surface is not None:
            layout.addWidget(conversation_surface, stretch=1)
        else:
            # Placeholder pendant Phase 1 si pas encore branché
            placeholder = QWidget()
            placeholder.setStyleSheet("background-color: transparent;")
            layout.addWidget(placeholder, stretch=1)
