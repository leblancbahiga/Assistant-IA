"""
NURU Kernel — Cache Centralisé (Phase aval).

Registre de caches régionaux avec TTL, priorité d'éviction,
et intégration au système de ressources du kernel.

Chaque région est un cache nommé qui suit le protocole ClearableCache
pour que KernelResources / RAMBudgetManager puisse l'évacuer
sous pression mémoire.

Usage :
    cache = KernelCache()
    cache.create_region("embedding", ttl=300, max_entries=1000)
    cache.create_region("llm", ttl=3600, max_entries=100, max_size_mb=200)

    # Get/set
    val = cache.get("embedding", key="doc_42")
    cache.set("embedding", key="doc_42", value=vector, size_bytes=8192)

    # Compute if absent
    result = cache.get_or_compute("llm", query_hash, compute_fn)

    # Stats
    cache.stats()
    cache.region_stats("embedding")

    # Éviction (appelé par KernelResources)
    cache.evict(priority_threshold=2)   # évince les priority >= 2
    cache.evict_all("embedding")
"""

import logging
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ── Types ──────────────────────────────────────────────────────


@dataclass
class CacheEntry:
    """Entrée individuelle dans une région de cache."""
    key: str
    value: Any
    ttl: float            # secondes (0 = infini)
    priority: int         # 0=protégé, 1=normal, 2=évincable en premier
    created_at: float     # time.monotonic()
    size_bytes: int = 0   # estimation mémoire (0 = inconnu)
    hits: int = 0
    last_access: float = 0.0

    @property
    def expired(self) -> bool:
        if self.ttl <= 0:
            return False
        return time.monotonic() - self.created_at > self.ttl


@dataclass
class CacheRegion:
    """Région de cache nommée."""
    name: str
    ttl: float
    max_entries: int
    max_size_bytes: int = 0        # 0 = pas de limite mémoire
    entries: dict[str, CacheEntry] = field(default_factory=dict)
    current_size: int = 0
    hits: int = 0
    misses: int = 0
    evictions: int = 0


# ── Cache Central ──────────────────────────────────────────────


