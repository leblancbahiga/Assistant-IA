"""Journal d'audit immuable pour les accès capteurs et actions sensibles.

Chaque entrée contient : timestamp, capteur, durée, déclencheur.
Stocké dans ~/.nuru/audit.log (append-only, ligne par ligne en JSON).
"""

from __future__ import annotations

import json
import os
import time
import hashlib
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from .consent_layer import SensorType

logger = logging.getLogger(__name__)

AUDIT_LOG_PATH = Path.home() / ".nuru" / "audit.log"


@dataclass
class SensorEvent:
    """Événement capteur enregistré dans le journal."""
    event_type: str          # 'activated', 'deactivated', 'blocked', 'auto_off', 'error'
    sensor: str              # SensorType.value
    duration: float          # Durée en secondes (0 pour les événements sans activation)
    trigger: str             # 'user', 'app', 'wake_word', 'proactive', 'auto'
    purpose: str             # Raison déclarée
    timestamp: float = field(default_factory=time.time)
    previous_hash: str = ""  # SHA256 de l'entrée précédente (chaîne d'intégrité)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


@dataclass
class AuditEntry:
    """Entrée du journal avec chaîne de hash."""
    event: SensorEvent
    hash: str = ""
    line_number: int = 0

    def compute_hash(self, previous_hash: str) -> str:
        raw = self.event.to_json() + previous_hash
        return hashlib.sha256(raw.encode()).hexdigest()

    def verify_chain(self, previous_hash: str) -> bool:
        expected = self.compute_hash(previous_hash)
        return self.hash == expected


class AuditLog:
    """Journal d'audit immuable (append-only, chaîne de hash)."""

    def __init__(self, log_path: Path = AUDIT_LOG_PATH):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: list[AuditEntry] = []
        self._load()

    def _load(self) -> None:
        """Charge le journal existant pour vérifier la chaîne."""
        if not self.log_path.exists():
            return
        prev_hash = ""
        with open(self.log_path, "r") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    event = SensorEvent(**data["event"])
                    entry = AuditEntry(
                        event=event,
                        hash=data.get("hash", ""),
                        line_number=i,
                    )
                    if not entry.verify_chain(prev_hash):
                        logger.warning(f"⚠️ Audit log: chaîne brisée ligne {i}")
                    self._entries.append(entry)
                    prev_hash = entry.hash
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"⚠️ Audit log: entrée invalide ligne {i}: {e}")

    def _get_last_hash(self) -> str:
        return self._entries[-1].hash if self._entries else ""

    def log(
        self,
        event_type: str,
        sensor: SensorType,
        duration: float = 0.0,
        trigger: str = "app",
        purpose: str = "",
    ) -> AuditEntry:
        """Ajoute une entrée au journal."""
        prev_hash = self._get_last_hash()
        event = SensorEvent(
            event_type=event_type,
            sensor=sensor.value,
            duration=duration,
            trigger=trigger,
            purpose=purpose,
        )
        entry = AuditEntry(event=event)
        entry.hash = entry.compute_hash(prev_hash)
        entry.line_number = len(self._entries) + 1

        # Append au fichier
        line = json.dumps({
            "event": event.to_dict(),
            "hash": entry.hash,
        }, default=str)
        with open(self.log_path, "a") as f:
            f.write(line + "\n")

        self._entries.append(entry)
        logger.debug(f"📝 Audit: {event_type} {sensor.value} ({trigger})")
        return entry

    def get_recent(self, n: int = 50) -> list[AuditEntry]:
        """Dernières N entrées."""
        return self._entries[-n:] if self._entries else []

    def get_by_sensor(self, sensor: SensorType) -> list[AuditEntry]:
        """Entrées pour un capteur spécifique."""
        return [e for e in self._entries if e.event.sensor == sensor.value]

    def get_by_type(self, event_type: str) -> list[AuditEntry]:
        """Entrées d'un type spécifique."""
        return [e for e in self._entries if e.event.event_type == event_type]

    def verify_integrity(self) -> bool:
        """Vérifie toute la chaîne de hash."""
        prev_hash = ""
        for entry in self._entries:
            if not entry.verify_chain(prev_hash):
                return False
            prev_hash = entry.hash
        return True

    def summary(self) -> dict:
        """Résumé du journal pour le Dashboard."""
        return {
            "total_entries": len(self._entries),
            "integrity_ok": self.verify_integrity(),
            "by_sensor": {
                s.value: len(self.get_by_sensor(s))
                for s in SensorType
            },
            "by_type": {
                t: len(self.get_by_type(t))
                for t in {"activated", "deactivated", "blocked", "auto_off", "error"}
            },
        }
