"""NURU Privacy & Consent Layer — Phase 2a.

Modules de sécurité avant l'ouverture des capteurs (micro, caméra, réseau).
Journal d'audit immuable, opt-in granulaire, indicateur visuel macOS.
"""

from .consent_layer import ConsentLayer, SensorPermission, SensorType, SensorState
from .permissions import PermissionManager, PermissionMatrix, PermissionLevel
from .audit_log import AuditLog, AuditEntry, SensorEvent

__all__ = [
    "ConsentLayer", "SensorPermission", "SensorType", "SensorState",
    "PermissionManager", "PermissionMatrix", "PermissionLevel",
    "AuditLog", "AuditEntry", "SensorEvent",
]
