"""NURU Model Router — Phase 4.

Router intelligent de modèles LLM avec CostGuard intégré.
Optimise le rapport coût/rapidité/précision selon la tâche.
"""

from .router import ModelRouter, ModelRoute, RoutingDecision
from .cost_guard import CostGuard, CostConfig, UsageRecord

__all__ = [
    "ModelRouter", "ModelRoute", "RoutingDecision",
    "CostGuard", "CostConfig", "UsageRecord",
]
