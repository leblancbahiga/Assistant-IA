"""
Cache LLM multi-niveau V10.2.

Hiérarchie :
  L1 (RAM)   → OrderedDict + MD5 hash. Hit en O(1), pas d'embedding.
  L2 (Disque) → memory_store.semantic_cache (SQLite + vec0). Hit cosinus ≥ 0.92.

get()  : L1 → L2 → None. Un hit L2 est promu dans L1.
set()  : L1 + L2 atomiquement.

Threading : asyncio.Lock() sur L1 (mutations dict), L2 déjà protégé par son propre lock.
"""

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from typing import Optional

from src.config import config

logger = logging.getLogger(__name__)


class LLMCacheEntry:
    """Entrée dans le cache L1."""
    __slots__ = ("response", "diagnostic", "ts")

    def __init__(self, response: str, diagnostic: Optional[dict], ts: float):
        self.response = response
        self.diagnostic = diagnostic
        self.ts = ts


class LLMCache:
    """Cache LLM multi-niveau.

    L1 : RAM (OrderedDict, hash exact, TTL configurable depuis config.cache_ttl_seconds).
    L2 : Délégue à memory_store.get_cache / set_cache (SQLite sémantique).

    Usage :
        cache = LLMCache(memory_store)
        hit, diag = await cache.get(query)
        if hit:
            yield hit
        else:
            response = await generate(...)
            await cache.set(query, response, diagnostic=diag)
            yield response
    """

    def __init__(self, memory_store, maxsize: Optional[int] = None, ttl: Optional[int] = None):
        self.memory_store = memory_store
        self._maxsize = maxsize or config.cache_maxsize  # 256
        self._ttl = ttl or config.cache_ttl_seconds        # 300 (5 min)
        self._l1: OrderedDict[str, LLMCacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()

        # Stats L1
        self.l1_hits = 0
        self.l1_misses = 0
        self.l1_expired = 0

    # ── Public API ─────────────────────────────────────────────────

    async def get(self, query: str) -> tuple[Optional[str], Optional[dict]]:
        """Cherche dans L1 (hash), puis L2 (sémantique). Retourne (response, diagnostic)."""
        # L1 : hash exact, O(1)
        key = self._hash(query)
        async with self._lock:
            entry = self._l1.get(key)
            if entry is not None:
                if time.time() - entry.ts < self._ttl:
                    self._l1.move_to_end(key)  # LRU refresh
                    self.l1_hits += 1
                    logger.debug(f"🧠 LLM Cache L1 Hit (key={key[:8]}…)")
                    return entry.response, entry.diagnostic
                else:
                    # Expiré
                    del self._l1[key]
                    self.l1_expired += 1

        self.l1_misses += 1

        # L2 : sémantique SQLite
        l2_response, l2_diag = await self.memory_store.get_cache(query)
        if l2_response is not None:
            # Promu dans L1
            async with self._lock:
                self._l1[key] = LLMCacheEntry(l2_response, l2_diag, time.time())
                self._trim_l1()
            logger.debug(f"🧠 LLM Cache L2 Hit → promu L1 (key={key[:8]}…)")
            return l2_response, l2_diag

        return None, None

    async def set(self, query: str, response: str, diagnostic: Optional[dict] = None):
        """Stocke dans L1 (RAM) + L2 (SQLite). L2 est async et peut être
        appelé en fire-and-forget si la latence est critique."""
        key = self._hash(query)
        now = time.time()

        # L1 : écriture synchrone en RAM
        async with self._lock:
            self._l1[key] = LLMCacheEntry(response, diagnostic, now)
            self._trim_l1()

        # L2 : écriture persistante
        await self.memory_store.set_cache(query, response, diagnostic)
        logger.debug(f"🧠 LLM Cache SET L1+L2 (key={key[:8]}…)")

    # ── Stats ──────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        total = self.l1_hits + self.l1_misses
        return {
            "l1_size": len(self._l1),
            "l1_maxsize": self._maxsize,
            "l1_ttl": self._ttl,
            "l1_hits": self.l1_hits,
            "l1_misses": self.l1_misses,
            "l1_expired": self.l1_expired,
            "l1_hit_rate": round(self.l1_hits / max(total, 1), 4),
        }

    async def clear_l1(self):
        """Vide le cache RAM (utile pour test ou purge manuelle)."""
        async with self._lock:
            self._l1.clear()
            self.l1_hits = 0
            self.l1_misses = 0
            self.l1_expired = 0
        logger.info("🧠 LLM Cache L1 purgé.")

    # ── Interne ────────────────────────────────────────────────────

    @staticmethod
    def _hash(query: str) -> str:
        # V16 AUDIT FIX QW13 : normaliser la requête avant hash
        # Évite les misses de cache pour variations mineures (espaces, casse)
        normalized = query.strip().lower()
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

    def _trim_l1(self):
        """Élimine les entrées les plus anciennes si L1 dépasse maxsize."""
        while len(self._l1) > self._maxsize:
            self._l1.popitem(last=False)

    def __len__(self) -> int:
        return len(self._l1)
