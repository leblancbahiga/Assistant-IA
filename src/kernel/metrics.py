"""
NURU Kernel — Metrics (Resource Monitor).

Probe périodique de l'état machine pour que le kernel "sache" en temps réel :
- RAM libre, swap, RSS du processus
- CPU (charge moyenne)
- Nombre de threads du processus
- Nombre de QObjects Qt (si PySide6 chargé)
- Timers actifs Qt (si PySide6 chargé)

Usage:
    metrics = KernelMetrics()
    metrics.start()        # lance la boucle (1s / 5s selon contexte)
    state = metrics.snapshot()  # dict des métriques actuelles
    await metrics.stop()   # arrête la boucle
"""

import asyncio
import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class KernelMetrics:
    """Collecteur de métriques système pour le kernel NURU.

    Boucle périodique légère (5s par défaut, 1s pendant génération).
    Thread-safe : snapshot() est une copie atomique des valeurs.

    Ne fait pas de monitoring RAM — ça c'est le travail de RAMBudgetManager.
    KernelMetrics se concentre sur CE QUI EST CHARGE, PAS SUR CE QUI EST LIBRE :
    - threads, workers, timers, QObjects, uptime
    - délégation à RAMBudgetManager si disponible pour RAM/swap
    """

    def __init__(self) -> None:
        self._loop_interval: float = 5.0
        self._monitoring: bool = False
        self._task: Optional[asyncio.Task] = None

        # Dernières valeurs collectées (écrites par _collect, lues par snapshot)
        self._data: dict[str, Any] = {
            "uptime_seconds": 0.0,
            "process_rss_mb": 0.0,
            "thread_count": 0,
            "cpu_percent": 0.0,
            "qobject_count": None,
            "timer_count": None,
            "memory_free_gb": None,
            "swap_percent": None,
            "pressure": "unknown",
        }
        self._started_at: float = 0.0
        self._process: Any = None  # psutil.Process, lazy
        self._psutil_available: bool = True

    def _init_process(self) -> None:
        """Init lazy psutil.Process (évite import au module level)."""
        if self._process is not None:
            return
        try:
            import psutil
            self._process = psutil.Process()
            # Probe initiale pour valider
            self._process.memory_info()
            self._process.cpu_percent()  # premier appel = 0, deuxième = réel
            logger.debug("📊 KernelMetrics: psutil OK, PID=%d", os.getpid())
        except Exception as e:
            self._psutil_available = False
            logger.warning("⚠️ KernelMetrics: psutil indisponible (%s)", e)

    # ── Collecte ────────────────────────────────────────────────

    def collect(self) -> dict[str, Any]:
        """Mesure unique (synchrone, rapide — < 10ms).

        Returns:
            Dict complet des métriques actuelles.
        """
        self._init_process()
        now = time.time()
        uptime = now - self._started_at if self._started_at > 0 else 0.0

        data: dict[str, Any] = {
            "uptime_seconds": round(uptime, 1),
        }

        if self._psutil_available and self._process is not None:
            try:
                # RSS
                mem = self._process.memory_info()
                data["process_rss_mb"] = round(mem.rss / (1024 * 1024), 1)

                # Threads
                data["thread_count"] = self._process.num_threads()

                # CPU (moyenne sur l'intervalle depuis la dernière mesure)
                cpu = self._process.cpu_percent()
                data["cpu_percent"] = round(cpu, 1)

            except Exception as e:
                logger.debug("⚠️ KernelMetrics: erreur probe process: %s", e)
                data["process_rss_mb"] = 0.0
                data["thread_count"] = 0
                data["cpu_percent"] = 0.0

            # RAM système via psutil
            try:
                import psutil
                vm = psutil.virtual_memory()
                data["memory_free_gb"] = round(vm.available / (1024**3), 2)
                sw = psutil.swap_memory()
                data["swap_percent"] = round(sw.percent, 1)
                # Pression estimée
                pct = vm.available / vm.total * 100
                if pct < 10 or sw.percent > 80:
                    data["pressure"] = "critical"
                elif pct < 20 or sw.percent > 50:
                    data["pressure"] = "warning"
                else:
                    data["pressure"] = "normal"
            except Exception:
                data["memory_free_gb"] = None
                data["swap_percent"] = None
                data["pressure"] = "unknown"

        # Métriques Qt (PySide6) — optionnelles, pas d'échec si pas chargé
        data["qobject_count"] = self._count_qobjects()
        data["timer_count"] = self._count_timers()

        # Mettre en cache
        self._data = dict(data)
        return data

    # ── Métriques Qt ────────────────────────────────────────────

    @staticmethod
    def _count_qobjects() -> Optional[int]:
        """Compte les QObjects actifs (ou None si PySide6 non chargé)."""
        try:
            from PySide6 import QtCore
            return len(QtCore.QObjectList())
        except Exception:
            return None

    @staticmethod
    def _count_timers() -> Optional[int]:
        """Compte les timers Qt actifs (ou None si PySide6 non chargé)."""
        try:
            from PySide6 import QtCore
            timers = [o for o in QtCore.QObjectList()
                      if isinstance(o, QtCore.QTimer) and o.isActive()]
            return len(timers)
        except Exception:
            return None

    # ── Boucle périodique ───────────────────────────────────────

    def set_fast_mode(self, active: bool) -> None:
        """Passe en mode rapide (1s au lieu de 5s) pendant la génération.

        À appeler depuis NuruCore.set_generating().
        """
        self._loop_interval = 1.0 if active else 5.0

    def start(self) -> None:
        """Lance la boucle périodique de collecte."""
        if self._monitoring:
            return
        self._monitoring = True
        self._started_at = time.time()
        self._init_process()
        logger.info("📊 KernelMetrics: monitoring toutes les %.0fs", self._loop_interval)

        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._run())
        except RuntimeError:
            logger.warning("⚠️ KernelMetrics: pas de boucle asyncio, monitoring différé")

    def stop(self) -> None:
        """Arrête la boucle périodique."""
        self._monitoring = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
        logger.info("🛑 KernelMetrics arrêté")
        self._started_at = 0.0

    async def _run(self) -> None:
        """Boucle interne.

        V17 P0-C : émettre les métriques collectées via EventBus
        pour que Dashboard et RightInspector puissent s'abonner.
        """
        while self._monitoring:
            self.collect()

            # V17 P0-C : émettre les métriques pour les abonnés
            try:
                from src.kernel import NuruKernel
                eb = NuruKernel().get("event_bus")
                if eb is not None:
                    eb.emit_sync("metrics.collected", dict(self._data))
            except Exception:
                pass

            await asyncio.sleep(self._loop_interval)

    # ── Snapshot ────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        """Retourne les dernières métriques collectées (thread-safe)."""
        return dict(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __repr__(self) -> str:
        rss = self._data.get("process_rss_mb", 0)
        cpu = self._data.get("cpu_percent", 0)
        return f"<KernelMetrics rss={rss}MB cpu={cpu}%>"
