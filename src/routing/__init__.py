"""NURU Routing Package — Routeur unifié + SemanticRouter + DynamicPromptBuilder.

Tous les imports sont lazy pour éviter le cascade d'imports lourds
(PolicyEngine → pydantic → pydantic_core C extension).
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

_MODULES = {
    "Router": "src.routing.router",
    "RouterResult": "src.routing.router",
    "DynamicPromptBuilder": "src.routing.prompt_builder",
    "SemanticRouter": "src.routing.semantic_router",
    "SemanticRoute": "src.routing.semantic_router",
    "RouterV16": "src.routing.v16.router_v16",
    "RouteDecision": "src.routing.v16.router_v16",
}


def __getattr__(name: str) -> Any:
    """Lazy import : ne charge le module que quand le symbole est accédé."""
    if name in _MODULES:
        mod = importlib.import_module(_MODULES[name])
        obj = getattr(mod, name)
        # Cache dans le module actuel pour les accès suivants
        globals()[name] = obj
        return obj
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = list(_MODULES.keys())
