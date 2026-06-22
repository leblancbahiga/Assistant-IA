"""Permission Manager — Matrice granulaire par connecteur.

Contrôle fin : lecture/écriture/suppression par connecteur externe.
Intégré au ToolRegistry pour toute action à effet de bord.
"""

from __future__ import annotations

import enum
import json
import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class PermissionLevel(enum.IntEnum):
    """Niveaux de permission pour chaque connecteur."""
    NONE = 0          # Aucun accès
    READ = 1          # Lecture seule
    WRITE = 2         # Lecture + écriture
    DELETE = 3        # Lecture + écriture + suppression
    ADMIN = 4         # Contrôle total (réservé)


CONNECTOR_OPERATIONS = {
    "gmail":       {"read", "send", "delete", "manage_labels"},
    "calendar":    {"read", "create", "update", "delete"},
    "tasks":       {"read", "create", "update", "delete"},
    "filesystem":  {"read", "write", "delete", "execute"},
    "shell":       {"read", "write", "execute"},
    "browser":     {"navigate", "click", "type", "scrape"},
    "os_control":  {"launch", "quit", "volume", "brightness"},
    "network":     {"http_get", "http_post", "websocket"},
    "microphone":  {"listen"},
    "camera":      {"capture"},
    "screen":      {"capture", "analyze"},
    "contacts":    {"read"},
    "notifications": {"send"},
}


@dataclass
class OperationPermission:
    """Permission pour une opération spécifique."""
    operation: str
    allowed: bool
    requires_confirmation: bool = True
    last_approved: Optional[float] = None
    auto_approve_count: int = 0        # Combien de fois auto-approuvé

    def to_dict(self) -> dict:
        return {
            "operation": self.operation,
            "allowed": self.allowed,
            "requires_confirmation": self.requires_confirmation,
            "last_approved": self.last_approved,
        }


@dataclass
class ConnectorPermissions:
    """Permissions pour un connecteur."""
    connector: str
    level: PermissionLevel = PermissionLevel.NONE
    operations: dict[str, OperationPermission] = field(default_factory=dict)
    notes: str = ""

    def can(self, operation: str) -> bool:
        """Vérifie si une opération est autorisée."""
        if operation in self.operations:
            return self.operations[operation].allowed
        # Fallback : vérifier le niveau
        op_map = {
            PermissionLevel.NONE: set(),
            PermissionLevel.READ: {"read", "navigate", "http_get", "scrape", "listen"},
            PermissionLevel.WRITE: {"read", "navigate", "http_get", "scrape", "listen",
                                    "write", "send", "create", "launch", "quit"},
            PermissionLevel.DELETE: set(),  # DELETE = tout sauf admin
            PermissionLevel.ADMIN: set(),
        }
        return operation in op_map.get(self.level, set())


@dataclass
class PermissionMatrix:
    """Matrice globale de permissions."""
    connectors: dict[str, ConnectorPermissions] = field(default_factory=dict)

    def __post_init__(self):
        if not self.connectors:
            self._init_defaults()

    def _init_defaults(self) -> None:
        """Initialise les permissions par défaut (sécuritaires)."""
        for connector in CONNECTOR_OPERATIONS:
            ops = {}
            for op in CONNECTOR_OPERATIONS[connector]:
                # Par défaut : tout nécessite confirmation
                ops[op] = OperationPermission(
                    operation=op,
                    allowed=True,
                    requires_confirmation=True,
                )
            self.connectors[connector] = ConnectorPermissions(
                connector=connector,
                level=PermissionLevel.READ,
                operations=ops,
            )

    def set_level(self, connector: str, level: PermissionLevel) -> None:
        """Définit le niveau global pour un connecteur."""
        if connector not in self.connectors:
            self.connectors[connector] = ConnectorPermissions(
                connector=connector, level=level
            )
        else:
            self.connectors[connector].level = level

    def allow_operation(
        self,
        connector: str,
        operation: str,
        requires_confirmation: bool = True,
    ) -> None:
        """Autorise une opération spécifique."""
        if connector not in self.connectors:
            self.connectors[connector] = ConnectorPermissions(
                connector=connector, level=PermissionLevel.READ
            )
        self.connectors[connector].operations[operation] = OperationPermission(
            operation=operation,
            allowed=True,
            requires_confirmation=requires_confirmation,
        )

    def check(self, connector: str, operation: str) -> bool:
        """Vérifie si une opération est autorisée."""
        if connector not in self.connectors:
            logger.warning(f"Connecteur inconnu: {connector}, accès refusé")
            return False
        return self.connectors[connector].can(operation)

    def to_dict(self) -> dict:
        return {
            name: {
                "level": perm.level.name,
                "operations": {k: v.to_dict() for k, v in perm.operations.items()},
                "notes": perm.notes,
            }
            for name, perm in self.connectors.items()
        }


class PermissionManager:
    """Gestionnaire central des permissions pour le ToolRegistry.

    Point de contrôle pour toute action à effet de bord.
    """

    def __init__(self, config_path: Optional[Path] = None):
        self.matrix = PermissionMatrix()
        self.config_path = config_path or Path.home() / ".nuru" / "permissions.json"
        self._load()

    def _load(self) -> None:
        """Charge la matrice depuis le disque."""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    data = json.load(f)
                for connector, config in data.items():
                    level = PermissionLevel[config.get("level", "NONE")]
                    self.matrix.set_level(connector, level)
                    for op_name, op_config in config.get("operations", {}).items():
                        self.matrix.allow_operation(
                            connector, op_name,
                            requires_confirmation=op_config.get("requires_confirmation", True),
                        )
                logger.info(f"Permissions chargées: {len(data)} connecteurs")
            except Exception as e:
                logger.warning(f"Erreur chargement permissions: {e}")

    def save(self) -> None:
        """Sauvegarde la matrice."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self.matrix.to_dict(), f, indent=2)
        logger.info("Permissions sauvegardées")

    def can_execute(self, connector: str, operation: str) -> bool:
        """Vérifie si une action peut être exécutée par le ToolRegistry."""
        allowed = self.matrix.check(connector, operation)
        if not allowed:
            logger.warning(f"🚫 Permission refusée: {connector}/{operation}")
        return allowed

    def require_confirmation(self, connector: str, operation: str) -> bool:
        """L'opération nécessite-t-elle une confirmation humaine ?"""
        if connector not in self.matrix.connectors:
            return True
        ops = self.matrix.connectors[connector].operations
        if operation in ops:
            return ops[operation].requires_confirmation
        return True  # Inconnu = sécuritaire

    def grant(self, connector: str, operation: str) -> None:
        """Accorde une permission spécifique."""
        self.matrix.allow_operation(connector, operation)
        self.save()

    def revoke(self, connector: str, operation: str) -> None:
        """Révoque une permission spécifique."""
        if connector in self.matrix.connectors:
            ops = self.matrix.connectors[connector].operations
            if operation in ops:
                ops[operation].allowed = False
                self.save()
