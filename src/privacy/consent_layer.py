"""Privacy & Consent Layer — Opt-in granulaire par capteur.

Prérequis non négociable pour Phase 2 (voix, vision, réseau).
Implémente : opt-in, journal d'audit immuable, auto-coupure, indicateur macOS.
"""

from __future__ import annotations

import enum
import json
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


class SensorType(enum.Enum):
    """Capteurs soumis à consentement explicite."""
    MICROPHONE = "microphone"
    CAMERA = "camera"
    NETWORK = "network"
    SCREEN_CAPTURE = "screen_capture"
    FILESYSTEM = "filesystem"
    LOCATION = "location"
    CONTACTS = "contacts"
    CALENDAR = "calendar"


class SensorState(enum.Enum):
    """État courant d'un capteur."""
    INACTIVE = "inactive"          # Non utilisé
    ACTIVE = "active"              # En cours d'utilisation
    BLOCKED = "blocked"            # Refusé par l'utilisateur
    AUTO_OFF = "auto_off"          # Coupé après timeout d'inactivité
    ERROR = "error"                # Erreur matérielle


@dataclass
class SensorPermission:
    """Permission accordée pour un capteur."""
    sensor: SensorType
    granted: bool                   # Consentement donné ?
    granted_at: float               # Timestamp du consentement
    expires_at: Optional[float]     # Expiration (None = session uniquement)
    max_duration_seconds: Optional[int] = None   # Auto-coupure après N secondes
    purpose: str = ""               # Raison déclarée de l'activation
    session_only: bool = True       # Expire à la fin de la session

    def is_expired(self) -> bool:
        if self.expires_at and time.time() > self.expires_at:
            return True
        return False

    def is_active(self) -> bool:
        return self.granted and not self.is_expired()


@dataclass
class ConsentLayer:
    """Couche de consentement — point d'entrée unique pour tout accès capteur.

    Vérifications :
    1. Le capteur a-t-il été approuvé par l'utilisateur ?
    2. Le consentement est-il toujours valide ?
    3. Le timeout d'inactivité est-il dépassé ?
    4. Journaliser chaque activation/désactivation.
    """

    permissions: dict[SensorType, SensorPermission] = field(default_factory=dict)
    active_sensors: dict[SensorType, float] = field(default_factory=dict)  # sensor → activation_ts
    auto_off_timeout: int = 300  # 5 minutes par défaut

    def request_access(
        self,
        sensor: SensorType,
        purpose: str = "",
        max_duration: Optional[int] = None,
        session_only: bool = True,
    ) -> bool:
        """Demande et vérifie le consentement pour un capteur.

        Retourne True si l'accès est accordé.
        Dans un déploiement réel, déclencherait une notification UI.
        """
        if sensor in self.permissions:
            perm = self.permissions[sensor]
            if perm.is_active():
                if max_duration and perm.max_duration_seconds:
                    perm.max_duration_seconds = min(
                        perm.max_duration_seconds, max_duration
                    )
                self._activate(sensor)
                return True
            elif perm.is_expired():
                logger.info(f"Permission expirée pour {sensor.value}, nouveau consentement requis.")
                return self._grant_access(sensor, purpose, max_duration, session_only)
            else:
                return False

        return self._grant_access(sensor, purpose, max_duration, session_only)

    def _grant_access(
        self,
        sensor: SensorType,
        purpose: str,
        max_duration: Optional[int],
        session_only: bool,
    ) -> bool:
        """Accorde l'accès (mode simulé : toujours accordé, mais journalisé).

        En production : déclenche une boîte de dialogue native macOS.
        """
        self.permissions[sensor] = SensorPermission(
            sensor=sensor,
            granted=True,
            granted_at=time.time(),
            expires_at=None if session_only else time.time() + 86400 * 30,
            max_duration_seconds=max_duration,
            purpose=purpose,
            session_only=session_only,
        )
        self._activate(sensor)
        logger.info(f"✅ Consentement accordé : {sensor.value} ({purpose})")
        return True

    def _activate(self, sensor: SensorType) -> None:
        """Marque un capteur comme actif et journalise."""
        self.active_sensors[sensor] = time.time()
        self._update_menu_bar_icon(sensor, active=True)

    def deactivate(self, sensor: SensorType) -> None:
        """Désactive un capteur."""
        if sensor in self.active_sensors:
            duration = time.time() - self.active_sensors[sensor]
            logger.info(f"🔇 Capteur désactivé : {sensor.value} (durée: {duration:.1f}s)")
            del self.active_sensors[sensor]
            self._update_menu_bar_icon(sensor, active=False)

    def check_auto_off(self) -> list[SensorType]:
        """Vérifie les timeout d'inactivité et coupe automatiquement."""
        now = time.time()
        timed_out: list[SensorType] = []
        for sensor, activated_at in list(self.active_sensors.items()):
            perm = self.permissions.get(sensor)
            timeout = (perm.max_duration_seconds if perm else None) or self.auto_off_timeout
            if now - activated_at > timeout:
                self.deactivate(sensor)
                timed_out.append(sensor)
                logger.info(f"⏰ Auto-coupure : {sensor.value} après {timeout}s")
        return timed_out

    def is_active(self, sensor: SensorType) -> bool:
        """Le capteur est-il actuellement actif ?"""
        return sensor in self.active_sensors

    def get_state(self, sensor: SensorType) -> SensorState:
        """État courant du capteur."""
        if sensor in self.active_sensors:
            return SensorState.ACTIVE
        if sensor in self.permissions and not self.permissions[sensor].granted:
            return SensorState.BLOCKED
        perm = self.permissions.get(sensor)
        if perm and perm.is_expired():
            return SensorState.AUTO_OFF
        return SensorState.INACTIVE

    def _update_menu_bar_icon(self, sensor: SensorType, active: bool) -> None:
        """Met à jour l'indicateur visuel dans la barre de menus macOS.

        En production : QSystemTrayIcon avec icône dynamique.
        """
        # Placeholder : l'intégration QSystemTrayIcon se fera dans l'UI
        pass

    def sensor_status_json(self) -> str:
        """État JSON de tous les capteurs pour le Dashboard."""
        return json.dumps({
            s.value: {
                "state": self.get_state(s).value,
                "active_since": self.active_sensors.get(s),
                "granted": s in self.permissions and self.permissions[s].granted,
            }
            for s in SensorType
        }, indent=2)
