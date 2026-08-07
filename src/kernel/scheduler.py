"""
NURU Kernel — Scheduler (Phase 3.10).

Ordonnanceur centralisé de toutes les tâches NURU.
Le kernel ne décide pas — il planifie.

Le Scheduler remplace les ensembles éparpillés de background tasks
(_bg_tasks dans NuruCore, orchestrator, etc.) par un point de contrôle
unique avec priorités, files, et conscience des ressources.

Priorités (7 niveaux) :
    CRITICAL  (0)   — réponse utilisateur, ne pas bloquer
    HIGH      (1)   — tâches interactives visibles
    NORMAL    (2)   — opérations normales (RAG, embedding)
    LOW       (3)   — consolidation mémoire, sleep cycle
    IDLE      (4)   — proactive, routine, watchdogs
    BACKGROUND(5)   — indexation, tâches longues
    MAINTENANCE(6)  — GC, nettoyage, purge

Usage :
    scheduler = KernelScheduler()
    
    # Tâche prioritaire (réponse utilisateur)
    task = await scheduler.schedule(
        generate_response(query),
        name="response",
        priority=TaskPriority.HIGH,
    )
    
    # Tâche de fond (indexation)
    task = await scheduler.schedule(
        index_document(path),
        name=f"index:{path.name}",
        priority=TaskPriority.BACKGROUND,
    )
    
    # Vérifier l'état
    status = scheduler.status          # "idle" | "running" | "full"
    running = scheduler.running_tasks  # dict[name -> TaskInfo]
    queue = scheduler.pending_tasks    # list[TaskInfo]
"""

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from threading import Lock
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ── Types ──────────────────────────────────────────────────────

class TaskPriority(IntEnum):
    """Priorité d'exécution. Plus le chiffre est bas, plus c'est prioritaire."""
    CRITICAL = 0      # Réponse utilisateur — exécuté immédiatement
    HIGH = 1          # Tâche interactive visible
    NORMAL = 2        # Opération normale (RAG, embedding)
    LOW = 3           # Consolidation mémoire, sleep cycle
    IDLE = 4          # Proactive, routine, watchdog
    BACKGROUND = 5    # Indexation, tâches longues
    MAINTENANCE = 6   # GC, nettoyage, purge


class TaskStatus(IntEnum):
    PENDING = 0
    RUNNING = 1
    COMPLETED = 2
    FAILED = 3
    CANCELLED = 4


@dataclass
class TaskInfo:
    """Métadonnées d'une tâche planifiée."""
    id: str
    name: str
    priority: TaskPriority
    status: TaskStatus
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    duration_s: Optional[float] = None
    error: Optional[str] = None
    coro_name: str = ""


# ── Scheduler ──────────────────────────────────────────────────