class KernelCache:
    """Registre centralisé de caches NURU.

    Chaque composant crée sa région avec create_region(), puis
    utilise get/set/get_or_compute sur cette région.

    L'éviction est déclenchée :
    - Automatiquement à chaque set() si la région dépasse ses limites
    - Par KernelResources via evict() sous pression mémoire
    - Manuellement via evict_all() / clear()

    Thread-safe (Lock par région).
    """

    def __init__(self):
        self._regions: dict[str, CacheRegion] = {}
        self._lock = Lock()
        self._default_ttl = 300.0   # 5 min
        self._default_max = 500     # entrées par région

    # ── Gestion des régions ────────────────────────────────────

    def create_region(
        self,
        name: str,
        ttl: Optional[float] = None,
        max_entries: Optional[int] = None,
        max_size_mb: int = 0,
    ) -> None:
        """Crée ou réinitialise une région de cache.

        Args:
            name: Identifiant unique de la région
            ttl: TTL par défaut pour les entrées (defaut: 300s)
            max_entries: Nombre max d'entrées (defaut: 500)
            max_size_mb: Limite mémoire en MB (0 = pas de limite)
        """
        region = CacheRegion(
            name=name,
            ttl=ttl if ttl is not None else self._default_ttl,
            max_entries=max_entries if max_entries is not None else self._default_max,
            max_size_bytes=max_size_mb * 1024 * 1024,
        )
        with self._lock:
            self._regions[name] = region
        logger.info(
            "🗂️ Cache region '%s' (ttl=%ss, max=%d, max_size=%dMB)",
            name, region.ttl, region.max_entries, max_size_mb,
        )

    def has_region(self, name: str) -> bool:
        with self._lock:
            return name in self._regions

    def drop_region(self, name: str) -> None:
        """Supprime une région et toutes ses entrées."""
        with self._lock:
            self._regions.pop(name, None)

    # ── Opérations ─────────────────────────────────────────────

    def get(self, region: str, key: str, default: Any = None) -> Any:
        """Récupère une entrée du cache.

        Retourne None ou default si absente ou expirée.
        """
        r = self._get_region(region)
        if r is None:
            return default

        entry = r.entries.get(key)
        if entry is None:
            r.misses += 1
            return default

        if entry.expired:
            self._delete(r, key)
            r.misses += 1
            return default

        entry.hits += 1
        entry.last_access = time.monotonic()
        r.hits += 1
        return entry.value

    def set(
        self,
        region: str,
        key: str,
        value: Any,
        ttl: Optional[float] = None,
        priority: int = 1,
        size_bytes: int = 0,
    ) -> None:
        """Stocke une entrée dans le cache.

        Args:
            region: Nom de la région
            key: Clé unique
            value: Valeur à stocker
            ttl: TTL en secondes (None = TTL de la région)
            priority: 0=protégé, 1=normal, 2=évincable
            size_bytes: Estimation mémoire (0 = inconnu)
        """
        r = self._get_region(region)
        if r is None:
            logger.warning("⚠️ Cache region '%s' inconnue", region)
            return

        # Si la clé existe déjà, soustraire l'ancienne taille
        old = r.entries.get(key)
        if old is not None:
            r.current_size -= old.size_bytes

        entry = CacheEntry(
            key=key,
            value=value,
            ttl=ttl if ttl is not None else r.ttl,
            priority=priority,
            created_at=time.monotonic(),
            size_bytes=size_bytes,
            last_access=time.monotonic(),
        )
        r.entries[key] = entry
        r.current_size += size_bytes

        # Éviction si la région dépasse ses limites
        self._maybe_evict(r)

    def get_or_compute(
        self,
        region: str,
        key: str,
        compute_fn: Callable[[], Any],
        ttl: Optional[float] = None,
        priority: int = 1,
        size_bytes: int = 0,
    ) -> Any:
        """Récupère depuis le cache ou calcule et stocke.

        Utility pattern : évite la duplication du get/set.
        """
        cached = self.get(region, key)
        if cached is not None:
            return cached

        value = compute_fn()
        self.set(region, key, value, ttl=ttl, priority=priority, size_bytes=size_bytes)
        return value

    def delete(self, region: str, key: str) -> bool:
        """Supprime une entrée du cache.

        Returns:
            True si l'entrée existait.
        """
        r = self._get_region(region)
        if r is None:
            return False
        return self._delete(r, key)

    def _delete(self, r: CacheRegion, key: str) -> bool:
        entry = r.entries.pop(key, None)
        if entry is None:
            return False
        r.current_size -= entry.size_bytes
        return True

    # ── Éviction ───────────────────────────────────────────────

    def _maybe_evict(self, r: CacheRegion) -> None:
        """Évince les entrées si la région dépasse ses limites."""
        # Vérifier nombre d'entrées
        while len(r.entries) > r.max_entries:
            self._evict_one(r)

        # Vérifier taille mémoire
        if r.max_size_bytes > 0:
            while r.current_size > r.max_size_bytes:
                self._evict_one(r)

    def _evict_one(self, r: CacheRegion) -> None:
        """Évince l'entrée la moins prioritaire/la plus vieille.

        Stratégie : d'abord par priorité (3 niveaux), puis par last_access.
        """
        if not r.entries:
            return

        # Trouver le pire candidat
        worst = min(
            r.entries.values(),
            key=lambda e: (e.priority, e.last_access if e.last_access else e.created_at),
        )
        r.entries.pop(worst.key, None)
        r.current_size -= worst.size_bytes
        r.evictions += 1
        logger.debug("🧹 Cache evict: %s/%s (prio=%d, size=%d)",
                     r.name, worst.key, worst.priority, worst.size_bytes)

    def evict(self, priority_threshold: int = 2, region: Optional[str] = None) -> int:
        """Évince les entrées dont la priorité >= threshold.

        Args:
            priority_threshold: Priorité minimale à évincer
            region: Si spécifié, seulement cette région

        Returns:
            Nombre d'entrées évincées
        """
        total = 0
        regions = [region] if region else list(self._regions.keys())

        for name in regions:
            r = self._regions.get(name)
            if r is None:
                continue
            to_evict = [
                key for key, entry in r.entries.items()
                if entry.priority >= priority_threshold
            ]
            for key in to_evict:
                self._delete(r, key)
                r.evictions += 1
            total += len(to_evict)
            if to_evict:
                logger.info("🧹 Cache evict: %d entrées de '%s' (prio>=%d)",
                           len(to_evict), name, priority_threshold)

        return total

    def evict_all(self, region: Optional[str] = None, **kwargs) -> int:
        """Vide une région ou toutes les régions.

        **kwargs : ignoré (compatibilité avec RAMBudgetManager qui passe force=).
        
        Returns:
            Nombre d'entrées supprimées.
        """
        total = 0
        if region:
            r = self._regions.get(region)
            if r:
                total = len(r.entries)
                if total:
                    r.entries.clear()
                    r.current_size = 0
                    logger.info("🧹 Cache '%s' vidé (%d entrées)", region, total)
        else:
            for name, r in self._regions.items():
                if r.entries:
                    total += len(r.entries)
                    r.entries.clear()
                    r.current_size = 0
            if total:
                logger.info("🧹 Cache global vidé (%d entrées, %d régions)",
                           total, len(self._regions))
        return total

    def clear(self) -> None:
        """Alias pour evict_all(). Compatible ClearableCache."""
        self.evict_all()

    # ── Stats ──────────────────────────────────────────────────

    def region_stats(self, region: str) -> Optional[dict]:
        """Statistiques détaillées d'une région."""
        r = self._get_region(region)
        if r is None:
            return None

        with self._lock:
            return {
                "name": r.name,
                "ttl": r.ttl,
                "max_entries": r.max_entries,
                "max_size_mb": r.max_size_bytes / (1024 * 1024) if r.max_size_bytes else 0,
                "entries": len(r.entries),
                "current_size_mb": r.current_size / (1024 * 1024),
                "hits": r.hits,
                "misses": r.misses,
                "hit_ratio": r.hits / (r.hits + r.misses + 1),
                "evictions": r.evictions,
            }

    def stats(self) -> dict:
        """Statistiques globales."""
        with self._lock:
            total_entries = sum(len(r.entries) for r in self._regions.values())
            total_size = sum(r.current_size for r in self._regions.values())
            total_hits = sum(r.hits for r in self._regions.values())
            total_misses = sum(r.misses for r in self._regions.values())
            total_evictions = sum(r.evictions for r in self._regions.values())

        return {
            "regions": len(self._regions),
            "total_entries": total_entries,
            "total_size_mb": total_size / (1024 * 1024) if total_size else 0,
            "hits": total_hits,
            "misses": total_misses,
            "hit_ratio": total_hits / (total_hits + total_misses + 1),
            "evictions": total_evictions,
        }

    # ── Interne ────────────────────────────────────────────────

    def _get_region(self, name: str) -> Optional[CacheRegion]:
        with self._lock:
            return self._regions.get(name)

    # ── Cycle de vie kernel ────────────────────────────────────

    def start(self) -> None:
        """Prépare les régions par défaut."""
        # Créer les régions de base si elles n'existent pas
        defaults = [
            ("embedding", 300, 1000, 100),
            ("rag", 600, 500, 200),
            ("llm", 3600, 100, 300),
            ("router", 300, 256, 50),
            ("session", 7200, 50, 100),
        ]
        for name, ttl, max_entries, max_mb in defaults:
            if not self.has_region(name):
                self.create_region(name, ttl=ttl, max_entries=max_entries, max_size_mb=max_mb)

        logger.info("🗂️ Cache: %d régions prêtes", len(self._regions))

    def stop(self) -> None:
        """Libère toutes les entrées."""
        self.evict_all()
        logger.info("🗂️ Cache arrêté")

    def __repr__(self) -> str:
        total = sum(len(r.entries) for r in self._regions.values())
        return f"<KernelCache {len(self._regions)} régions, {total} entrées>"


# ── Protocole ClearableCache ──────────────────────────────────
# Pour compatibilité avec RAMBudgetManager et KernelResources.
# Une région de cache peut être utilisée comme callback d'éviction :

# kernel.resources.register_callback(
#     lambda: kernel.cache.evict(priority_threshold=1),
#     priority='memory',
# )
