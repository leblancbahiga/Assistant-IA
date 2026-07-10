"""NURU V15 Phase 5 — RAMBudgetManager (Item 40, P1 #50).

Gestion centralisée du budget RAM pour M1 8 Go.

Objectifs :
1. Maintenir RSS total < 6 Go (marge 2 Go pour macOS)
2. Déchargement préemptif quand swap > 50 % ou RAM libre < 1 Go
3. Éviction par priorité : LLM > Embedder > Reranker > Cache
4. Intégration SleepCycle : flush mémoire épisodique avant déchargement

Usage:
    rbm = RAMBudgetManager()
    rbm.register_component("llm", priority=1, estimated_mb=3500)
    ...
    if not rbm.can_load("llm"):
        rbm.evict(priority_below=2)  # décharge reranker, cache
"""

import asyncio
import gc
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

logger = logging.getLogger(__name__)


___RAM_BUDGET_INSTANCE: Optional["RAMBudgetManager"] = None


def get_budget() -> "RAMBudgetManager":
    """Singleton global — une seule instance de RAMBudgetManager pour NURU."""
    global ___RAM_BUDGET_INSTANCE
    if ___RAM_BUDGET_INSTANCE is None:
        ___RAM_BUDGET_INSTANCE = RAMBudgetManager()
    return ___RAM_BUDGET_INSTANCE


class Priority(IntEnum):
    """Priorité d'éviction : plus le chiffre est bas, plus on garde."""
    LLM = 1       # Toujours garder si possible
    EMBEDDER = 2  # Garder entre les requêtes
    RERANKER = 3  # Décharger immédiatement après usage
    CACHE = 4     # Premier à évacuer
    MEMORY = 5    # Mémoire épisodique/session — compresser/en swap


@dataclass
class BudgetSlot:
    """Un composant enregistré avec son budget."""
    name: str
    priority: Priority
    estimated_mb: int       # Estimation du coût en RAM
    loaded: bool = False
    last_used: float = 0.0
    peak_mb: int = 0        # Mesure réelle au pic


@dataclass
class BudgetState:
    """État instantané du budget RAM."""
    total_ram_gb: float = 8.0         # M1 8 Go
    hard_limit_gb: float = 6.0        # Budget max pour NURU
    soft_limit_gb: float = 5.0        # Seuil d'éviction préemptive
    used_mb: int = 0                  # Somme des estimated_mb chargés
    free_ram_gb: float = 0.0          # RAM système libre
    swap_used_gb: float = 0.0
    swap_total_gb: float = 0.0
    swap_percent: float = 0.0
    process_rss_mb: float = 0.0           # RSS du processus NURU
    pressure_level: str = "normal"    # normal | warning | critical
    slots: list = field(default_factory=list)


