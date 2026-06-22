"""NURU Security — Hardening final Phase 4.

Couche de sécurité finale : validation d'entrées, anti-injection,
protection des fichiers sensibles, vérification d'intégrité.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

NURU_HOME = Path.home() / ".nuru"


@dataclass
class SecurityConfig:
    """Configuration de sécurité."""
    allowed_paths: list[str] = field(default_factory=lambda: [
        str(Path.home()),
    ])
    blocked_paths: list[str] = field(default_factory=lambda: [
        "/etc", "/usr", "/bin", "/sbin", "/var/root",
    ])
    max_input_length: int = 100000
    blocked_commands: list[str] = field(default_factory=lambda: [
        "rm -rf /", "sudo", "chmod 777", "> /dev/sda",
    ])
    enable_sandbox: bool = True
    integrity_check: bool = True


@dataclass
class SecurityCheckResult:
    """Résultat d'une vérification de sécurité."""
    passed: bool
    message: str = ""
    warnings: list[str] = field(default_factory=list)


class SecurityManager:
    """Gestionnaire de sécurité NURU.

    Usage :
        security = SecurityManager()
        security.validate_path("~/Downloads/test.sh")  # True/False
        security.validate_input("rm -rf /")  # Blocks it
    """

    def __init__(self, config: Optional[SecurityConfig] = None):
        self.config = config or SecurityConfig()

    def validate_path(self, path: str | Path) -> bool:
        """Valide qu'un chemin est autorisé."""
        path = str(Path(path).expanduser().resolve())

        # Bloquer les chemins système
        for blocked in self.config.blocked_paths:
            if path.startswith(blocked):
                logger.warning(f"Chemin bloqué: {path}")
                return False

        # Vérifier qu'il est dans les dossiers autorisés
        for allowed in self.config.allowed_paths:
            allowed_path = str(Path(allowed).expanduser().resolve())
            if path.startswith(allowed_path):
                return True

        # ~/Downloads est toujours autorisé
        download_path = str(Path.home() / "Downloads")
        if path.startswith(download_path):
            return True

        # ~/.nuru est toujours autorisé
        nuru_path = str(NURU_HOME)
        if path.startswith(nuru_path):
            return True

        logger.warning(f"Chemin non autorisé: {path}")
        return False

    def validate_input(self, text: str) -> SecurityCheckResult:
        """Valide qu'une entrée utilisateur ne contient pas d'injection."""
        warnings = []

        # Taille max
        if len(text) > self.config.max_input_length:
            return SecurityCheckResult(False, f"Input trop long ({len(text)} > {self.config.max_input_length})")

        # Commandes dangereuses
        for cmd in self.config.blocked_commands:
            if cmd.lower() in text.lower():
                warnings.append(f"Tentative de commande bloquée: '{cmd}'")
                return SecurityCheckResult(False, f"Commande dangereuse détectée", warnings)

        # Patterns d'injection
        injection_patterns = [
            r"(?:';|' OR |' --|'; DROP|'; DELETE|'; UPDATE)",
            r"(?:<script>|javascript:|onerror=|onload=)",
            r"(?:\$\{|`[^`]*`|subprocess\.)",
        ]
        for pattern in injection_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                warnings.append(f"Pattern d'injection détecté: {pattern}")

        return SecurityCheckResult(
            passed=len(warnings) == 0,
            message="Input valide" if not warnings else "Avertissements",
            warnings=warnings,
        )

    def validate_command(self, command_parts: list[str]) -> SecurityCheckResult:
        """Valide une commande shell et ses arguments."""
        warnings = []

        for part in command_parts:
            # Chemin
            if part.startswith("/") and not self.validate_path(part):
                return SecurityCheckResult(False, f"Chemin non autorisé: {part}")

            # Sous-shell
            if "`" in part or "$(" in part:
                warnings.append("Sous-shell détecté")

        return SecurityCheckResult(
            passed=len(warnings) == 0,
            message="Commande valide" if not warnings else "Avertissements",
            warnings=warnings,
        )

    def check_integrity(self) -> SecurityCheckResult:
        """Vérification d'intégrité des fichiers critiques."""
        if not self.config.integrity_check:
            return SecurityCheckResult(True, "Intégrité désactivée")

        warnings = []
        critical_files = [
            NURU_HOME / "config" / "settings.yaml",
            Path("src/personality/guardrails.py"),
            Path("src/privacy/audit_log.py"),
        ]

        for path in critical_files:
            if path.exists():
                # Vérifier que le fichier n'est pas vide
                if path.stat().st_size == 0:
                    warnings.append(f"Fichier vide: {path}")
            else:
                warnings.append(f"Fichier manquant: {path}")

        return SecurityCheckResult(
            passed=len(warnings) == 0,
            message="Intégrité OK" if not warnings else f"{len(warnings)} avertissements",
            warnings=warnings,
        )

    def generate_integrity_hash(self, filepath: Path) -> Optional[str]:
        """Génère un hash SHA-256 d'un fichier."""
        try:
            data = filepath.read_bytes()
            return hashlib.sha256(data).hexdigest()
        except Exception as e:
            logger.error(f"Erreur hash {filepath}: {e}")
            return None

    def to_dict(self) -> dict:
        return {
            "allowed_paths": self.config.allowed_paths,
            "blocked_paths": self.config.blocked_paths,
            "enable_sandbox": self.config.enable_sandbox,
            "integrity_check": self.config.integrity_check,
        }
