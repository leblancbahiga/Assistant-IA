"""NURU V15 Phase 3 — WorkingMemory (P1 #32).

Mémoire de travail : contexte de session en RAM avec TTL.
Stocke les données éphémères de la session en cours : contexte de
conversation, résultats RAG temporaires, état UI, préférences de session.

Couche 1/6 du MemoryManager unifié (Item 28).
"""

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class WorkingMemory:
    """Contexte de session en RAM avec TTL automatique.

    Les entrées expirent après working_ttl secondes.
    Le cache est limité à max_entries pour éviter les fuites mémoire.
    """

    def __init__(self, working_ttl: float = 300.0, max_entries: int = 200):
        self._ttl = working_ttl
        self._max = max_entries
        self._data: dict[str, tuple[float, Any]] = {}

    # ── CRUD ──────────────────────────────────────────────────────────

    def set(self, key: str, value: Any) -> None:
        """Stocke une valeur avec timestamp courant."""
        self._evict_expired()
        if len(self._data) >= self._max:
            self._evict_oldest()
        self._data[key] = (time.time(), value)
        logger.debug("🧠 WorkingMemory.set(%s) → %d entrées", key, len(self._data))

    def get(self, key: str, default: Any = None) -> Any:
        """Récupère une valeur. Retourne default si absente ou expirée."""
        self._evict_expired()
        entry = self._data.get(key)
        if entry is None:
            return default
        ts, value = entry
        if self._is_expired(ts):
            del self._data[key]
            return default
        return value

    def delete(self, key: str) -> bool:
        """Supprime une entrée. Retourne True si existait."""
        return self._data.pop(key, None) is not None

    def clear(self) -> None:
        """Vide toute la mémoire de travail."""
        self._data.clear()
        logger.debug("🧠 WorkingMemory effacée")

    def keys(self) -> list[str]:
        """Retourne les clés non expirées."""
        self._evict_expired()
        return list(self._data.keys())

    def all(self) -> dict[str, Any]:
        """Retourne toutes les entrées non expirées (copie)."""
        self._evict_expired()
        return {k: v[1] for k, v in self._data.items()}

    def count(self) -> int:
        """Nombre d'entrées actives."""
        self._evict_expired()
        return len(self._data)

    # ── Session helpers ───────────────────────────────────────────────

    def set_session_context(self, session_id: str, context: dict) -> None:
        """Stocke le contexte complet d'une session."""
        self.set(f"session:{session_id}", context)

    def get_session_context(self, session_id: str) -> Optional[dict]:
        """Récupère le contexte complet d'une session."""
        return self.get(f"session:{session_id}")

    def set_conversation_turns(self, session_id: str, turns: int) -> None:
        """Compteur de tours de conversation."""
        self.set(f"turns:{session_id}", turns)

    def increment_turns(self, session_id: str) -> int:
        """Incrémente et retourne le compteur de tours."""
        current = self.get(f"turns:{session_id}", 0) or 0
        self.set(f"turns:{session_id}", current + 1)
        return current + 1

    # ── Interne ───────────────────────────────────────────────────────

    def _is_expired(self, timestamp: float) -> bool:
        return (time.time() - timestamp) > self._ttl

    def _evict_expired(self) -> int:
        """Supprime les entrées expirées. Retourne le nombre supprimé."""
        now = time.time()
        expired = [k for k, (ts, _) in self._data.items() if (now - ts) > self._ttl]
        for k in expired:
            del self._data[k]
        if expired:
            logger.debug("🧠 WorkingMemory: %d entrées expirées purgées", len(expired))
        return len(expired)

    def _evict_oldest(self) -> None:
        """Supprime l'entrée la plus ancienne (FIFO eviction)."""
        if not self._data:
            return
        oldest = min(self._data.items(), key=lambda x: x[1][0])
        del self._data[oldest[0]]
        logger.debug("🧠 WorkingMemory: éviction FIFO de %s", oldest[0])