class RAMBudgetManager:
    """Gestionnaire de budget RAM avec éviction priorisée.

    Remplace et étend ModelManager pour tous les composants.
    """

    def __init__(
        self,
        hard_limit_gb: float = 6.0,
        soft_limit_gb: float = 5.0,
        swap_warning_pct: float = 50.0,
    ):
        self.hard_limit_gb = hard_limit_gb
        self.soft_limit_gb = soft_limit_gb
        self.swap_warning_pct = swap_warning_pct
        self._components: dict[str, BudgetSlot] = {}
        self._model_storage: dict[str, Any] = {}  # Modèles effectivement chargés
        self._last_probe: float = 0.0
        self._probe_interval: float = 2.0  # secondes entre probes RAM
        self._cached_state: Optional[BudgetState] = None
        self._consolidation_callback: Optional[Callable] = None

    # ─── Enregistrement des composants ───────────────────────────────

    def register_component(
        self,
        name: str,
        priority: Priority,
        estimated_mb: int,
    ) -> None:
        """Enregistre un composant avec son budget estimé."""
        self._components[name] = BudgetSlot(
            name=name,
            priority=priority,
            estimated_mb=estimated_mb,
        )
        logger.debug(f"📋 RAM: {name} enregistré ({estimated_mb} MB, priorité {priority.name})")

    def unregister_component(self, name: str) -> None:
        """Supprime un composant du budget."""
        self._components.pop(name, None)
        self._model_storage.pop(name, None)
        logger.debug(f"🗑️ RAM: {name} retiré du budget")

    # ─── Cycle de vie des modèles ────────────────────────────────────

    def can_load(self, name: str) -> bool:
        """Vérifie si le chargement est possible sans dépasser le budget."""
        state = self.probe()
        comp = self._components.get(name)
        if not comp:
            return True  # Composant non enregistré → on laisse passer

        # Budget déjà dépassé ?
        if state.used_mb + comp.estimated_mb > state.hard_limit_gb * 1024:
            logger.warning(
                f"🚫 RAM: chargement {name} refusé "
                f"({state.used_mb + comp.estimated_mb} MB > {state.hard_limit_gb} Go)"
            )
            return False

        # Swap trop élevé ?
        if state.swap_percent > self.swap_warning_pct:
            logger.warning(
                f"🚫 RAM: swap à {state.swap_percent:.0f}% — "
                f"chargement {name} refusé"
            )
            return False

        return True

    def mark_loaded(self, name: str, model: Any = None) -> None:
        """Marque un composant comme chargé."""
        comp = self._components.get(name)
        if comp:
            comp.loaded = True
            comp.last_used = time.time()
            if model is not None:
                self._model_storage[name] = model
            logger.debug(f"📦 RAM: {name} marqué chargé ({comp.estimated_mb} MB)")

    def mark_unloaded(self, name: str) -> None:
        """Marque un composant comme déchargé."""
        comp = self._components.get(name)
        if comp:
            comp.loaded = False
        self._model_storage.pop(name, None)
        logger.debug(f"🧹 RAM: {name} marqué déchargé")

    def touch(self, name: str) -> None:
        """Rafraîchit le timestamp d'utilisation (keep-alive)."""
        comp = self._components.get(name)
        if comp:
            comp.last_used = time.time()

    # ─── Éviction priorisée ──────────────────────────────────────────

    def evict(self, priority_below: Priority = Priority.CACHE) -> list[str]:
        """Décharge tous les composants de priorité >= threshold.

        Args:
            priority_below: Priorité seuil (ex: Priority.RERANKER = décharge
                           reranker + cache + memory)

        Returns:
            Liste des noms de composants déchargés
        """
        evicted: list[str] = []
        for name, comp in sorted(
            self._components.items(),
            key=lambda x: (-x[1].priority.value, x[1].last_used),
        ):
            if comp.loaded and comp.priority >= priority_below:
                self._unload_component(name)
                evicted.append(name)

        if evicted:
            logger.info(
                f"🧹 RAM: éviction priorités ≥{priority_below.name} → "
                f"{evicted}"
            )
            gc.collect()
            self._try_clear_mlx_cache()
        return evicted

    def evict_one(self, exclude: Optional[set[str]] = None) -> Optional[str]:
        """Décharge le composant chargé de plus basse priorité.

        Utile pour faire de la place avant un chargement.
        """
        candidates = sorted(
            [(n, c) for n, c in self._components.items() if c.loaded],
            key=lambda x: (-x[1].priority.value, x[1].last_used),
        )
        for name, comp in candidates:
            if exclude and name in exclude:
                continue
            self._unload_component(name)
            logger.info(f"🧹 RAM: éviction unitaire {name}")
            return name
        return None

    def _unload_component(self, name: str) -> None:
        """Décharge effectivement un composant."""
        comp = self._components.get(name)
        if not comp:
            return

        model = self._model_storage.pop(name, None)
        if model is not None:
            # Appel à unload si disponible
            unloader = getattr(model, "unload", None)
            if callable(unloader):
                try:
                    unloader()
                except Exception as e:
                    logger.warning(f"⚠️ RAM: erreur unload {name}: {e}")
            del model

        comp.loaded = False
        comp.last_used = 0.0

    # ─── Sondes RAM ──────────────────────────────────────────────────

    def probe(self, force: bool = False) -> BudgetState:
        """Mesure l'état RAM actuel (caché 2s)."""
        now = time.time()
        if (
            not force
            and self._cached_state is not None
            and now - self._last_probe < self._probe_interval
        ):
            return self._cached_state

        import psutil

        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        proc = psutil.Process()

        state = BudgetState()
        state.free_ram_gb = vm.available / (1024**3)
        state.swap_used_gb = swap.used / (1024**3)
        state.swap_total_gb = swap.total / (1024**3)
        state.swap_percent = swap.percent
        state.process_rss_mb = proc.memory_info().rss / (1024**2)

        # Budget utilisé (somme des estimated_mb des composants chargés)
        used = sum(
            c.estimated_mb for c in self._components.values() if c.loaded
        )
        state.used_mb = used

        # Niveau de pression
        if state.free_ram_gb < 0.5 or state.swap_percent > 80:
            state.pressure_level = "critical"
        elif state.free_ram_gb < 1.0 or state.swap_percent > 50:
            state.pressure_level = "warning"
        else:
            state.pressure_level = "normal"

        state.slots = list(self._components.values())
        self._cached_state = state
        self._last_probe = now
        return state

    def get_pressure(self) -> str:
        """Retourne le niveau de pression actuel (sans log)."""
        return self.probe().pressure_level

    # ─── Nettoyage systèmes ──────────────────────────────────────────

    def force_gc(self) -> None:
        """GC complet + cache MLX."""
        gc.collect()
        self._try_clear_mlx_cache()
        logger.debug("🧹 GC + cache MLX vidé")

    @staticmethod
    def _try_clear_mlx_cache() -> None:
        try:
            import mlx.core as mx
            mx.clear_cache()
        except Exception:
            pass

    # ─── Consolidation mémoire ───────────────────────────────────────

    def set_consolidation_callback(self, callback: Callable) -> None:
        """Callback déclenché avant éviction heavy (flush mémoire)."""
        self._consolidation_callback = callback

    async def maybe_consolidate(self) -> bool:
        """Déclenche la consolidation mémoire si pression warning+.

        Returns:
            True si une consolidation a eu lieu
        """
        state = self.probe()
        if state.pressure_level in ("warning", "critical"):
            cb = self._consolidation_callback
            if cb is not None:
                logger.info(
                    f"🔄 RAM: pression {state.pressure_level} → consolidation mémoire"
                )
                try:
                    if asyncio.iscoroutinefunction(cb):
                        await cb()
                    else:
                        cb()
                except Exception as e:
                    logger.warning(f"⚠️ RAM: erreur consolidation: {e}")
                return True
        return False

    # ─── Utilitaires ─────────────────────────────────────────────────

    def summary(self) -> str:
        """Rapport textuel de l'état RAM."""
        state = self.probe(force=True)
        lines = [
            f"📊 RAM Budget Summary",
            f"   Process RSS : {state.process_rss_mb:.0f} MB",
            f"   Système libre : {state.free_ram_gb:.2f} Go / 8 Go",
            f"   Swap : {state.swap_used_gb:.1f} / {state.swap_total_gb:.0f} Go ({state.swap_percent:.0f}%)",
            f"   Budget NURU : {state.used_mb} MB / {self.hard_limit_gb*1024:.0f} MB (hard)",
            f"   Pression : {state.pressure_level}",
            f"   Composants chargés :",
        ]
        for c in state.slots:
            mark = "🔵" if c.loaded else "⚪"
            lines.append(
                f"     {mark} {c.name} ({c.estimated_mb} MB, "
                f"priorité {c.priority.name})"
            )
        return "\n".join(lines)
