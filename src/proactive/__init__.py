"""NURU ProactiveEngine — Phase 3.

Moteur de proactivité : signaux contextuels, évaluation LLM,
planification d'actions non sollicitées, routines et presets.
"""

from .engine import ProactiveEngine, Signal, SignalPriority, Action, ActionPlan
from .routines import Routine, RoutineScheduler, RoutinePreset
from .learning import ContextualLearner

__all__ = [
    "ProactiveEngine", "Signal", "SignalPriority", "Action", "ActionPlan",
    "Routine", "RoutineScheduler", "RoutinePreset",
    "ContextualLearner",
]
