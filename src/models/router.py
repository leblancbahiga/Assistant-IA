"""ModelRouter — Router intelligent de modèles LLM.

Sélectionne automatiquement le meilleur modèle selon :
  - Type de tâche (simple vs complexe)
  - Coût actuel et budget restant
  - Charge système (RAM, CPU)
  - Performance mesurée (latence, précision)
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Callable

logger = logging.getLogger(__name__)


class TaskType(enum.Enum):
    """Type de tâche LLM."""
    SIMPLE = "simple"           # Réponses rapides, formatage
    RAG = "rag"                 # Recherche documentaire
    COMPLEX = "complex"         # Raisonnement, analyse
    CREATIVE = "creative"       # Génération, brainstorming
    CODE = "code"               # Génération de code
    VISION = "vision"           # Analyse d'images
    TOOL = "tool"               # Appel d'outil, JSON structuré


@dataclass
class ModelRoute:
    """Configuration de routage pour un modèle."""
    name: str                    # e.g., "groq/llama-3.3-70b"
    provider: str                # e.g., "groq", "openrouter"
    task_types: list[TaskType] = field(default_factory=lambda: list(TaskType))
    cost_per_1k_tokens: float = 0.0
    max_tokens: int = 4096
    context_window: int = 32768
    priority: int = 0            # 0 = default, plus haut = préféré
    fallback: str = ""           # Nom du modèle fallback
    requires_image: bool = False
    requires_tool_calling: bool = False
    avg_latency_ms: float = 0.0
    avg_accuracy: float = 0.0


@dataclass
class RoutingDecision:
    """Décision de routage."""
    selected_model: str
    task_type: TaskType
    reason: str
    estimated_cost: float
    fallback_models: list[str] = field(default_factory=list)
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "model": self.selected_model,
            "task": self.task_type.value,
            "reason": self.reason,
            "estimated_cost": self.estimated_cost,
            "fallbacks": self.fallback_models,
        }


@dataclass
class ModelRouter:
    """Router intelligent de modèles.

    Usage :
        router = ModelRouter()
        router.add_route(ModelRoute(
            name="groq/llama-3.3-70b",
            provider="groq",
            task_types=[TaskType.SIMPLE, TaskType.RAG],
            cost_per_1k_tokens=0.0001,
            priority=10,
        ))
        decision = router.decide(TaskType.RAG)
        print(decision.selected_model)
    """

    routes: list[ModelRoute] = field(default_factory=list)
    cost_guard: Optional[Any] = None  # CostGuard instance
    _metrics: dict[str, list[float]] = field(default_factory=dict)  # latency history
    _on_routing: Optional[Callable[[RoutingDecision], None]] = None

    def add_route(self, route: ModelRoute) -> None:
        """Ajoute une route de modèle."""
        self.routes.append(route)
        self.routes.sort(key=lambda r: r.priority, reverse=True)

    def clear_routes(self) -> None:
        """Supprime toutes les routes (utile pour rebuild après changement de clé API)."""
        self.routes.clear()

    def remove_route(self, name: str) -> None:
        self.routes = [r for r in self.routes if r.name != name]

    def decide(self, task_type: TaskType, requires_image: bool = False,
               requires_tools: bool = False) -> RoutingDecision:
        """Décide du meilleur modèle pour une tâche donnée.

        Args:
            task_type: Type de tâche
            requires_image: Si la tâche nécessite la vision
            requires_tools: Si la tâche nécessite du tool calling

        Returns:
            RoutingDecision
        """
        budget_ok = True
        if self.cost_guard:
            budget_ok = self.cost_guard.can_spend(0.001)  # $0.001 threshold

        candidates = [
            r for r in self.routes
            if task_type in r.task_types
            and (not requires_image or r.requires_image)
            and (not requires_tools or r.requires_tool_calling)
        ]

        if not candidates:
            # Fallback : n'importe quelle route
            candidates = self.routes

        if not candidates:
            return RoutingDecision(
                selected_model="default",
                task_type=task_type,
                reason="Aucune route configurée",
                estimated_cost=0.0,
            )

        # Budget check : si serré, prendre le moins cher
        if not budget_ok:
            cheapest = min(candidates, key=lambda r: r.cost_per_1k_tokens)
            decision = RoutingDecision(
                selected_model=cheapest.name,
                task_type=task_type,
                reason=f"Budget limité → modèle le moins cher ({cheapest.name})",
                estimated_cost=cheapest.cost_per_1k_tokens,
                fallback_models=[c.name for c in candidates[:3] if c != cheapest],
            )
            if self._on_routing:
                self._on_routing(decision)
            return decision

        # Sinon : meilleur modèle (priorité × accuracy)
        best = max(candidates, key=lambda r: r.priority * (1 + r.avg_accuracy))

        decision = RoutingDecision(
            selected_model=best.name,
            task_type=task_type,
            reason=f"Route optimale: priorité={best.priority}, accuracy={best.avg_accuracy:.2f}",
            estimated_cost=best.cost_per_1k_tokens,
            fallback_models=[c.name for c in candidates[:3] if c != best],
        )

        if self._on_routing:
            self._on_routing(decision)
        return decision

    def record_metrics(self, model: str, latency_ms: float, success: bool = True) -> None:
        """Enregistre les métriques de performance pour un modèle."""
        if model not in self._metrics:
            self._metrics[model] = []
        self._metrics[model].append(latency_ms)

        # Mettre à jour la latence moyenne sur la route
        for route in self.routes:
            if route.name == model:
                recent = self._metrics[model][-20:]  # Fenêtre 20
                route.avg_latency_ms = sum(recent) / len(recent)
                route.avg_accuracy = (sum(1 for _ in recent) / len(recent)) * 0.9 + 0.1

    def set_routing_callback(self, callback: Callable[[RoutingDecision], None]) -> None:
        self._on_routing = callback

    def to_dict(self) -> dict:
        return {
            "n_routes": len(self.routes),
            "routes": [{"name": r.name, "provider": r.provider, "priority": r.priority} for r in self.routes],
        }
