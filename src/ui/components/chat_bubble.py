"""
NURU V6 — ChatBubble : design sobre anthracite/bleu électrique.

- Avatar circulaire avec bordure colorée (bleu pour l'IA, vert pour l'utilisateur)
- Entête "NURU SYSTEM" / "VOUS"
- Indicateur de frappe clignotant
- Boutons de feedback pour l'assistant
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QSizePolicy, QFrame
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QTextCursor
import datetime


class TypingIndicator(QLabel):
    """Indicateur de frappe clignotant — curseur █ bleu."""

    def __init__(self, parent=None):
        super().__init__("█", parent)
        self.setStyleSheet("color: #00A3FF; font-size: 16px; font-weight: bold;")
        self._visible = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._blink)
        self._timer.start(500)

    def _blink(self):
        self._visible = not self._visible
        self.setText("█" if self._visible else " ")

    def stop(self):
        self._timer.stop()
        self.setText("")


class ChatBubble(QWidget):
    """Bulle de discussion — design sobre anthracite/bleu électrique.

    - Avatar circulaire coloré (bleu #00A3FF pour l'IA, vert #39FF14 pour l'utilisateur)
    - Bordure gauche neon (bleue assistant, verte user)
    - En-tête avec nom + horodatage
    - Indicateur de frappe clignotant pendant la génération
    - Boutons de feedback 👍/👎 sur les réponses de l'assistant
    """

    feedback_given = Signal(str, str)  # (vote: 'up'|'down', message)

    def __init__(self, sender: str, message: str, is_user: bool = False, parent=None):
        super().__init__(parent)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setAlignment(Qt.AlignTop)

        # ── Avatar ──
        self.avatar = QLabel()
        self.avatar.setFixedSize(32, 32)
        if is_user:
            self.avatar.setText("👤")
            self.avatar.setStyleSheet(
                "background-color: rgba(57, 255, 20, 0.12);"
                "border: 2px solid #39FF14;"
                "border-radius: 16px;"
                "font-size: 14px;"
                "qproperty-alignment: AlignCenter;"
            )
        else:
            self.avatar.setText("🧠")
            self.avatar.setStyleSheet(
                "background-color: rgba(0, 163, 255, 0.12);"
                "border: 2px solid #00A3FF;"
                "border-radius: 16px;"
                "font-size: 14px;"
                "qproperty-alignment: AlignCenter;"
            )

        main_layout.addWidget(self.avatar, 0, Qt.AlignTop)

        # ── Bulle ──
        accent_color = "#00A3FF" if not is_user else "#39FF14"
        bg_color = "#161B22" if not is_user else "#1A1D24"
        self.bubble = QFrame()
        self.bubble.setObjectName("BubbleFrame")
        self.bubble.setStyleSheet(f"""
            #BubbleFrame {{
                background-color: {bg_color};
                border: 1px solid {accent_color}33;
                border-left: 3px solid {accent_color};
                border-radius: 12px;
                padding: 12px;
            }}
        """)

        content_layout = QVBoxLayout(self.bubble)
        content_layout.setContentsMargins(12, 10, 12, 10)
        content_layout.setSpacing(4)

        # ── En-tête ──
        header = QHBoxLayout()

        # Badge rôle
        if not is_user:
            badge = QLabel("⚡ SYSTEM")
            badge.setStyleSheet(
                f"background-color: rgba(0, 163, 255, 0.15);"
                f"color: #00A3FF; font-size: 8px; font-weight: bold;"
                f"border-radius: 4px; padding: 1px 6px;"
            )
            header.addWidget(badge)
            header.addSpacing(8)

        name_lbl = QLabel(sender.upper())
        name_lbl.setStyleSheet(
            f"color: {accent_color}; font-size: 9px; font-weight: bold; letter-spacing: 1px;"
        )
        time_lbl = QLabel(datetime.datetime.now().strftime("%H:%M"))
        time_lbl.setStyleSheet("color: #6B7280; font-size: 9px;")

        header.addWidget(name_lbl)
        header.addStretch()
        header.addWidget(time_lbl)
        content_layout.addLayout(header)

        # ── Message ──
        self.msg_text = QTextEdit()
        self.msg_text.setReadOnly(True)
        self.msg_text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.msg_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.msg_text.setFrameShape(QFrame.NoFrame)
        self.msg_text.setStyleSheet("background: transparent; color: #E5E7EB; font-size: 13px;")
        self.msg_text.setPlainText(message)
        self.msg_text.document().setDocumentMargin(0)
        self.msg_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.msg_text.textChanged.connect(self._resize_to_content)
        content_layout.addWidget(self.msg_text)

        # ── Indicateur de frappe (caché par défaut) ──
        self.typing = TypingIndicator()
        self.typing.setVisible(False)
        content_layout.addWidget(self.typing)

        # ── Feedback (assistant uniquement) ──
        if not is_user:
            fb_layout = QHBoxLayout()
            fb_layout.setContentsMargins(0, 6, 0, 0)
            fb_layout.setSpacing(6)

            self.btn_up = QPushButton("👍")
            self.btn_up.setStyleSheet("""
                QPushButton { background: transparent; color: #6B7280; border: none; font-size: 12px; }
                QPushButton:hover { color: #39FF14; }
            """)
            self.btn_up.setFixedSize(28, 24)
            self.btn_up.setCursor(Qt.PointingHandCursor)

            self.btn_down = QPushButton("👎")
            self.btn_down.setStyleSheet("""
                QPushButton { background: transparent; color: #6B7280; border: none; font-size: 12px; }
                QPushButton:hover { color: #ef4444; }
            """)
            self.btn_down.setFixedSize(28, 24)
            self.btn_down.setCursor(Qt.PointingHandCursor)

            self.fb_status = QLabel("")
            self.fb_status.setStyleSheet("color: #6B7280; font-size: 9px;")

            fb_layout.addWidget(self.btn_up)
            fb_layout.addWidget(self.btn_down)
            fb_layout.addWidget(self.fb_status)
            fb_layout.addStretch()
            content_layout.addLayout(fb_layout)

        main_layout.addWidget(self.bubble, 1)

        # Alignement : user à droite, assistant à gauche
        if is_user:
            main_layout.insertStretch(0, 1)
        else:
            main_layout.addStretch(1)

    def append_text(self, text: str):
        """Ajoute du texte au message existant (streaming)."""
        try:
            cursor = self.msg_text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(text)
            self.msg_text.setTextCursor(cursor)
        except RuntimeError:
            pass

    def show_typing(self):
        """Affiche l'indicateur de frappe clignotant."""
        self.typing.setVisible(True)

    def hide_typing(self):
        """Cache et arrête l'indicateur de frappe."""
        self.typing.stop()
        self.typing.setVisible(False)

    def finalize_response(self):
        """Post-traitement : arrête le curseur clignotant."""
        self.hide_typing()

    def _resize_to_content(self):
        try:
            doc = self.msg_text.document()
            doc.setTextWidth(self.msg_text.viewport().width())
            h = doc.documentLayout().documentSize().height()
            if h > 0:
                self.msg_text.setFixedHeight(int(h) + 4)
        except Exception:
            pass
