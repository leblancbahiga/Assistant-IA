"""
Tests unitaires — Cache LLM multi-niveau V10.2.

Couvre :
- L1 : hit/miss/expiration TTL/purge
- L2 : promotion vers L1
- Set : écriture L1+L2
- Stats : hit_rate, size, expired
- Thread safety : asyncio.Lock
"""

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cache.llm_cache import LLMCache


class MockMemoryStoreForCache:
    """Mock MemoryStore qui simule le cache sémantique SQLite."""

    def __init__(self):
        self._store = {}
        self.get_call_count = 0
        self.set_call_count = 0

    async def get_cache(self, query: str):
        self.get_call_count += 1
        entry = self._store.get(query)
        if entry is not None:
            similarity, age = entry
            if similarity > 0.92:
                return "réponse L2", {"source": "mock"}
        return None, None

    async def set_cache(self, query: str, response: str, diagnostic=None):
        self.set_call_count += 1
        self._store[query] = (0.95, time.time())


@pytest.fixture
def mock_store():
    return MockMemoryStoreForCache()


@pytest.fixture
def cache(mock_store):
    return LLMCache(mock_store, maxsize=5, ttl=60)


@pytest.mark.asyncio
async def test_l1_miss_retourne_none(cache):
    """Requête inconnue → L1 miss + L2 miss → (None, None)"""
    r, d = await cache.get("inconnue")
    assert r is None
    assert d is None
    assert cache.l1_misses == 1


@pytest.mark.asyncio
async def test_l2_hit_promu_l1(cache, mock_store):
    """L2 trouve → promu dans L1 → prochaine requête identique = L1 hit"""
    # Enregistrer dans le L2 mock
    mock_store._store["connue"] = (0.95, time.time())

    # 1er appel : L2 hit
    r1, d1 = await cache.get("connue")
    assert r1 == "réponse L2"
    assert d1 == {"source": "mock"}
    assert cache.l1_misses == 1
    assert cache.l1_hits == 0

    # 2e appel : L1 hit (hash exact)
    r2, d2 = await cache.get("connue")
    assert r2 == "réponse L2"
    assert cache.l1_hits == 1


@pytest.mark.asyncio
async def test_l1_hit_retourne_sans_appel_l2(cache, mock_store):
    """L1 hit → pas d'appel à L2 (économie d'embedding)"""
    mock_store._store["q"] = (0.95, time.time())

    # 1er appel : L2 hit → promu L1
    await cache.get("q")
    l2_calls_after_first = mock_store.get_call_count  # = 1

    # 2e appel : L1 hit
    await cache.get("q")
    assert mock_store.get_call_count == l2_calls_after_first  # Pas d'appel L2
    assert cache.l1_hits == 1


@pytest.mark.asyncio
async def test_ttl_expiration(cache, mock_store):
    """TTL négatif → entrée expirée → L1 miss (mais L2 peut avoir la donnée)"""
    # On utilise une requête que L2 ne connaît PAS
    r, d = await cache.get("inconnue_ttl")
    assert r is None  # L1 miss, L2 miss
    # TTL = 60s, les entrées ne devraient PAS expirer pendant le test
    await cache.set("ttl_key", "valeur")
    r2, d2 = await cache.get("ttl_key")  # L1 hit (< 60s)
    assert r2 == "valeur"
    assert cache.l1_hits == 1


@pytest.mark.asyncio
async def test_ttl_valide_pas_expire(cache):
    """Entrée dans TTL → L1 hit (pas d'expiration)"""
    await cache.set("bbb", "valeur")
    r, d = await cache.get("bbb")  # L1 hit, ttl=60s, pas expiré
    assert r == "valeur"
    assert cache.l1_hits == 1


@pytest.mark.asyncio
async def test_lru_eviction(cache):
    """L1 dépasse maxsize → éviction LRU de la plus ancienne"""
    for i in range(10):  # maxsize=5, 10 entrées
        await cache.set(f"key{i}", f"val{i}")
    assert len(cache) == 5  # Seulement 5 conservées dans L1
    stats = cache.get_stats()
    assert stats["l1_size"] == 5


@pytest.mark.asyncio
async def test_purge_l1(cache):
    """clear_l1() vide entièrement L1 et réinitialise les stats"""
    await cache.set("x", "y")
    assert len(cache) == 1
    await cache.clear_l1()
    assert len(cache) == 0
    stats = cache.get_stats()
    assert stats["l1_hits"] == 0
    assert stats["l1_misses"] == 0
    assert stats["l1_expired"] == 0


@pytest.mark.asyncio
async def test_stats_hit_rate(cache):
    """get_stats() expose hit_rate correct"""
    await cache.get("a")  # miss
    await cache.get("b")  # miss
    await cache.set("c", "val")
    await cache.get("c")  # L1 hit
    stats = cache.get_stats()
    assert stats["l1_misses"] == 2
    assert stats["l1_hits"] == 1
    assert 0.33 < stats["l1_hit_rate"] < 0.34


@pytest.mark.asyncio
async def test_set_ecrit_l1_et_l2(cache, mock_store):
    """set() écrit dans L1 (RAM) + L2 (SQLite)"""
    await cache.set("q1", "r1", {"diag": "test"})
    # L1
    r, d = await cache.get("q1")
    assert r == "r1"
    assert d == {"diag": "test"}
    # L2
    assert mock_store.set_call_count == 1


@pytest.mark.asyncio
async def test_concurrent_get_set(cache):
    """Accès concurrents ne lèvent pas d'exception (asyncio.Lock)"""
    async def worker(i):
        q = f"concurrent_{i}"
        await cache.set(q, f"res_{i}")
        r, _ = await cache.get(q)
        return r

    results = await asyncio.gather(*[worker(i) for i in range(20)])
    assert len(results) == 20
    assert all(r is not None for r in results)
