"""ViewModel du chat — prépare les messages pour l'affichage."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MessageViewModel:
    """Un message formaté pour l'affichage."""
    sender: str
    content: str
    is_user: bool
    timestamp: str = ""
    citations: list[str] = field(default_factory=list)
    confidence: float = 0.0
    feedback: Optional[str] = None  # 'up' | 'down' | None


class ChatViewModel:
    """Logique d'affichage du chat : formatage, historique, streaming."""

    def __init__(self, max_messages: int = 50):
        self.messages: list[MessageViewModel] = []
        self.max_messages = max_messages

    def add_message(self, sender: str, content: str, is_user: bool,
                    citations: list[str] = None, confidence: float = 0.0) -> MessageViewModel:
        import datetime
        msg = MessageViewModel(
            sender=sender,
            content=content,
            is_user=is_user,
            timestamp=datetime.datetime.now().strftime("%H:%M:%S"),
            citations=citations or [],
            confidence=confidence,
        )
        self.messages.append(msg)
        if len(self.messages) > self.max_messages:
            self.messages.pop(0)
        return msg

    def get_last_message(self) -> Optional[MessageViewModel]:
        return self.messages[-1] if self.messages else None

    def register_feedback(self, message_index: int, vote: str):
        if 0 <= message_index < len(self.messages):
            self.messages[message_index].feedback = vote

    def clear(self):
        self.messages.clear()
