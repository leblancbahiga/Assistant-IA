"""
NURU Kernel — Resources.

Wrapper formel autour de RAMBudgetManager (core/ram_budget.py).
Le kernel "sait" où est la RAM, ce qui est chargé, ce qui peut être déchargé.

Contrairement au singleton global ``get_budget()``, KernelResources est
enregistré dans le kernel et accessible via ``kernel.resources``.
Tout module qui a besoin de vérifier la RAM demande au kernel, pas à un import.

Usage:
    resources = KernelResources()
    resources.register_component("embedder", Priority.EMBEDDER, estimated_mb=450)
    if resources.can_load("embedder"):
        resources.mark_loaded("embedder", model_instance)

    pressure = resources.get_pressure()  # "normal" | "warning" | "critical"
    if kernel.metrics is not None:
        kernel.metrics.snapshot().update(resources.probe().__dict__)
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class KernelResources:
    """Gestionnaire de ressources système (RAM, modèle, cache).

    Délègue à RAMBudgetManager pour les politiques M1 8 Go.
    Seule différence avec l'appel direct à get_budget() : ce service
    est enregistré dans le kernel, donc :
    - kernel.resources est le point d'accès unique
    - aucune importation directe de core/ram_budget.py ailleurs
    - RAMBudgetManager peut être remplacé sans changer les appelants

    Cycle de vie : enregistré tôt dans NuruCore.__init__, appelé par
    kernel.boot() via start().
    """

    def __init__(self) -> None:
        self._budget: Any = None  # RAMBudgetManager, lazy
        self._budget_available: bool = True

    @property
    def budget(self) -> Any:
        """Accès direct à RAMBudgetManager (rétrocompatibilité).

        Initialisé lazy au premier accès pour éviter les imports
        circulaires au module level.
        """
        if self._budget is None:
            try:
                from src.core.ram_budget import get_budget, Priority
                self._budget = get_budget()
                # Exposer Priority pour les modules qui enregistrent des composants
                self.Priority = Priority
            except Exception as e:
                self._budget_available = False
                logger.error("❌ KernelResources: RAMBudgetManager non disponible: %s", e)
                self._budget = _NullBudget()
        return self._budget

    # ── Délégation directe ──────────────────────────────────────

    def probe(self, force: bool = False) -> Any:
        """État RAM instantané (délègue à RAMBudgetManager.probe())."""
        return self.budget.probe(force=force)

    def get_pressure(self) -> str:
        """Niveau de pression : normal | warning | critical."""
        return self.budget.get_pressure()

    def can_load(self, name: str) -> bool:
        """Vérifie si le chargement est possible sans dépasser le budget."""
        return self.budget.can_load(name)

    def mark_loaded(self, name: str, model: Any = None) -> None:
        """Marque un composant comme chargé."""
        self.budget.mark_loaded(name, model=model)

    def mark_unloaded(self, name: str) -> None:
        """Marque un composant comme déchargé."""
        self.budget.mark_unloaded(name)

    def evict(self, priority_below: Any = None) -> list[str]:
        """Décharge les composants de priorité >= threshold."""
        if priority_below is None:
            try:
                priority_below = self.budget.Priority.CACHE
            except Exception:
                priority_below = 4
        return self.budget.evict(priority_below=priority_below)

    def evict_one(self, exclude: Optional[set[str]] = None) -> Optional[str]:
        """Décharge un seul composant de plus basse priorité."""
        return self.budget.evict_one(exclude=exclude)

    def register_component(self, name: str, priority: Any, estimated_mb: int) -> None:
        """Enregistre un composant avec son budget RAM."""
        self.budget.register_component(name, priority, estimated_mb=estimated_mb)

    def register_callback(self, callback: Any) -> None:
        """Enregistre une fonction appelée lors d'une pression mémoire."""
        self.budget.register_callback(callback)

    def should_force_cloud(self) -> bool:
        """True si RAM < 1 Go ou swap > 80%."""
        return self.budget.should_force_cloud()

    def force_gc(self) -> None:
        """GC + cache MLX."""
        self.budget.force_gc()

    def summary(self) -> str:
        """Rapport textuel."""
        return self.budget.summary()

    def snapshot_budget(self) -> dict:
        """Snapshot de l'état budget pour monitoring."""
        state = self.probe()
        return {
            "free_ram_gb": round(state.free_ram_gb, 2),
            "swap_percent": round(state.swap_percent, 1),
            "pressure": state.pressure_level,
            "rss_mb": round(state.process_rss_mb, 0),
            "used_budget_mb": state.used_mb,
            "hard_limit_gb": state.hard_limit_gb,
        }

    # ── Cycle de vie kernel ─────────────────────────────────────

    def start(self) -> None:
        """Démarre le monitoring RAM périodique."""
        budget = self.budget
        budget.start_monitoring()
        logger.info("▶️ KernelResources: monitoring activé")

    def stop(self) -> None:
        """Arrête le monitoring RAM."""
        self._budget.stop_monitoring()
        logger.info("⏹️ KernelResources: monitoring arrêté")

    def __repr__(self) -> str:
        try:
            p = self.get_pressure()
            return f"<KernelResources pressure={p}>"
        except Exception:
            return "<KernelResources (unavailable)>"


class _NullBudget:
    """Budget null — utilisé quand RAMBudgetManager n'est pas disponible.

    Permet à KernelResources de ne pas planter même si l'import
    de psutil ou ram_budget échoue (environnement sans dépendances).
    """

    def __getattr__(self, name):
        return self._noop

    def _noop(self, *args, **kwargs):
        return None

    def get_pressure(self):
        return "unknown"

    def probe(self, *args, **kwargs):
        from types import SimpleNamespace
        return SimpleNamespace(
            free_ram_gb=0.0, swap_percent=0.0, pressure_level="unknown",
            process_rss_mb=0.0, used_mb=0, hard_limit_gb=6.0,
        )

    def should_force_cloud(self):
        return False

    def can_load(self, name):
        return True

    def summary(self):
        return "RAMBudgetManager non disponible"