class KernelScheduler:
    """Ordonnanceur centralisé des tâches NURU.

    Files de priorité : les tâches de priorité plus élevée passent avant.
    Concurrence : max_concurrent tâches simultanées (défaut : 5).
    Resource-aware : avant de lancer une tâche, vérifie avec KernelResources
    que la RAM le permet.

    Usage :
        scheduler = KernelScheduler(max_concurrent=5)
        scheduler.start()  # Démarre la boucle d'exécution

        # Planifier
        task = await scheduler.schedule(
            mon_coroutine(),
            name="ma tâche",
            priority=TaskPriority.NORMAL,
        )

        # Attendre la fin
        result = await task
    """

    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent
        self._lock = Lock()
        # Files par priorité (deque par priorité)
        self._queues: dict[int, deque] = {
            p.value: deque() for p in TaskPriority
        }
        self._running: dict[str, asyncio.Task] = {}
        self._tasks: dict[str, TaskInfo] = {}
        self._completed: dict[str, TaskInfo] = {}  # Cache des N dernières
        self._max_completed = 50

        # Flag d'exécution
        self._running_flag = False
        self._pause_flag = False

        # KernelResources (résolu lazy)
        self._resources: Any = None

    @property
    def resources(self) -> Any:
        if self._resources is None:
            try:
                from src.kernel import NuruKernel
                kernel = NuruKernel()
                if kernel.has("resources"):
                    self._resources = kernel.get("resources")
            except Exception:
                pass
        return self._resources

    # ── Planification ──────────────────────────────────────────

    async def schedule(
        self,
        coro: Any,
        name: str = "",
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> asyncio.Task:
        """Planifie une coroutine pour exécution.

        Toutes les tâches passent par la file de priorité.
        La tâche s'exécute quand c'est son tour (priorité + concurrence).

        Args:
            coro : Coroutine à exécuter
            name : Nom lisible (logs + déduplication)
            priority : Priorité d'exécution

        Returns:
            asyncio.Task  prêt à attendre avec await
        """
        task_id = uuid.uuid4().hex[:12]
        coro_name = getattr(coro, "__name__", str(type(coro)))

        info = TaskInfo(
            id=task_id,
            name=name or coro_name,
            priority=priority,
            status=TaskStatus.PENDING,
            created_at=time.time(),
            coro_name=coro_name,
        )

        with self._lock:
            self._tasks[task_id] = info
            self._queues[priority.value].append(task_id)

        async def _run():
            info.status = TaskStatus.PENDING
            # Attendre son tour
            await self._wait_for_turn(task_id, info)
            if info.status == TaskStatus.CANCELLED:
                return None

            # Exécuter
            info.status = TaskStatus.RUNNING
            info.started_at = time.time()
            try:
                result = await coro
                info.status = TaskStatus.COMPLETED
                info.completed_at = time.time()
                info.duration_s = info.completed_at - info.started_at
                logger.debug("✅ Scheduler: %s terminé (%.2fs)", info.name, info.duration_s)
                return result
            except asyncio.CancelledError:
                info.status = TaskStatus.CANCELLED
                logger.debug("⏹️ Scheduler: %s annulé", info.name)
                raise
            except Exception as e:
                info.status = TaskStatus.FAILED
                info.error = str(e)
                info.completed_at = time.time()
                info.duration_s = info.completed_at - (info.started_at or info.completed_at)
                logger.warning("❌ Scheduler: %s échec: %s", info.name, e)
                return None
            finally:
                self._cleanup(task_id, info)

        task = asyncio.create_task(_run(), name=name or coro_name)
        with self._lock:
            self._running[task_id] = task

        logger.info(
            "📋 Scheduler: %s [%s] priorité=%s (file=%d, running=%d)",
            info.name, task_id[:8], priority.name,
            self.queue_length, len(self._running),
        )
        return task

    async def _wait_for_turn(self, task_id: str, info: TaskInfo) -> None:
        """Attend que la tâche soit éligible pour s'exécuter.

        Conditions :
        1. La tâche est en tête de sa file de priorité
        2. Le nombre de tâches concurrentes < max_concurrent
        3. Les ressources le permettent (RAM)
        """
        while self._running_flag:
            with self._lock:
                if info.status == TaskStatus.CANCELLED:
                    return

                # Est-ce notre tour ?
                queue = self._queues[info.priority.value]
                if not queue or queue[0] != task_id:
                    await asyncio.sleep(0.1)
                    continue

                # Concurrence OK ?
                actual_running = sum(
                    1 for t in self._running.values()
                    if not t.done()
                )
                if actual_running >= self.max_concurrent:
                    await asyncio.sleep(0.2)
                    continue

                # Ressources OK ?
                if self.resources is not None and not self.resources.can_load("scheduler_task"):
                    await asyncio.sleep(0.5)
                    continue

                # On peut lancer — retirer de la file
                queue.popleft()
                return

            await asyncio.sleep(0.1)

    def _cleanup(self, task_id: str, info: TaskInfo) -> None:
        """Nettoie après exécution d'une tâche."""
        with self._lock:
            self._running.pop(task_id, None)
            self._completed[task_id] = info
            if len(self._completed) > self._max_completed:
                oldest = min(
                    self._completed.keys(),
                    key=lambda k: self._completed[k].completed_at or 0,
                )
                del self._completed[oldest]
            self._tasks.pop(task_id, None)

    # ── Boucle d'exécution ─────────────────────────────────────

    def start(self) -> None:
        """Démarre le scheduler (active le flag d'exécution)."""
        if self._running_flag:
            return
        self._running_flag = True
        self._pause_flag = False
        logger.info("▶️ Scheduler: démarré")

    def pause(self) -> None:
        """Met en pause l'exécution de nouvelles tâches."""
        self._pause_flag = True
        logger.info("⏸️ Scheduler: en pause")

    def resume(self) -> None:
        """Reprend l'exécution."""
        self._pause_flag = False
        logger.info("▶️ Scheduler: repris")

    def stop(self) -> None:
        """Arrête le scheduler et annule toutes les tâches en cours.

        Les tâches en file d'attente sont annulées.
        Les tâches en cours d'exécution reçoivent CancelledError.
        """
        self._running_flag = False

        # Annuler les tâches en file d'attente
        with self._lock:
            for priority in self._queues:
                while self._queues[priority]:
                    tid = self._queues[priority].popleft()
                    info = self._tasks.get(tid)
                    if info:
                        info.status = TaskStatus.CANCELLED
                        self._cleanup(tid, info)

            # Annuler les tâches en cours
            for task_id, task in list(self._running.items()):
                if not task.done():
                    task.cancel()
                info = self._tasks.get(task_id)
                if info:
                    info.status = TaskStatus.CANCELLED
                    self._cleanup(task_id, info)

        logger.info(
            "⏹️ Scheduler arrêté (%d tasks restantes)",
            len(self._running),
        )

    def cancel(self, task_id: str) -> bool:
        """Annule une tâche par son ID.

        Returns:
            True si la tâche a été annulée, False si introuvable.
        """
        # Vérifier les tâches en cours
        task = self._running.get(task_id)
        if task is not None and not task.done():
            task.cancel()
            info = self._tasks.get(task_id)
            if info:
                info.status = TaskStatus.CANCELLED
                self._cleanup(task_id, info)
            logger.info("⏹️ Scheduler: tâche %s annulée", task_id[:8])
            return True

        # Vérifier les files d'attente
        for priority in self._queues:
            new_queue = deque()
            found = False
            while self._queues[priority]:
                tid = self._queues[priority].popleft()
                if tid == task_id:
                    info = self._tasks.get(tid)
                    if info:
                        info.status = TaskStatus.CANCELLED
                        self._cleanup(tid, info)
                    found = True
                else:
                    new_queue.append(tid)
            self._queues[priority] = new_queue
            if found:
                logger.info("⏹️ Scheduler: tâche %s retirée de la file", task_id[:8])
                return True

        return False

    # ── Status ─────────────────────────────────────────────────

    @property
    def running_tasks(self) -> dict[str, TaskInfo]:
        """Tâches en cours d'exécution."""
        result = {}
        with self._lock:
            for task_id, info in self._tasks.items():
                if info.status == TaskStatus.RUNNING:
                    result[task_id] = info
        return result

    @property
    def pending_tasks(self) -> list[TaskInfo]:
        """Tâches en file d'attente (ordonnées par priorité)."""
        result = []
        with self._lock:
            for priority in sorted(self._queues.keys()):
                for tid in self._queues[priority]:
                    info = self._tasks.get(tid)
                    if info:
                        result.append(info)
        return result

    @property
    def status(self) -> str:
        """État général du scheduler."""
        running = len(self._running)
        pending = sum(len(q) for q in self._queues.values())
        if running >= self.max_concurrent:
            return "full"
        if running > 0:
            return "running"
        if pending > 0:
            return "pending"
        return "idle"

    @property
    def queue_length(self) -> int:
        """Nombre de tâches en attente."""
        return sum(len(q) for q in self._queues.values())

    def snapshot(self) -> dict:
        """État complet pour monitoring/debug."""
        return {
            "status": self.status,
            "running": len(self._running),
            "pending": self.queue_length,
            "max_concurrent": self.max_concurrent,
            "paused": self._pause_flag,
            "total_completed": len(self._completed),
        }

    def __repr__(self) -> str:
        return f"<KernelScheduler running={len(self._running)} pending={self.queue_length}>"
