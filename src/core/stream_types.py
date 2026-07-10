"""Types pour le streaming de tokens MLX — callback structuré + cancel token.

V15 Phase 2 — Item 26 (P0 #11) : callback de génération MLX pour envoyer
les tokens un par un à l'UI (effet wow immédiat).

Usage :
    async with TokenStream() as stream:
        for token in generator:
            stream.emit(token)

    # Abort depuis un autre thread/coroutine :
    stream.cancel()
"""

from __future__ import annotations

import asyncio
import enum
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable


class StreamEventType(enum.Enum):
    """Type d'événement dans le flux de génération."""
    TOKEN = "token"               # Nouveau token généré
    ERROR = "error"               # Erreur de génération
    DONE = "done"                 # Génération terminée
    CANCELLED = "cancelled"       # Génération annulée


@dataclass
class StreamEvent:
    """Événement de streaming — token ou métadonnée."""
    type: StreamEventType
    text: str = ""
    token_count: int = 0
    elapsed_ms: float = 0.0
    error: Optional[str] = None


# Callback synchrone (rapide — UI, logs)
TokenCallback = Callable[[str], None]
# Callback asynchrone (lent — TTS, écriture fichier)
AsyncTokenCallback = Callable[[str], Awaitable[None]]


class CancellationToken:
    """Token d'annulation pour la génération en streaming.

    Permet à l'UI d'arrêter la génération à tout moment sans
    avoir à fermer le générateur asynchrone.

    Thread-safe : utilise un Event asyncio.
    """

    def __init__(self):
        self._event = asyncio.Event()

    def cancel(self):
        """Demande l'annulation. Appelable depuis n'importe quel thread."""
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    async def wait_cancel(self):
        """Attend que l'annulation soit demandée."""
        await self._event.wait()


@dataclass
class StreamSession:
    """Session de streaming — agrège le callback, le cancel token et les stats.

    Usage :
        session = StreamSession()
        session.on_token = lambda t: ui.append(t)

        # Dans le générateur :
        for token in stream_generate(...):
            if session.is_cancelled:
                break
            session.emit(token)
            yield token

        session.finalize()
    """

    cancel_token: CancellationToken = field(default_factory=CancellationToken)
    on_token: Optional[TokenCallback] = None
    on_async_token: Optional[AsyncTokenCallback] = None
    on_event: Optional[Callable[[StreamEvent], None]] = None

    # Stats
    token_count: int = 0
    start_time: float = 0.0
    first_token_time: float = 0.0
    _done: bool = False

    def start(self):
        """Marque le début de la session."""
        self.start_time = time.perf_counter()
        self.token_count = 0
        self._done = False

    def emit(self, token: str):
        """Émet un token vers tous les callbacks enregistrés."""
        if self._done:
            return
        if self.token_count == 0:
            self.first_token_time = time.perf_counter()
        self.token_count += 1

        # Callback synchrone
        if self.on_token:
            self.on_token(token)
        # Événement structuré
        if self.on_event:
            elapsed = (time.perf_counter() - self.start_time) * 1000
            self.on_event(StreamEvent(
                type=StreamEventType.TOKEN,
                text=token,
                token_count=self.token_count,
                elapsed_ms=elapsed,
            ))

    def cancel(self):
        """Demande l'annulation."""
        self.cancel_token.cancel()

    @property
    def is_cancelled(self) -> bool:
        return self.cancel_token.is_cancelled

    def finalize(self, error: Optional[str] = None):
        """Finalise la session — émet l'événement de fin."""
        if self._done:
            return
        self._done = True
        elapsed = (time.perf_counter() - self.start_time) * 1000 if self.start_time else 0

        if error:
            if self.on_event:
                self.on_event(StreamEvent(
                    type=StreamEventType.ERROR,
                    error=error,
                    token_count=self.token_count,
                    elapsed_ms=elapsed,
                ))
        elif self.is_cancelled:
            if self.on_event:
                self.on_event(StreamEvent(
                    type=StreamEventType.CANCELLED,
                    token_count=self.token_count,
                    elapsed_ms=elapsed,
                ))
        else:
            if self.on_event:
                self.on_event(StreamEvent(
                    type=StreamEventType.DONE,
                    token_count=self.token_count,
                    elapsed_ms=elapsed,
                ))
