from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QSizePolicy, QFrame
from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QTextCursor
import datetime


class ChatBubble(QWidget):
    """Bulle de discussion V4.0 avec avatars circulaires et feedback V4.5."""

    # V4.5 Phase 4 : Signal de feedback (up/down) avec le texte du message
    feedback_given = Signal(str, str)  # (vote: 'up'|'down', message_text)

    def __init__(self, sender: str, message: str, is_user: bool = False, parent=None):
        super().__init__(parent)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setAlignment(Qt.AlignTop)

        # Avatar circulaire (discret, sans bordure colorée)
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(24, 24)
        if is_user:
            self.icon_label.setStyleSheet(
                "background-color: #3A3A3A; "
                "border-radius: 12px;"
            )
        else:
            self.icon_label.setStyleSheet(
                "background-color: #2A2A2A; "
                "border-radius: 12px;"
            )

        main_layout.addWidget(self.icon_label, 0, Qt.AlignTop)

        # Contenu
        content_wrapper = QFrame()
        content_wrapper.setObjectName("BubbleFrame")
        if not is_user:
            content_wrapper.setObjectName("AssistantBubbleFrame")
        
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(15, 12, 15, 12)
        content_layout.setSpacing(4)

        # Header
        header_layout = QHBoxLayout()
        name_label = QLabel(sender.upper())
        name_label.setObjectName("BubbleName")

        time_label = QLabel(datetime.datetime.now().strftime("%H:%M:%S"))
        time_label.setObjectName("BubbleTime")

        header_layout.addWidget(name_label)
        header_layout.addStretch()
        header_layout.addWidget(time_label)

        content_layout.addLayout(header_layout)

        # Message (QTextEdit pour supporter les longs textes et le streaming)
        self.msg_text = QTextEdit()
        self.msg_text.setReadOnly(True)
        self.msg_text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.msg_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.msg_text.setFrameShape(QFrame.NoFrame)
        self.msg_text.setObjectName("BubbleText")
        self.msg_text.setPlainText(message)
        
        # Ajuster la hauteur au contenu
        self.msg_text.document().setDocumentMargin(0)
        self.msg_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.msg_text.textChanged.connect(self._resize_to_content)

        content_layout.addWidget(self.msg_text)

        # V4.5 Phase 4 : Boutons de feedback 👍/👎 (uniquement pour assistant)
        if not is_user:
            feedback_layout = QHBoxLayout()
            feedback_layout.setContentsMargins(0, 4, 0, 0)
            feedback_layout.setSpacing(8)

            self.btn_up = QPushButton("👍")
            self.btn_up.setObjectName("BtnFeedback")
            self.btn_up.setFixedSize(32, 28)
            self.btn_up.setCursor(Qt.PointingHandCursor)

            self.btn_down = QPushButton("👎")
            self.btn_down.setObjectName("BtnFeedback")
            self.btn_down.setFixedSize(32, 28)
            self.btn_down.setCursor(Qt.PointingHandCursor)

            self.feedback_status = QLabel("")
            self.feedback_status.setObjectName("FeedbackStatus")

            feedback_layout.addWidget(self.btn_up)
            feedback_layout.addWidget(self.btn_down)
            feedback_layout.addWidget(self.feedback_status)
            feedback_layout.addStretch()
            content_layout.addLayout(feedback_layout)

        main_layout.addWidget(content_wrapper, 1)
        if is_user:
            main_layout.insertStretch(0, 1) # Align user to right
        else:
            main_layout.addStretch(1) # Align assistant to left


    def _on_feedback(self, vote: str):
        """Émet le signal de feedback et désactive les deux boutons."""
        self.btn_up.setEnabled(False)
        self.btn_down.setEnabled(False)
        emoji = "👍" if vote == "up" else "👎"
        self.feedback_status.setText(f"{emoji} Merci de votre retour !")
        self.feedback_given.emit(vote, self.msg_text.toPlainText())

    def _resize_to_content(self):
        """Ajuste la hauteur du QTextEdit au contenu."""
        try:
            doc = self.msg_text.document()
            doc.setTextWidth(self.msg_text.viewport().width())
            h = doc.documentLayout().documentSize().height()
            if h > 0:
                self.msg_text.setFixedHeight(int(h) + 4)
        except Exception:
            pass

    def append_text(self, text: str):
        """Streaming de texte."""
        try:
            cursor = self.msg_text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(text)
            self.msg_text.setTextCursor(cursor)
        except RuntimeError:
            pass
