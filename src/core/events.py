"""Bus d'événements unifié pour NURU V8+.

Fusion de src/event_bus.py (singleton V3/V4) et src/core/events.py (V8+).
Thread-safe, singleton, compatible UI Qt.
"""
import asyncio
import logging
from typing import Callable, Any, Dict, List, Tuple
from collections import deque
from threading import Lock

logger = logging.getLogger(__name__)


class EventBus:
    """Bus d'événements thread-safe avec abonnement asynchrone et singleton.

    - subscribe() / unsubscribe() pour les abonnés
    - emit() pour les émetteurs async
    - emit_sync() pour les émetteurs synchrones (ex: RuntimeManager)
    - drain_events() pour l'UI Qt (vide la file dans le timer)
    """

    _instance = None
    _singleton_lock = Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._listeners: Dict[str, List[Callable]] = {}
                    instance._queue: deque = deque(maxlen=500)
                    instance._lock = Lock()
                    instance._queue_lock = Lock()
                    cls._instance = instance
        return cls._instance

    # ─── Abonnement ───

    def subscribe(self, event_type: str, callback: Callable):
        with self._lock:
            self._listeners.setdefault(event_type, []).append(callback)

    def unsubscribe(self, event_type: str, callback: Callable):
        with self._lock:
            lst = self._listeners.get(event_type, [])
            if callback in lst:
                lst.remove(callback)

    # ─── Émission ───

    async def emit(self, event_type: str, data: Any = None):
        """Émet un événement : met en file + notifie les abonnés async."""
        self._enqueue(event_type, data)

        listeners = []
        with self._lock:
            listeners = list(self._listeners.get(event_type, []))

        if not listeners:
            return

        tasks = []
        for cb in listeners:
            if asyncio.iscoroutinefunction(cb):
                tasks.append(cb(data))
            else:
                try:
                    cb(data)
                except Exception as e:
                    logger.error(f"[EventBus] {event_type}: {e}")

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def emit_sync(self, event_type: str, data: Any = None):
        """Émet depuis un contexte synchrone : met en file uniquement."""
        self._enqueue(event_type, data)

    # ─── File d'attente ───

    def _enqueue(self, event_type: str, data: Any):
        with self._queue_lock:
            self._queue.append((event_type, data))

    def drain(self) -> List[tuple]:
        """Vide la file (appelé depuis le timer Qt)."""
        events = []
        with self._queue_lock:
            while self._queue:
                events.append(self._queue.popleft())
        return events

    # Alias pour compatibilité avec le dashboard (ancien nom)
    drain_events = drain
