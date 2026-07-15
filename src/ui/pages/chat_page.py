"""
NURU V16 — ChatPage.
Page de chat = ConversationSurface + ChatInputBar + wiring engine.
Audit sections 9.2, 11 : grouping conversation_surface.py + input bar + orb.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout

from src.ui.components.chat.input_bar import ChatInputBar
from src.ui.tokens import Spacing

logger = logging.getLogger(__name__)


class ChatPage(QWidget):
    """Page de chat — coeur de l'application.

    Regroupe :
      - ConversationSurface (messages scrollables)
      - ChatInputBar (saisie + 📎 🎤 ➤)
      - Wiring directe vers ConversationEngine (adapters plus tard)
    """

    def __init__(
        self,
        conversation_surface=None,
        engine=None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("ChatPage")
        self._engine = engine
        self._surface = conversation_surface

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 0)
        layout.setSpacing(8)

        # Zone de messages
        if self._surface is not None:
            layout.addWidget(self._surface, stretch=1)
        else:
            placeholder = QWidget()
            placeholder.setObjectName("ChatPlaceholder")
            placeholder.setStyleSheet("background: transparent;")
            layout.addWidget(placeholder, stretch=1)

        # Barre de saisie
        self._input_bar = ChatInputBar(self)
        self._input_bar.send_requested.connect(self._on_send)
        layout.addWidget(self._input_bar)

        # Wiring engine si disponible
        if self._engine is not None:
            self._wire_engine()

    def _wire_engine(self) -> None:
        """Connecte les signaux de l'engine vers la surface de conversation."""
        if self._surface is None:
            return

        self._engine.token_received.connect(self._surface.append_to_stream)
        self._engine.response_complete.connect(self._on_response_complete)
        self._engine.error_occurred.connect(self._on_error)

    # ── Slots ───────────────────────────────────────────────

    def _on_send(self, text: str) -> None:
        """Envoie un message via l'engine, affiche la bulle utilisateur."""
        if self._engine is None:
            return
        if self._surface is not None:
            self._surface.add_message(text, is_user=True)
        self._engine.send_message(text)

    def _on_response_complete(self, full_text: str) -> None:
        """Finalise la réponse NURU dans la surface."""
        if self._surface is not None:
            # Fin du stream — la surface finalise
            self._surface._flush_stream_buffer()
            self._surface._streaming_bubble = None

    def _on_error(self, code: str, message: str) -> None:
        """Affiche une erreur dans la surface."""
        if self._surface is not None:
            self._surface.add_message(f"[{code}] {message}", is_user=False)

    @property
    def input_bar(self) -> ChatInputBar:
        return self._input_bar
