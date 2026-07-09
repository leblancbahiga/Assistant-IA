"""NURU V15 — Shim de compatibilité déprécié pour AgentOrchestrator.

⚠️ FICHIER RENOMMÉ (Item 24). Ancien nom : src/tools/agent_orchestrator.py.
    Ne plus utiliser ce chemin directement.

Importe depuis src.agent.orchestrator (fusionné V15 P0 #1).
Conserve la rétrocompatibilité des imports :

    from src.tools._deprecated_agent_orchestrator import (
        AgentOrchestrator, AgentTrace, PlanResult, VerifyResult,
    )

⚠️ Déprécié : migrer vers `from src.agent.orchestrator import ...`.
"""

import logging
import warnings

logger = logging.getLogger(__name__)

warnings.warn(
    "src.tools.agent_orchestrator est déprécié — "
    "utiliser from src.agent.orchestrator import ...",
    DeprecationWarning,
    stacklevel=2,
)

from src.agent.orchestrator import (  # noqa: F401, E402
    AgentOrchestrator,
    AgentTrace,
    PlanResult,
    VerifyResult,
)

__all__ = [
    "AgentOrchestrator",
    "AgentTrace",
    "PlanResult",
    "VerifyResult",
]
