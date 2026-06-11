"""
NURU V9 — Types partagés du module Agent.

Centralise les dataclasses utilisées par Planner, Executor, Verifier,
Recovery, Resume, et Orchestrator.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


class TaskStatus(enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    INTERRUPTED = "interrupted"


class ErrorType(enum.Enum):
    TOOL_FAILURE = "tool_failure"
    TIMEOUT = "timeout"
    HALLUCINATION_DETECTED = "hallucination_detected"
    LOW_CONFIDENCE = "low_confidence"
    RAM_EXCEEDED = "ram_exceeded"
    NETWORK_ERROR = "network_error"
    USER_CANCELLED = "user_cancelled"
    UNKNOWN = "unknown"


class RecoveryAction(enum.Enum):
    RETRY = "retry"
    ALTERNATIVE_TOOL = "alternative_tool"
    SIMPLIFY = "simplify"
    ASK_USER = "ask_user"
    FALLBACK_TO_RAG = "fallback_to_rag"
    REGENERATE_STRICT = "regenerate_strict_prompt"
    REDUCE_BATCH = "reduce_batch_size"
    UNLOAD_MODELS = "unload_unused_models"
    OFFLINE_FALLBACK = "offline_fallback"
    ESCALATE = "escalate_to_user"
    PARTIAL_RESULT = "partial_result"
    SEARCH_MORE = "search_more_sources"
    RETRY_BACKOFF = "retry_with_backoff"


@dataclass
class ToolCall:
    """Un appel d'outil dans le cadre d'une étape de tâche."""
    tool_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    timeout_s: int = 30


@dataclass
class TaskStep:
    """Une étape atomique dans un plan de tâche."""
    step_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    max_retries: int = 3
    timeout_s: int = 60
    expected_output: str = ""


@dataclass
class TaskPlan:
    """Plan complet décomposant un objectif en étapes ordonnées."""
    goal: str
    steps: list[TaskStep] = field(default_factory=list)
    created_at: float = 0.0


@dataclass
class StepResult:
    """Résultat de l'exécution d'une étape."""
    step_id: str
    status: TaskStatus = TaskStatus.PENDING
    output: Any = None
    error: Optional[str] = None
    duration_s: float = 0.0
    confidence: float = 1.0
    tool_results: list[dict] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return self.status == TaskStatus.COMPLETED


@dataclass
class RecoveryDecision:
    """Décision de recovery suite à une erreur."""
    action: RecoveryAction
    params: dict[str, Any] = field(default_factory=dict)
    message: str = ""


@dataclass
class AgentState:
    """État persistant de l'agent pour une session."""
    session_id: str = ""
    current_goal: str = ""
    plan: Optional[TaskPlan] = None
    step_results: dict[str, StepResult] = field(default_factory=dict)
    current_step_index: int = 0
    started_at: float = 0.0
    status: str = "idle"  # idle | planning | executing | verifying | done | error

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "current_goal": self.current_goal,
            "current_step_index": self.current_step_index,
            "started_at": self.started_at,
            "status": self.status,
            "step_count": len(self.plan.steps) if self.plan else 0,
        }


# ── Limites de sécurité ──
AGENT_LIMITS = {
    "max_steps": 5,
    "max_retries_per_step": 3,
    "max_wall_time_seconds": 300,
    "max_tool_calls_per_step": 3,
    "require_confirmation": ["edit_file", "execute_python", "run_git_commit"],
    "sandbox_only": ["execute_python"],
}
