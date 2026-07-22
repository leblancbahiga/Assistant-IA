"""NURU V9 — Module Agent : orchestration ReAct avec planification et vérification.

V17 NOTE : CE MODULE N'EST PAS BRANCHÉ AU PIPELINE CONVERSATIONNEL ACTIF.
AgentOrchestrator, TaskPlanner, TaskExecutor, TaskVerifier, ErrorRecovery
et ResumeManager ne sont importés par ConversationEngine ni par NuruCore.
Le pipeline réel (NuruOrchestrator + LLMGenerator) gère les requêtes sans
ce sous-système. ~2000 lignes de code dormant — conservé pour usage futur.
"""

import logging
logger = logging.getLogger(__name__)
logger.warning(
    "⚠️ Module Agent (ReAct) non branché : AgentOrchestrator, Planner, "
    "Executor, Verifier, Recovery, Resume ne sont pas connectés au pipeline "
    "conversationnel. Voir src/agent/__init__.py pour la documentation."
)

__all__ = [
    "TaskPlanner", "TaskExecutor", "TaskVerifier",
    "ErrorRecovery", "ResumeManager", "AgentOrchestrator",
    "TaskStatus", "TaskPlan", "TaskStep", "StepResult",
    "AgentState", "AGENT_LIMITS",
]


def TaskPlanner(*args, **kwargs):
    from src.agent.planner import TaskPlanner as _c
    return _c(*args, **kwargs)


def TaskExecutor(*args, **kwargs):
    from src.agent.executor import TaskExecutor as _c
    return _c(*args, **kwargs)


def TaskVerifier(*args, **kwargs):
    from src.agent.verifier import TaskVerifier as _c
    return _c(*args, **kwargs)


def ErrorRecovery(*args, **kwargs):
    from src.agent.recovery import ErrorRecovery as _c
    return _c(*args, **kwargs)


def ResumeManager(*args, **kwargs):
    from src.agent.resume import ResumeManager as _c
    return _c(*args, **kwargs)


def AgentOrchestrator(*args, **kwargs):
    from src.agent.orchestrator import AgentOrchestrator as _c
    return _c(*args, **kwargs)


def TaskStatus(*args, **kwargs):
    from src.agent.types import TaskStatus
    return TaskStatus


def TaskPlan(*args, **kwargs):
    from src.agent.types import TaskPlan
    return TaskPlan


def TaskStep(*args, **kwargs):
    from src.agent.types import TaskStep
    return TaskStep


def StepResult(*args, **kwargs):
    from src.agent.types import StepResult
    return StepResult


def AgentState(*args, **kwargs):
    from src.agent.types import AgentState
    return AgentState


def AGENT_LIMITS(*args, **kwargs):
    from src.agent.types import AGENT_LIMITS
    return AGENT_LIMITS
