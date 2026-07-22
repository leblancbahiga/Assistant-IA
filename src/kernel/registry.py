"""NURU Kernel — ServiceRegistry.

Registre central de tous les services NURU.
Plus aucun import direct entre modules — tout passe par kernel.get().

Principes :
  1. Les services sont enregistrés par nom au démarrage
  2. Les factories permettent l'initialisation lazy (LLM, embedder)
  3. Le cycle de vie (start/stop) est centralisé
  4. L'accès est thread-safe via un lock
"""

import asyncio
import logging
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ServiceRegistry:
    """Registre central des services NURU.

    Tous les composants sont enregistrés ici et accessibles via get().
    Remplace les ``from src.x import Y`` directs entre modules.
    """

    def __init__(self):
        self._services: dict[str, Any] = {}
        self._factories: dict[str, Callable[[], Any]] = {}
        self._started: set[str] = set()
        self._lock = threading.RLock()

    # ── Enregistrement ────────────────────────────────────────

    def register(self, name: str, service: Any, *, replace: bool = False) -> None:
        """Enregistre une instance de service."""
        with self._lock:
            if name in self._services and not replace:
                raise ValueError(f"Service '{name}' déjà enregistré")
            self._services[name] = service
            logger.debug("📦 Service enregistré: %s", name)

    def register_factory(
        self, name: str, factory: Callable[[], Any], *, replace: bool = False
    ) -> None:
        """Enregistre une factory pour création lazy au premier get()."""
        with self._lock:
            if name in self._factories and not replace:
                raise ValueError(f"Factory '{name}' déjà enregistrée")
            self._factories[name] = factory
            logger.debug("🏭 Factory enregistrée: %s", name)

    def unregister(self, name: str) -> None:
        """Supprime un service ou une factory."""
        with self._lock:
            self._services.pop(name, None)
            self._factories.pop(name, None)
            self._started.discard(name)

    # ── Accès ─────────────────────────────────────────────────

    def get(self, name: str) -> Any:
        """Récupère un service par son nom.

        Si le service est une factory, l'instancie au premier appel.
        """
        with self._lock:
            # Déjà instancié
            if name in self._services:
                return self._services[name]
            # Factory → instancier
            if name in self._factories:
                factory = self._factories.pop(name)
                try:
                    service = factory()
                    self._services[name] = service
                    logger.info("🏗️ Service instancié via factory: %s", name)
                    return service
                except Exception as e:
                    logger.error("❌ Échec instanciation service '%s': %s", name, e)
                    raise
            raise KeyError(f"Service '{name}' non trouvé dans le registre")

    def get_or_none(self, name: str) -> Any:
        """Récupère un service ou None s'il n'existe pas."""
        try:
            return self.get(name)
        except KeyError:
            return None

    def has(self, name: str) -> bool:
        """Vérifie si un service est enregistré (instance ou factory)."""
        with self._lock:
            return name in self._services or name in self._factories

    # ── Énumération ───────────────────────────────────────────

    @property
    def names(self) -> list[str]:
        """Liste tous les noms de services enregistrés."""
        with self._lock:
            return list(self._services.keys()) + [
                f"{k} (lazy)" for k in self._factories.keys()
            ]

    # ── Cycle de vie ──────────────────────────────────────────

    def start(self, name: str) -> None:
        """Démarre un service s'il a une méthode start() ou async start()."""
        service = self.get(name)
        if not hasattr(service, "start"):
            return

        start_fn = service.start
        if asyncio.iscoroutinefunction(start_fn):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(start_fn())
                else:
                    asyncio.run(start_fn())
            except RuntimeError:
                logger.warning("⚠️ Pas de loop pour démarrer %s", name)
                return
        else:
            start_fn()

        self._started.add(name)
        logger.info("▶️ Service démarré: %s", name)

    def start_all(self) -> None:
        """Démarre tous les services enregistrés."""
        with self._lock:
            for name in list(self._services.keys()):
                if name not in self._started:
                    self.start(name)

    def stop(self, name: str) -> None:
        """Arrête un service s'il a une méthode stop()."""
        service = self._services.get(name)
        if service is None:
            return
        if not hasattr(service, "stop"):
            self._started.discard(name)
            return

        stop_fn = service.stop
        if asyncio.iscoroutinefunction(stop_fn):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(stop_fn())
                else:
                    asyncio.run(stop_fn())
            except RuntimeError:
                logger.warning("⚠️ Pas de loop pour arrêter %s", name)
        else:
            stop_fn()

        self._started.discard(name)
        logger.info("⏹️ Service arrêté: %s", name)

    def stop_all(self) -> None:
        """Arrête tous les services."""
        with self._lock:
            for name in list(self._services.keys()):
                self.stop(name)

    # ── Utilitaires ───────────────────────────────────────────

    def snapshot(self) -> dict[str, str]:
        """État actuel du registre (pour debug/monitoring)."""
        with self._lock:
            result: dict[str, str] = {}
            for name in self._services:
                svc = self._services[name]
                status = "started" if name in self._started else "registered"
                result[name] = f"{type(svc).__name__} [{status}]"
            for name in self._factories:
                result[name] = f"factory (lazy)"
            return result

    def __contains__(self, name: str) -> bool:
        return self.has(name)

    def __len__(self) -> int:
        with self._lock:
            return len(self._services) + len(self._factories)
