"""NURU V9 — Module Agent : orchestration ReAct avec planification et verification.

V17 : AgentOrchestrator desormais delegable depuis NuruOrchestrator.
    Activation : config.agent_loop_enabled=True (False par defaut).
    Les requetes COMPLEX peuvent etre traitees par l'agent 4-phase
    (Plan->Execute->Verify->Synthesize) au lieu du pipeline Q&A standard.
    Par defaut : toujours dormant, non branche au pipeline ConversationEngine.
"""

import logging
logger = logging.getLogger(__name__)
logger.warning(
    "⚠️ V17 : Module Agent (ReAct) — delegable depuis NuruOrchestrator "
    "(config.agent_loop_enabled=True). Par defaut : toujours non branche "
    "au pipeline ConversationEngine."
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
