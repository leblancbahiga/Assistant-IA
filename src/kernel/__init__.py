"""NURU Kernel — package du noyau central.

Remplace les imports directs entre modules par un registre central.
Tout service est accessible via kernel.get('name').

Migration progressive :
  Phase 3.0 : Créer le Kernel aux côtés de l'architecture existante
  Phase 3.1 : Migrer les modules un par un vers kernel.get()
  Phase 3.2 : Supprimer les imports directs
"""

from src.kernel.registry import ServiceRegistry
from src.kernel.kernel import NuruKernel
from src.kernel.state import KernelState
from src.kernel.metrics import KernelMetrics
from src.kernel.resources import KernelResources
from src.kernel.pipeline import PipelineEngine
from src.kernel.pipeline_steps import (
    ReceiveQuestion, Route, Retrieve, BuildContext,
    Generate, Validate, Act, Respond,
)
from src.kernel.router import KernelRouter
from src.kernel.cache import KernelCache
from src.kernel.scheduler import KernelScheduler, TaskPriority, TaskStatus, TaskInfo

__all__ = [
    "ServiceRegistry", "NuruKernel", "KernelState", "KernelMetrics",
    "KernelResources", "PipelineEngine", "KernelRouter",
    "KernelScheduler", "TaskPriority", "TaskStatus", "TaskInfo",
    "KernelCache",
]
