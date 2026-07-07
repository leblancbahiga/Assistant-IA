"""
NURU Security — DÉPRÉCIÉ V15 Phase 0B.

Les classes SecurityManager, SecurityConfig, SecurityCheckResult ont été
fusionnées dans src.core.prompt_guard. Ce module sert de shim de compatibilité.

Utilisez désormais :
    from src.core.prompt_guard import SecurityManager, SecurityConfig, SecurityCheckResult
"""
from __future__ import annotations

import logging
import warnings

from src.core.prompt_guard import (  # noqa: F401
    NURU_HOME,
    SecurityCheckResult,
    SecurityConfig,
    SecurityManager,
)

logger = logging.getLogger(__name__)
warnings.warn(
    "src.security est déprécié — importez depuis src.core.prompt_guard "
    "à la place : from src.core.prompt_guard import SecurityManager",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "SecurityManager",
    "SecurityConfig",
    "SecurityCheckResult",
    "NURU_HOME",
]
