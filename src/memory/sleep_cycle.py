"""SleepCycleManager — Gestionnaire de cycles de sommeil NURU.

Phases : light sleep (consolidation mémoire), deep sleep (nettoyage),
REM (synthèse créative). Effet de bord minimal sur la RAM.
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class SleepPhase(enum.Enum):
    """Phase de sommeil de NURU."""
    AWAKE = "awake"
    LIGHT = "light_sleep"     # Consolidation mémoire légère
    DEEP = "deep_sleep"       # Nettoyage, optimisation
    REM = "rem"               # Synthèse, création de liens


@dataclass
class SleepConfig:
    """Configuration du cycle de sommeil."""
    auto_sleep_enabled: bool = True
    idle_timeout_minutes: int = 15    # → light
    light_duration_minutes: int = 3   # → deep ou REM
    deep_duration_minutes: int = 2
    rem_duration_minutes: int = 1
    wake_check_interval_sec: int = 30 # Vérification activité utilisateur


@dataclass
class SleepCycleManager:
    """Gestionnaire de cycles de sommeil.

    Usage :
        sleep = SleepCycleManager()
        sleep.start_monitoring()
        # ... plus tard
        phase = sleep.current_phase
        if phase == SleepPhase.DEEP:
            await cleanup_tasks()
        sleep.user_activity_detected()  # Réveil immédiat
    """

    config: SleepConfig = field(default_factory=SleepConfig)

    def __init__(self, config: Optional[SleepConfig] = None):
        self.config = config or SleepConfig()
        self._phase = SleepPhase.AWAKE
        self._last_activity: float = time.time()
        self._phase_start: float = time.time()
        self._running = False
        self._on_phase_change: Optional[Callable[[SleepPhase], None]] = None

    def start_monitoring(self) -> None:
        """Démarre la surveillance d'inactivité."""
        self._running = True
        self._last_activity = time.time()
        logger.info("Sleep cycle monitoring started")

    def stop_monitoring(self) -> None:
        """Arrête la surveillance."""
        self._running = False
        self._phase = SleepPhase.AWAKE
        logger.info("Sleep cycle monitoring stopped")

    def user_activity_detected(self) -> None:
        """Signal d'activité utilisateur → réveil immédiat."""
        self._last_activity = time.time()
        if self._phase != SleepPhase.AWAKE:
            self._set_phase(SleepPhase.AWAKE)

    def tick(self) -> SleepPhase:
        """Met à jour l'état du cycle (appelé périodiquement).

        Returns:
            Phase actuelle après mise à jour
        """
        if not self._running:
            return SleepPhase.AWAKE

        now = time.time()
        idle_seconds = now - self._last_activity

        if self._phase == SleepPhase.AWAKE:
            if idle_seconds >= self.config.idle_timeout_minutes * 60:
                self._set_phase(SleepPhase.LIGHT)

        elif self._phase == SleepPhase.LIGHT:
            phase_elapsed = now - self._phase_start
            if phase_elapsed >= self.config.light_duration_minutes * 60:
                # → deep sleep (ou détection d'activité)
                if idle_seconds >= self.config.idle_timeout_minutes * 60:
                    self._set_phase(SleepPhase.DEEP)
                else:
                    self._set_phase(SleepPhase.AWAKE)

        elif self._phase == SleepPhase.DEEP:
            phase_elapsed = now - self._phase_start
            if phase_elapsed >= self.config.deep_duration_minutes * 60:
                self._set_phase(SleepPhase.REM)

        elif self._phase == SleepPhase.REM:
            phase_elapsed = now - self._phase_start
            if phase_elapsed >= self.config.rem_duration_minutes * 60:
                # Retour à lumière ou réveil
                if idle_seconds >= self.config.idle_timeout_minutes * 60:
                    self._set_phase(SleepPhase.LIGHT)
                else:
                    self._set_phase(SleepPhase.AWAKE)

        return self._phase

    def _set_phase(self, phase: SleepPhase) -> None:
        old = self._phase
        self._phase = phase
        self._phase_start = time.time()
        logger.info(f"💤 Cycle sommeil: {old.value} → {phase.value}")
        if self._on_phase_change:
            self._on_phase_change(phase)

    @property
    def current_phase(self) -> SleepPhase:
        return self._phase

    @property
    def phase_duration_seconds(self) -> float:
        """Durée de la phase actuelle en secondes."""
        return time.time() - self._phase_start

    def set_on_phase_change(self, callback: Callable[[SleepPhase], None]) -> None:
        self._on_phase_change = callback

    def to_dict(self) -> dict:
        return {
            "phase": self._phase.value,
            "phase_duration_s": self.phase_duration_seconds,
            "idle_s": time.time() - self._last_activity,
            "running": self._running,
        }
