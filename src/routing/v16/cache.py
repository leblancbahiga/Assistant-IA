"""NURU Router V16 — Cache de décision, conscient du contexte.

Bug latent dans TTLDecisionCache (router.py V12) : la clé de cache est
`make_key(query_lower)` — uniquement le texte. Or à partir du niveau 4
(contexte), deux requêtes texte-identiques ("Résume-le.") peuvent avoir des
décisions différentes selon le document ouvert. Sans le contexte dans la
clé, le cache renverrait la mauvaise route dès la deuxième occurrence.

Correctif : la clé inclut un fingerprint du contexte pertinent
(last_document_ref). Coût : quelques octets par entrée, négligeable sur
un cache de 256 entrées.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Any, Optional


def make_key(folded_query: str, context_fingerprint: str) -> str:
    return f"{folded_query}::{context_fingerprint}"


@dataclass
class CacheEntry:
    value: Any
    inserted_at: float


class TTLDecisionCache:
    def __init__(self, maxsize: int = 256, ttl_seconds: float = 300.0):
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        self._store: "OrderedDict[str, CacheEntry]" = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> Optional[Any]:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if now - entry.inserted_at > self.ttl_seconds:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return entry.value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = CacheEntry(value=value, inserted_at=time.monotonic())
            while len(self._store) > self.maxsize:
                self._store.popitem(last=False)

    def invalidate_document(self, document_ref: str) -> None:
        """À appeler quand un document est fermé/modifié : purge toute
        entrée de cache dont le fingerprint contexte référence ce doc."""
        with self._lock:
            dead = [k for k in self._store if f"doc={document_ref}" in k]
            for k in dead:
                del self._store[k]
