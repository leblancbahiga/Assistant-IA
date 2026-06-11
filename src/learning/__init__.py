"""
NURU V6/V9 — Learning Loop.

Collecte les traces d'interaction, analyse les patterns d'échec,
recueille le feedback utilisateur, et mesure les performances système.

Modules :
- TraceCollector    : enregistrement des traces d'interaction (V6)
- MiningWorker      : analyse des patterns d'échec (V6)
- FeedbackCollector : collecte structurée du feedback utilisateur (V9)
- PerformanceTracker: mesure continue des performances (V9)
- StrategyOptimizer : ajustement automatique des paramètres système (V9)
- SelfEvaluator     : évaluation de qualité des réponses sans référence (V9)
"""

from src.learning.feedback import FeedbackCollector
from src.learning.tracker import PerformanceTracker
from src.learning.optimizer import StrategyOptimizer, Adjustment
from src.learning.self_eval import SelfEvaluator, EvalResult

__all__ = [
    "FeedbackCollector",
    "PerformanceTracker",
    "StrategyOptimizer",
    "Adjustment",
    "SelfEvaluator",
    "EvalResult",
]
