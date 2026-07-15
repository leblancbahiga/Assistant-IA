"""
NURU V16 — ChatInputBar.
Barre de saisie verre morphique : champ + 📎 + 🎤 + ➤.
Audit section 9.2 : Message NURU…  📎 🎤 ➤
"""

from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton
from src.ui.tokens import Color, Spacing, Radius, Typography


class ChatInputBar(QWidget):
    """Barre de saisie intégrable dans ChatPage."""

    send_requested = Signal(str)  # émet le texte à envoyer

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ChatInputBar")
        self.setFixedHeight(64)
        self.setStyleSheet(f"""
            #ChatInputBar {{
                background: rgba(10, 15, 30, 0.75);
                border-top: 1px solid rgba(0, 240, 255, 0.08);
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(8)

        # Champ de saisie
        self._input = QLineEdit()
        self._input.setObjectName("ChatInput")
        self._input.setPlaceholderText("Message NURU…")
        self._input.setMinimumHeight(40)
        self._input.returnPressed.connect(self._on_send)
        layout.addWidget(self._input, stretch=1)

        # Bouton pièce jointe
        self._attach = QPushButton("📎")
        self._attach.setObjectName("InputAttach")
        self._attach.setFixedSize(40, 40)
        self._attach.setToolTip("Joindre un fichier")
        self._attach.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self._attach)

        # Bouton micro
        self._mic = QPushButton("🎤")
        self._mic.setObjectName("InputMic")
        self._mic.setFixedSize(40, 40)
        self._mic.setToolTip("Mode vocal")
        self._mic.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self._mic)

        # Bouton envoi
        self._send = QPushButton("➤")
        self._send.setObjectName("InputSend")
        self._send.setFixedSize(40, 40)
        self._send.setToolTip("Envoyer (Entrée)")
        self._send.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send.clicked.connect(self._on_send)
        layout.addWidget(self._send)

    def _on_send(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self.send_requested.emit(text)
        self._input.clear()

    @property
    def text(self) -> str:
        return self._input.text()

    def clear(self) -> None:
        self._input.clear()

    def focus(self) -> None:
        self._input.setFocus()
