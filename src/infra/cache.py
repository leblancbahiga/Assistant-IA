"""Infrastructure de cache TTL pour décisions de routage."""
from cachetools import TTLCache
from hashlib import sha1


class TTLDecisionCache:
    """Cache LRU avec TTL pour les décisions de routage du SemanticRouter.

    Permet d'éviter le re-routage complet pour des requêtes identiques ou
    quasi-identiques dans un intervalle de temps configurable.
    Utilisé en Phase 0 — Quick Win : active enfin le cache routeur.
    """

    def __init__(self, maxsize: int = 256, ttl_seconds: int = 300):
        self.cache = TTLCache(maxsize=maxsize, ttl=ttl_seconds)

    def make_key(self, query: str, mode: str = "default") -> str:
        """Génère une clé de cache déterministe à partir de la requête et du mode."""
        return sha1(f"{query}|{mode}".encode()).hexdigest()

    def get(self, key: str):
        return self.cache.get(key)

    def set(self, key: str, value):
        self.cache[key] = value

    @property
    def size(self) -> int:
        return len(self.cache)

    def clear(self):
        self.cache.clear()
