"""Routines et Presets — Actions proactives programmables.

Routines : séquences d'actions récurrentes (réveil, travail, soirée).
Presets : configurations prédéfinies de comportement proactif.
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class RoutineTrigger(enum.Enum):
    """Déclencheur de routine."""
    TIME = "time"               # Heure fixe
    DAY_OF_WEEK = "day_of_week"  # Jour de la semaine
    IDLE = "idle"               # Après inactivité
    STARTUP = "startup"         # Au démarrage de NURU
    SHUTDOWN = "shutdown"       # À l'arrêt
    MANUAL = "manual"           # Déclenché manuellement


@dataclass
class RoutineStep:
    """Étape d'une routine."""
    action: str                  # Description de l'action
    type: str                    # "command", "suggest", "remind"
    payload: dict = field(default_factory=dict)
    delay_seconds: int = 0       # Délai avant exécution


@dataclass
class Routine:
    """Routine programmable."""
    id: str
    name: str
    description: str
    trigger: RoutineTrigger
    steps: list[RoutineStep] = field(default_factory=list)
    active: bool = True
    schedule: str = ""            # e.g., "08:00" ou "mon-fri"
    created_at: float = 0.0

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()

    @classmethod
    def morning_routine(cls) -> Routine:
        """Routine matinale par défaut."""
        return cls(
            id="morning",
            name="Routine matinale",
            description="Préparation de la journée : météo, agenda, rappels",
            trigger=RoutineTrigger.TIME,
            schedule="08:00",
            steps=[
                RoutineStep("Résumé de la météo", "suggest"),
                RoutineStep("Aperçu de l'agenda du jour", "suggest"),
                RoutineStep("Rappels intelligents", "remind"),
            ],
        )

    @classmethod
    def evening_routine(cls) -> Routine:
        """Routine du soir par défaut."""
        return cls(
            id="evening",
            name="Routine du soir",
            description="Bilan de la journée et préparation du lendemain",
            trigger=RoutineTrigger.TIME,
            schedule="21:00",
            steps=[
                RoutineStep("Résumé de la journée", "suggest"),
                RoutineStep("Rappel des tâches en cours", "remind"),
                RoutineStep("Suggestion de consolidation mémoire", "suggest"),
            ],
        )


@dataclass
class RoutinePreset:
    """Preset de routines."""
    name: str
    description: str
    routines: list[Routine] = field(default_factory=list)

    @classmethod
    def default(cls) -> RoutinePreset:
        return cls(
            name="default",
            description="Routines par défaut",
            routines=[Routine.morning_routine(), Routine.evening_routine()],
        )

    @classmethod
    def work_focused(cls) -> RoutinePreset:
        return cls(
            name="work_focused",
            description="Routines orientées travail",
            routines=[
                Routine.morning_routine(),
                Routine.evening_routine(),
                Routine(
                    id="work_start",
                    name="Début de travail",
                    description="Focus : tâches prioritaires",
                    trigger=RoutineTrigger.TIME,
                    schedule="09:00",
                    steps=[
                        RoutineStep("Rappel des objectifs du jour", "remind"),
                        RoutineStep("Ouverture des outils de travail", "suggest"),
                    ],
                ),
                Routine(
                    id="lunch_break",
                    name="Pause déjeuner",
                    description="Rappel de pause",
                    trigger=RoutineTrigger.TIME,
                    schedule="12:30",
                    steps=[
                        RoutineStep("Pause déjeuner : déconnexion recommandée", "suggest"),
                    ],
                ),
            ],
        )


@dataclass
class RoutineScheduler:
    """Planificateur de routines.

    Usage :
        scheduler = RoutineScheduler()
        scheduler.add_routine(Routine.morning_routine())
        due = scheduler.check_due()  # Routines à déclencher maintenant
    """

    routines: dict[str, Routine] = field(default_factory=dict)
    last_triggered: dict[str, float] = field(default_factory=dict)

    def add_routine(self, routine: Routine) -> None:
        self.routines[routine.id] = routine
        logger.info(f"Routine ajoutée: {routine.name}")

    def remove_routine(self, routine_id: str) -> None:
        self.routines.pop(routine_id, None)

    def activate(self, routine_id: str, active: bool = True) -> None:
        if routine_id in self.routines:
            self.routines[routine_id].active = active

    def check_due(self, current_time: Optional[float] = None) -> list[Routine]:
        """Vérifie les routines à déclencher maintenant.

        Args:
            current_time: Timestamp (default: now)

        Returns:
            Routines dont le déclencheur correspond
        """
        now = current_time or time.time()
        due: list[Routine] = []
        from datetime import datetime

        current_hour = datetime.fromtimestamp(now).strftime("%H:%M")

        for routine in self.routines.values():
            if not routine.active:
                continue

            if routine.trigger == RoutineTrigger.TIME or routine.trigger == RoutineTrigger.STARTUP:
                if routine.schedule and routine.schedule == current_hour:
                    last = self.last_triggered.get(routine.id, 0)
                    if now - last > 300:  # Pas 2x dans les 5 min
                        due.append(routine)
                        self.last_triggered[routine.id] = now

        return due

    def get_due_now(self, current_time: Optional[float] = None) -> list[Routine]:
        """Même chose que check_due mais nommé pour clarté."""
        return self.check_due(current_time)

    def load_preset(self, preset: RoutinePreset) -> None:
        """Charge tous les routines d'un preset."""
        for routine in preset.routines:
            self.add_routine(routine)

    def get_active(self) -> list[Routine]:
        return [r for r in self.routines.values() if r.active]

    def to_dict(self) -> list[dict]:
        return [{
            "id": r.id,
            "name": r.name,
            "schedule": r.schedule,
            "active": r.active,
            "n_steps": len(r.steps),
        } for r in self.routines.values()]
