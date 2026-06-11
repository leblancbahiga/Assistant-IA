"""
NURU V10 Sprint 5 — Reasoning Modules.

Exporte :
  - ReflexionEngine  : boucle d'auto-critique (max 2 passes)
  - SelfConsistency  : vote majoritaire sur N réponses
  - ConfidenceCalibrator : calibrage du score de confiance
"""

from .reflexion import ReflexionEngine, ReflexionResult
from .consistency import SelfConsistency, ConsistencyResult
from .confidence import ConfidenceCalibrator, CalibratedResult

__all__ = [
    "ReflexionEngine",
    "ReflexionResult",
    "SelfConsistency",
    "ConsistencyResult",
    "ConfidenceCalibrator",
    "CalibratedResult",
]
