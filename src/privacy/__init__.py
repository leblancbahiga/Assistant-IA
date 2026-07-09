"""NURU Privacy & Consent Layer — Phase 2a.

Modules de sécurité avant l'ouverture des capteurs (micro, caméra, réseau).
Journal d'audit immuable, opt-in granulaire, indicateur visuel macOS.
"""

from __future__ import annotations

import logging
from typing import Optional

from .consent_layer import ConsentLayer, SensorPermission, SensorType, SensorState
from .permissions import PermissionManager, PermissionMatrix, PermissionLevel
from .audit_log import AuditLog, AuditEntry, SensorEvent

logger = logging.getLogger(__name__)

# Singleton paresseux pour le ConsentLayer
_consent_layer: Optional[ConsentLayer] = None


def get_consent_layer() -> ConsentLayer:
    """Retourne l'instance unique du ConsentLayer (lazy)."""
    global _consent_layer
    if _consent_layer is None:
        _consent_layer = ConsentLayer()
        logger.debug("ConsentLayer singleton initialisé")
    return _consent_layer


__all__ = [
    "ConsentLayer", "SensorPermission", "SensorType", "SensorState",
    "PermissionManager", "PermissionMatrix", "PermissionLevel",
    "AuditLog", "AuditEntry", "SensorEvent",
    "get_consent_layer",
]
