"""
NURU V16 — SessionMemory unifié (Item : Mémoire glissante).

Remplace les mémoires fragmentées :
- memory_store.py (V5 legacy) → DEPRECATED
- session/store.py (V10.3f) → DEPRECATED  
- MemoryManager V9 (6 couches) → pour mémoire LONGUE seulement

SessionMemory = buffer FIFO court terme (session courante)
- 6 messages max (3 tours user/assistant)
- Compatible format OpenAI/MLX messages
- Thread-safe pour PySide6 + asyncio
"""
import logging
from collections import deque
from typing import List, Dict, Any, Optional
from threading import Lock

logger = logging.getLogger(__name__)


class SessionMemory:
    """Buffer d'historique de session FIFO (First-In, First-Out).
    
    Garde les 6 derniers messages (3 échanges user/assistant).
    Suffisant pour le contexte conversationnel sans saturer la fenêtre
    de contexte du modèle 8B sur M1 8Go RAM unifiée.
    """
    
    def __init__(self, max_messages: int = 6):
        self.max_messages = max_messages
        self._history: deque = deque(maxlen=max_messages)
        self._lock = Lock()  # Thread-safe pour PySide6 + asyncio
    
    def add_message(self, role: str, content: str) -> None:
        """Ajoute un message à l'historique (thread-safe)."""
        with self._lock:
            self._history.append({"role": role, "content": content})
    
    def add_interaction(self, user_text: str, assistant_text: str) -> None:
        """Ajoute une interaction complète user+assistant (thread-safe)."""
        with self._lock:
            self._history.append({"role": "user", "content": user_text})
            self._history.append({"role": "assistant", "content": assistant_text})
            # Le deque gère automatiquement la troncature FIFO via maxlen
    
    def get_formatted_history(self) -> List[Dict[str, str]]:
        """Retourne l'historique formaté pour l'API OpenAI/MLX (thread-safe)."""
        with self._lock:
            return list(self._history)
    
    def get_recent_context(self, max_chars: int = 2000) -> str:
        """Retourne un résumé textuel des derniers échanges pour injection prompt."""
        with self._lock:
            if not self._history:
                return ""
            
            parts = []
            total_chars = 0
            for msg in reversed(self._history):
                role_label = "Utilisateur" if msg["role"] == "user" else "NURU"
                text = f"{role_label}: {msg['content']}"
                if total_chars + len(text) > max_chars:
                    break
                parts.insert(0, text)
                total_chars += len(text)
            
            return "\n".join(parts) if parts else ""
    
    def clear(self) -> None:
        """Vide l'historique (thread-safe)."""
        with self._lock:
            self._history.clear()
    
    def __len__(self) -> int:
        with self._lock:
            return len(self._history)
    
    def __bool__(self) -> bool:
        with self._lock:
            return bool(self._history)


# Instance globale (singleton) pour la session courante
_session_memory_instance: Optional[SessionMemory] = None
_session_memory_lock = Lock()


def get_session_memory(max_messages: int = 6) -> SessionMemory:
    """Retourne l'instance singleton de SessionMemory (création lazy)."""
    global _session_memory_instance
    with _session_memory_lock:
        if _session_memory_instance is None:
            _session_memory_instance = SessionMemory(max_messages=max_messages)
            logger.info(f"🧠 SessionMemory initialisé (max_messages={max_messages})")
        return _session_memory_instance


def reset_session_memory() -> None:
    """Réinitialise l'instance globale (nouvelle session)."""
    global _session_memory_instance
    with _session_memory_lock:
        if _session_memory_instance is not None:
            _session_memory_instance.clear()
            _session_memory_instance = None
            logger.info("🧠 SessionMemory réinitialisé")