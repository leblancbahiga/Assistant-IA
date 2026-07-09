"""
NURU V15 — Shim de compatibilité pour AgentOrchestrator.

Importe depuis src.agent.orchestrator (fusionné V15 P0 #1).
Conserve la rétrocompatibilité des imports :

    from src.tools.agent_orchestrator import (
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

logger.debug("Shim src.tools.agent_orchestrator chargé")
