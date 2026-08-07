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


# Registre de sessions cloisonne (V17: plus de singleton global)
_session_registry: dict[str, SessionMemory] = {}
_session_registry_lock = Lock()


def get_session_memory(session_id: str = "default", max_messages: int = 6) -> SessionMemory:
    """Retourne l'instance cloisonnee de SessionMemory pour l'ID de session.

    Chaque session_id possede sa propre memoire, sans contamination entre sessions.
    """
    with _session_registry_lock:
        if session_id not in _session_registry:
            _session_registry[session_id] = SessionMemory(max_messages=max_messages)
            logger.info(f"🧠 SessionMemory cree pour session={session_id}")
        return _session_registry[session_id]


def reset_session_memory(session_id: str | None = None) -> None:
    """Reinitialise la memoire d'une session (ou toutes si session_id=None)."""
    global _session_registry
    with _session_registry_lock:
        if session_id is None:
            _session_registry.clear()
            logger.info("🧠 Toutes les sessions memoire reinitialisees")
        elif session_id in _session_registry:
            _session_registry[session_id].clear()
            del _session_registry[session_id]
            logger.info(f"🧠 SessionMemory session={session_id} reinitialisee")