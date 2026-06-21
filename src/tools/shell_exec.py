"""Shell sécurisé NURU V12 — Exécution contrôlée de commandes shell.

Classes:
    CommandCategory: Catégories de risque des commandes.
    ValidationResult: Résultat de validation d'une commande.
    ExecutionResult: Résultat d'exécution d'une commande.
    ShellSandbox: Bac à sable pour exécution sécurisée (singleton).
    ApprovalRequest: Demande d'approbation en attente.
    ApprovalManager: Gestionnaire d'approbation (singleton).

Fonctions:
    register_shell_tools: Enregistre les outils shell dans le registre.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Callable

from src.core.events import EventBus
from src.tools.registry import ToolDefinition, ToolParameter, ToolExecutor, ToolRegistry

logger = logging.getLogger(__name__)

# ── Constantes ──────────────────────────────────────────────────

BLOCKED_COMMANDS: set[str] = {
    # Escalade privilèges
    "sudo", "su", "passwd",
    # Destruction disque/système
    "dd", "mkfs", "fdisk", "parted",
    "shutdown", "reboot", "halt", "poweroff", "init",
    # Processus
    "kill", "pkill",
    # Permissions dangereuses (patterns spécifiques)
    "chmod 777", "chmod -R 777",
    # Propriétaire
    "chown",
    # Destruction fichiers
    "rm -rf /", "rm -rf /*",
    # Fork bomb
    ":(){ :|:& };:",
    # Écriture directe disque
    "> /dev/sda",
    # Téléchargement + exécution
    "wget -O- | sh", "curl -sSL | bash",
    # Diskutil (macOS)
    "diskutil eraseDisk", "diskutil unmount", "diskutil mount",
    "diskutil",
    # Périphériques
    "/dev/sd", "/dev/nvme", "/dev/disk",
}

SAFE_COMMANDS: set[str] = {
    "ls", "pwd", "echo", "cat", "head", "tail", "file", "which",
    "uname", "date", "cal", "du", "df", "uptime", "whoami", "id",
    "groups", "locale", "printenv",
    "python3 --version", "python --version",
    "pip list", "pip3 list",
    "docker ps",
    "git status", "git log", "git diff", "git branch", "git remote",
}

AUTO_CONFIRM_COMMANDS: set[str] = {
    "ls", "pwd", "echo", "cat", "head", "tail", "file", "which",
    "uname", "date", "cal", "df -h", "du -sh",
    "uptime", "whoami", "id", "groups",
}

MAX_OUTPUT_LINES: int = 500
MAX_OUTPUT_CHARS: int = 50000
DEFAULT_TIMEOUT: int = 30
WORKSPACE_ONLY_BY_DEFAULT: bool = True
HOME: str = os.path.expanduser("~")
WORKSPACE: str = HOME + "/Nuru_Workspace"


# ── CommandCategory ─────────────────────────────────────────────

class CommandCategory(IntEnum):
    """Catégorie de risque d'une commande shell.

    Values:
        SAFE (0): Commandes totalement sûres (echo, ls...).
        READ (1): Lecture seule (cat, head...).
        WRITE (2): Écriture fichiers (touch, mkdir...).
        DESTRUCTIVE (3): Destruction potentielle (rm, dd...).
        NETWORK (4): Réseau (curl, wget...).
        INSTALL (5): Installation (pip, brew...).
    """
    SAFE = 0
    READ = 1
    WRITE = 2
    DESTRUCTIVE = 3
    NETWORK = 4
    INSTALL = 5


# ── ValidationResult ────────────────────────────────────────────

@dataclass
class ValidationResult:
    """Résultat de validation d'une commande shell.

    Attributes:
        allowed: La commande est-elle autorisée.
        reason: Raison du refus ou de l'acceptation.
        risk_category: Catégorie de risque détectée.
        suggested_level: Niveau d'accès minimum requis.
    """
    allowed: bool
    reason: str
    risk_category: CommandCategory
    suggested_level: int


# ── ExecutionResult ─────────────────────────────────────────────

@dataclass
class ExecutionResult:
    """Résultat d'exécution d'une commande shell.

    Attributes:
        success: La commande s'est terminée avec code 0.
        stdout: Sortie standard (stdout).
        stderr: Sortie d'erreur (stderr).
        exit_code: Code de retour du processus.
        duration_ms: Durée d'exécution en millisecondes.
        command: Commande exécutée.
    """
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float
    command: str


# ── ApprovalRequest ─────────────────────────────────────────────

@dataclass
class ApprovalRequest:
    """Demande d'approbation pour une commande shell.

    Attributes:
        id: Identifiant unique de la demande.
        command: Commande à approuver.
        reason: Raison de la demande.
        status: Statut (pending/approved/denied).
        timestamp: Timestamp de création.
        callback: Fonction à appeler lors de la résolution.
    """
    id: str
    command: str
    reason: str
    status: str  # "pending", "approved", "denied"
    timestamp: float
    callback: Callable | None = None


# ── ShellSandbox ────────────────────────────────────────────────

class ShellSandbox:
    """Bac à sable pour exécution sécurisée de commandes shell.

    Singleton. Valide, filtre et exécute des commandes avec :
    - Blocklist de commandes dangereuses
    - Restriction au workspace
    - Catégorisation du risque
    - Environnement nettoyé
    - Timeout et limites de sortie
    - Événements EventBus

    Utilisation::
        sandbox = ShellSandbox.get_instance()
        result = sandbox.execute("ls -la")
        if result.success:
            print(result.stdout)
    """

    _instance: ShellSandbox | None = None
    _singleton_lock: threading.Lock = threading.Lock()
    _initialized: bool = False

    def __new__(cls, *args: Any, **kwargs: Any) -> ShellSandbox:
        """Crée ou retourne l'instance unique (thread-safe)."""
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def __init__(self) -> None:
        """Initialisation unique du singleton."""
        if self._initialized:
            return
        self._initialized = True
        self._approval_manager: ApprovalManager | None = None
        logger.debug("ShellSandbox initialisé")

    # ── Validation ──

    def validate_command(self, command: str) -> ValidationResult:
        """Valide une commande shell complète.

        Vérifie successivement :
        1. Que la commande n'est pas vide.
        2. Qu'elle ne contient aucun motif de la blocklist.
        3. Qu'elle ne correspond à aucun pattern destructeur.
        4. Catégorise le risque résiduel.

        Args:
            command: Commande shell à valider.

        Returns:
            ValidationResult indiquant si la commande est autorisée.
        """
        if not command or not command.strip():
            return ValidationResult(
                allowed=False,
                reason="Commande vide",
                risk_category=CommandCategory.SAFE,
                suggested_level=1,
            )

        # Vérification blocklist
        blocked, reason = self._check_blocklist(command)
        if blocked:
            return ValidationResult(
                allowed=False,
                reason=reason,
                risk_category=CommandCategory.DESTRUCTIVE,
                suggested_level=5,
            )

        # Vérification patterns destructeurs
        destructive, reason = self._check_destructive_pattern(command)
        if destructive:
            return ValidationResult(
                allowed=False,
                reason=reason,
                risk_category=CommandCategory.DESTRUCTIVE,
                suggested_level=5,
            )

        # Catégorisation du risque
        category, level = self._get_risk_category(command)

        return ValidationResult(
            allowed=True,
            reason=(
                f"Commande autorisée "
                f"(catégorie: {category.name}, niveau: {level})"
            ),
            risk_category=category,
            suggested_level=level,
        )

    def _extract_base_command(self, command: str) -> str:
        """Extrait la commande de base d'une ligne de commande complète.

            >>> sandbox._extract_base_command("ls -la | grep foo")
            "ls"
            >>> sandbox._extract_base_command("echo hello > file.txt")
            "echo"
            >>> sandbox._extract_base_command("cd /tmp && pwd")
            "cd"

        Args:
            command: Ligne de commande complète.

        Returns:
            Commande de base (premier mot), ou chaîne vide si non trouvée.
        """
        cmd = command.strip()

        # Supprime les pipes, redirects et chaînages
        for sep in ("|", "&&", "||", ";", ">", "<", "2>", ">>", "2>>"):
            parts = cmd.split(sep, 1)
            cmd = parts[0].strip()

        # Extrait le premier mot
        parts = cmd.split()
        return parts[0] if parts else ""

    def _check_blocklist(self, command: str) -> tuple[bool, str]:
        """Vérifie si la commande contient un motif de la blocklist.

        La recherche est insensible à la casse et utilise la
        correspondance de sous-chaîne (substring match).

        Args:
            command: Commande à inspecter.

        Returns:
            Tuple (bloqué, raison). Si non bloqué, raison est vide.
        """
        cmd_lower = command.lower().strip()

        for blocked in BLOCKED_COMMANDS:
            if blocked.lower() in cmd_lower:
                return True, f"Commande bloquée: motif interdit '{blocked}'"

        return False, ""

    def _check_workspace(
        self, command: str, cwd: str | None
    ) -> tuple[bool, str]:
        """Vérifie que le répertoire de travail est dans le workspace.

        Args:
            command: Commande (non utilisée directement, gardée pour
                     cohérence d'API).
            cwd: Répertoire de travail à vérifier (None = WORKSPACE).

        Returns:
            Tuple (conforme, raison). Si conforme, raison est vide.
        """
        effective_cwd = cwd or WORKSPACE

        # Normalise le chemin
        try:
            effective_cwd = os.path.abspath(os.path.expanduser(effective_cwd))
        except Exception:
            return False, "Chemin invalide"

        workspace_norm = os.path.abspath(WORKSPACE)
        home_norm = os.path.abspath(HOME)

        if not effective_cwd.startswith(workspace_norm) and effective_cwd != home_norm:
            return (
                False,
                f"Répertoire non autorisé: {effective_cwd} (hors workspace)",
            )

        return True, ""

    def _get_risk_category(
        self, command: str
    ) -> tuple[CommandCategory, int]:
        """Détermine la catégorie de risque d'une commande.

        Se base sur la commande de base extraite et des ensembles
        de commandes connues.

        Args:
            command: Commande à évaluer.

        Returns:
            Tuple (catégorie, niveau de risque).
        """
        base = self._extract_base_command(command)
        cmd_text = command.strip().lower()

        # Safe commands
        if base in SAFE_COMMANDS:
            return CommandCategory.SAFE, 0
        # Vérifie aussi les commandes multi-mots connues
        for safe_cmd in SAFE_COMMANDS:
            if cmd_text.startswith(safe_cmd):
                return CommandCategory.SAFE, 0

        # Auto-confirm commands (aussi safe)
        if base in AUTO_CONFIRM_COMMANDS:
            return CommandCategory.SAFE, 0

        # Réseau
        network_cmds: set[str] = {
            "curl", "wget", "ssh", "scp", "sftp", "ftp", "rsync",
            "nc", "ncat", "ping", "nslookup", "dig", "telnet",
            "netcat", "socat",
        }
        if base in network_cmds:
            return CommandCategory.NETWORK, 4

        # Installation
        install_cmds: set[str] = {
            "pip", "pip3", "brew", "apt", "apt-get", "yum", "dnf",
            "npm", "yarn", "cargo", "gem", "conda", "poetry",
            "go", "rustup",
        }
        if base in install_cmds:
            return CommandCategory.INSTALL, 5

        # Écriture / modification
        write_cmds: set[str] = {
            "touch", "mkdir", "cp", "mv", "rm", "chmod", "chown",
            "ln", "tee", "dd", "install", "mktemp",
        }
        if base in write_cmds:
            return CommandCategory.WRITE, 2

        # Lecture seule
        read_cmds: set[str] = {
            "find", "grep", "rg", "ag", "ack", "tree", "stat", "wc",
            "sort", "uniq", "cut", "diff", "comm", "less", "more",
            "strings", "xxd", "hexdump", "od", "type", "cmd",
        }
        if base in read_cmds:
            return CommandCategory.READ, 1

        # Par défaut : WRITE (prudent)
        return CommandCategory.WRITE, 2

    def _check_destructive_pattern(self, command: str) -> tuple[bool, str]:
        """Vérifie les patterns destructeurs connus par regex.

        Détecte :
        - Fork bomb (:(){ :|:& };:)
        - rm -rf / ou rm -rf /*
        - Écriture directe sur /dev/sd*, /dev/nvme*
        - Téléchargement + exécution (curl/wget | sh)
        - chmod 777 / chmod -R 777
        - chown sur la racine

        Args:
            command: Commande à inspecter.

        Returns:
            Tuple (destructif, raison). Si non destructif, raison vide.
        """
        cmd_lower = command.lower().strip()

        # Fork bomb
        if ":(){ :|:& };:" in cmd_lower:
            return True, "Fork bomb détectée"

        # rm -rf / ou rm -rf /*
        if re.search(
            r'\brm\s+(-[a-z]*[rf]+[a-z]*\s+)+/\s*$', cmd_lower
        ) or re.search(r'\brm\s+(-[a-z]*[rf]+[a-z]*\s+)+/\*', cmd_lower):
            return True, "Commande rm destructive détectée"

        # Écriture directe sur disque (> /dev/sdX ou > /dev/nvmeX)
        if re.search(r'>\s+/dev/sd[a-z]', cmd_lower):
            return True, "Écriture directe sur disque détectée"
        if re.search(r'>\s+/dev/nvme', cmd_lower):
            return True, "Écriture directe sur disque NVMe détectée"

        # Téléchargement + exécution (curl|wget ... | sh|bash)
        if re.search(
            r'\b(?:curl|wget)\b.*\|\s*(?:sh|bash)\b', cmd_lower
        ):
            return True, "Téléchargement avec exécution détecté"

        # chmod 777 / chmod -R 777 (input déjà lowered)
        if re.search(r'chmod\s+(-[rR]\s+)?777\b', cmd_lower):
            return True, "Permissions 777 détectées"

        # chown sur /
        if re.search(r'\bchown\b', cmd_lower) and re.search(
            r'\s/\s', cmd_lower
        ):
            return True, "chown sur la racine détecté"

        return False, ""

    # ── Exécution ──

    def execute(
        self,
        command: str,
        cwd: str | None = None,
        timeout: int | None = None,
        level: int = 1,
    ) -> ExecutionResult:
        """Exécute une commande shell dans le bac à sable sécurisé.

        Le pipeline de validation complet est appliqué avant
        exécution : blocklist, patterns destructeurs, workspace,
        niveau d'accès.

        Émet les événements EventBus :
        - ``shell:execute:start`` au début
        - ``shell:execute:blocked`` si bloqué
        - ``shell:execute:complete`` en cas de succès
        - ``shell:execute:timeout`` en cas de timeout
        - ``shell:execute:error`` en cas d'erreur

        Args:
            command: Commande shell à exécuter.
            cwd: Répertoire de travail (None = WORKSPACE).
            timeout: Timeout en secondes (None = DEFAULT_TIMEOUT).
            level: Niveau d'accès de l'appelant (1-5).

        Returns:
            ExecutionResult avec stdout, stderr, code de retour.
        """
        start_time = time.time()
        effective_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
        effective_cwd = cwd if cwd else WORKSPACE

        bus = EventBus()
        bus.emit_sync(
            "shell:execute:start",
            {
                "command": command,
                "cwd": effective_cwd,
                "level": level,
            },
        )

        # Étape 1 : Validation
        validation = self.validate_command(command)
        if not validation.allowed:
            duration = (time.time() - start_time) * 1000
            bus.emit_sync(
                "shell:execute:blocked",
                {"command": command, "reason": validation.reason},
            )
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=validation.reason,
                exit_code=-1,
                duration_ms=duration,
                command=command,
            )

        # Étape 2 : Vérification workspace
        if WORKSPACE_ONLY_BY_DEFAULT:
            ws_ok, ws_reason = self._check_workspace(command, effective_cwd)
            if not ws_ok:
                duration = (time.time() - start_time) * 1000
                bus.emit_sync(
                    "shell:execute:blocked",
                    {"command": command, "reason": ws_reason},
                )
                return ExecutionResult(
                    success=False,
                    stdout="",
                    stderr=ws_reason,
                    exit_code=-1,
                    duration_ms=duration,
                    command=command,
                )

        # Étape 3 : Vérification niveau d'accès
        _, risk_level = self._get_risk_category(command)
        if level < risk_level:
            duration = (time.time() - start_time) * 1000
            msg = (
                f"Niveau d'accès insuffisant "
                f"(nécessite: {risk_level}, demandé: {level})"
            )
            bus.emit_sync(
                "shell:execute:blocked",
                {"command": command, "reason": msg},
            )
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=msg,
                exit_code=-1,
                duration_ms=duration,
                command=command,
            )

        # Exécution
        try:
            env = self._sanitize_env()

            # Créer le workspace si nécessaire
            os.makedirs(effective_cwd, exist_ok=True)

            result = subprocess.run(
                command,
                shell=True,
                cwd=effective_cwd,
                env=env,
                timeout=effective_timeout,
                capture_output=True,
                text=True,
            )

            duration = (time.time() - start_time) * 1000

            # Troncature
            stdout = self._truncate_output(result.stdout)
            stderr = self._truncate_output(result.stderr)

            execution_result = ExecutionResult(
                success=result.returncode == 0,
                stdout=stdout,
                stderr=stderr,
                exit_code=result.returncode,
                duration_ms=duration,
                command=command,
            )

            bus.emit_sync(
                "shell:execute:complete",
                {
                    "command": command,
                    "success": execution_result.success,
                    "exit_code": execution_result.exit_code,
                    "duration_ms": duration,
                },
            )

            return execution_result

        except subprocess.TimeoutExpired:
            duration = (time.time() - start_time) * 1000
            bus.emit_sync(
                "shell:execute:timeout",
                {"command": command, "timeout": effective_timeout},
            )
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Timeout ({effective_timeout}s) dépassé",
                exit_code=-1,
                duration_ms=duration,
                command=command,
            )

        except FileNotFoundError:
            duration = (time.time() - start_time) * 1000
            bus.emit_sync(
                "shell:execute:error",
                {"command": command, "error": "Commande introuvable"},
            )
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="Commande introuvable",
                exit_code=-1,
                duration_ms=duration,
                command=command,
            )

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            logger.exception("Erreur inattendue lors de l'exécution")
            bus.emit_sync(
                "shell:execute:error",
                {"command": command, "error": str(e)},
            )
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Erreur inattendue: {e}",
                exit_code=-1,
                duration_ms=duration,
                command=command,
            )

    def dry_run(self, command: str) -> ExecutionResult:
        """Simule l'exécution d'une commande sans la lancer.

        Produit un rapport de validation détaillé incluant :
        - Commande de base extraite
        - Statut d'autorisation
        - Catégorie de risque
        - Conformité workspace
        - Niveau requis

        Args:
            command: Commande à simuler.

        Returns:
            ExecutionResult avec le rapport de validation dans stdout.
        """
        validation = self.validate_command(command)
        base = self._extract_base_command(command)
        category, level = self._get_risk_category(command)

        lines = [
            f"▶ Dry-run: {command}",
            f"  Base command: {base}",
            f"  Autorisée: {validation.allowed}",
            f"  Catégorie: {category.name} (niveau {level})",
            f"  Raison: {validation.reason}",
        ]

        # Vérification workspace
        ws_ok, ws_reason = self._check_workspace(command, None)
        lines.append(f"  Workspace: {'OK' if ws_ok else ws_reason}")

        # Niveau suggéré
        lines.append(f"  Niveau requis: {validation.suggested_level}")

        return ExecutionResult(
            success=validation.allowed,
            stdout="\n".join(lines),
            stderr="" if validation.allowed else validation.reason,
            exit_code=0 if validation.allowed else -1,
            duration_ms=0.0,
            command=command,
        )

    def _sanitize_env(self) -> dict[str, str]:
        """Crée un environnement sécurisé minimisé pour subprocess.

        - PATH limité aux binaires systèmes et Homebrew
        - Suppression des variables de détournement (LD_PRELOAD, etc.)
        - SHELL restreint à /bin/sh

        Returns:
            Dictionnaire d'environnement sécurisé.
        """
        env = os.environ.copy()
        env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"
        # Supprime les variables potentiellement dangereuses
        for var in (
            "LD_PRELOAD",
            "LD_LIBRARY_PATH",
            "LD_AUDIT",
            "LD_DEBUG",
            "DYLD_INSERT_LIBRARIES",
            "DYLD_LIBRARY_PATH",
        ):
            env.pop(var, None)
        # Restreint le shell par défaut
        env["SHELL"] = "/bin/sh"
        return env

    def _truncate_output(self, output: str) -> str:
        """Tronque la sortie selon les limites MAX_OUTPUT_*.

        Args:
            output: Texte brut à tronquer.

        Returns:
            Texte tronqué, avec note si limite atteinte.
        """
        lines = output.splitlines(keepends=True)
        if len(lines) > MAX_OUTPUT_LINES:
            lines = lines[:MAX_OUTPUT_LINES]
            lines.append(
                f"\n[... sortie tronquée à {MAX_OUTPUT_LINES} lignes]"
            )

        text = "".join(lines)
        if len(text) > MAX_OUTPUT_CHARS:
            text = text[:MAX_OUTPUT_CHARS]
            text += (
                f"\n[... sortie tronquée à {MAX_OUTPUT_CHARS} caractères]"
            )

        return text

    # ── Gestionnaire d'approbation ──

    def set_approval_manager(self, manager: ApprovalManager) -> None:
        """Associe un gestionnaire d'approbation au sandbox.

        Args:
            manager: Instance d'ApprovalManager.
        """
        self._approval_manager = manager

    # ── Singleton ──

    @classmethod
    def get_instance(cls) -> ShellSandbox:
        """Retourne l'instance unique de ShellSandbox (singleton).

        Returns:
            Instance unique de ShellSandbox.
        """
        return cls()


# ── ApprovalManager ─────────────────────────────────────────────

class ApprovalManager:
    """Gestionnaire de demandes d'approbation pour commandes shell.

    Singleton. Gère un dictionnaire de demandes en attente avec
    capacités d'approbation, rejet et nettoyage des expirées.

    Utilisation::
        manager = ApprovalManager.get_instance()
        req_id = manager.request_approval("rm -rf /tmp/old", "Nettoyage")
        manager.resolve_approval(req_id, approved=True)
    """

    _instance: ApprovalManager | None = None
    _singleton_lock: threading.Lock = threading.Lock()
    _initialized: bool = False

    def __new__(cls, *args: Any, **kwargs: Any) -> ApprovalManager:
        """Crée ou retourne l'instance unique (thread-safe)."""
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def __init__(self) -> None:
        """Initialisation unique du singleton."""
        if self._initialized:
            return
        self._initialized = True
        self._lock: threading.Lock = threading.Lock()
        self._pending: dict[str, ApprovalRequest] = {}
        logger.debug("ApprovalManager initialisé")

    def request_approval(
        self,
        command: str,
        reason: str,
        callback: Callable | None = None,
    ) -> str:
        """Crée une demande d'approbation.

        La demande est stockée avec un ID unique et un timestamp.

        Args:
            command: Commande à approuver.
            reason: Raison justifiant la demande.
            callback: Fonction optionnelle appelée avec
                      (approved: bool, request_id: str) lors de la
                      résolution.

        Returns:
            Identifiant unique de la demande.
        """
        request_id = str(uuid.uuid4())
        request = ApprovalRequest(
            id=request_id,
            command=command,
            reason=reason,
            status="pending",
            timestamp=time.time(),
            callback=callback,
        )

        with self._lock:
            self._pending[request_id] = request

        logger.info(
            "Demande d'approbation créée: %s (%s)", request_id, reason
        )

        bus = EventBus()
        bus.emit_sync(
            "shell:approval:requested",
            {
                "request_id": request_id,
                "command": command,
                "reason": reason,
            },
        )

        return request_id

    def resolve_approval(self, request_id: str, approved: bool) -> bool:
        """Résout une demande d'approbation.

        Met à jour le statut et appelle le callback si présent.

        Args:
            request_id: Identifiant de la demande.
            approved: True pour approuver, False pour refuser.

        Returns:
            True si la demande a été trouvée et résolue.
        """
        with self._lock:
            request = self._pending.get(request_id)
            if request is None:
                logger.warning(
                    "Demande d'approbation introuvable: %s", request_id
                )
                return False
            request.status = "approved" if approved else "denied"
            # Retire de la file des demandes actives
            self._pending.pop(request_id, None)

        logger.info(
            "Demande %s: %s", request_id, request.status
        )

        # Appel du callback
        if request.callback:
            try:
                request.callback(approved, request_id)
            except Exception as e:
                logger.error(
                    "Erreur dans le callback d'approbation: %s", e
                )

        bus = EventBus()
        bus.emit_sync(
            "shell:approval:resolved",
            {
                "request_id": request_id,
                "command": request.command,
                "status": request.status,
            },
        )

        return True

    def list_pending(self) -> list[dict]:
        """Liste toutes les demandes en attente.

        Returns:
            Liste de dictionnaires représentant les demandes avec
            les clés : id, command, reason, status, timestamp.
        """
        with self._lock:
            return [
                {
                    "id": req.id,
                    "command": req.command,
                    "reason": req.reason,
                    "status": req.status,
                    "timestamp": req.timestamp,
                }
                for req in self._pending.values()
                if req.status == "pending"
            ]

    def cancel_expired(self, max_age: int | float = 300) -> int:
        """Annule les demandes plus anciennes que max_age secondes.

        Les demandes expirées sont marquées 'denied' et retirées.

        Args:
            max_age: Âge maximum en secondes (défaut: 300s = 5 min).

        Returns:
            Nombre de demandes annulées.
        """
        now = time.time()
        expired_ids: list[str] = []

        with self._lock:
            for req_id, req in list(self._pending.items()):
                if now - req.timestamp > max_age:
                    req.status = "denied"
                    expired_ids.append(req_id)
                    self._pending.pop(req_id, None)

        for req_id in expired_ids:
            logger.info("Demande expirée annulée: %s", req_id)
            bus = EventBus()
            bus.emit_sync(
                "shell:approval:expired",
                {"request_id": req_id},
            )

        return len(expired_ids)

    # ── Singleton ──

    @classmethod
    def get_instance(cls) -> ApprovalManager:
        """Retourne l'instance unique d'ApprovalManager.

        Returns:
            Instance unique d'ApprovalManager.
        """
        return cls()


# ── Fonction de registre ────────────────────────────────────────

def register_shell_tools(
    registry: ToolRegistry, executor: ToolExecutor
) -> None:
    """Enregistre les outils shell dans le ToolRegistry.

    Définit deux outils :
    - ``shell_exec`` : exécute une commande shell validée.
    - ``shell_dry_run`` : valide une commande sans l'exécuter.

    Les handlers sont enregistrés dans le ToolExecutor fourni.

    Args:
        registry: Registre d'outils (ToolRegistry).
        executor: Exécuteur d'outils (ToolExecutor).
    """
    # ── shell_exec ──────────────────────────────────────────

    exec_def = ToolDefinition(
        name="shell_exec",
        description=(
            "Exécute une commande shell dans le bac à sable sécurisé. "
            "Validation automatique, restriction workspace, "
            "environnement nettoyé."
        ),
        category="system",
        parameters=[
            ToolParameter(
                name="command",
                type="str",
                description="Commande shell à exécuter",
                required=True,
            ),
            ToolParameter(
                name="cwd",
                type="str",
                description=(
                    "Répertoire de travail (défaut: Nuru_Workspace)"
                ),
                required=False,
                default="",
            ),
            ToolParameter(
                name="timeout",
                type="int",
                description="Timeout en secondes (défaut: 30)",
                required=False,
                default=30,
            ),
            ToolParameter(
                name="level",
                type="int",
                description=(
                    "Niveau d'accès (1=lecture, 2=écriture, "
                    "4=réseau, 5=installation)"
                ),
                required=False,
                default=1,
            ),
        ],
    )

    def _exec_handler(**kwargs: Any) -> dict:
        """Handler pour shell_exec.

        Args:
            **kwargs: Paramètres de la commande.

        Returns:
            Dict avec les résultats de l'exécution.
        """
        sandbox = ShellSandbox.get_instance()
        command = kwargs.get("command", "")
        cwd = kwargs.get("cwd") or None
        timeout = kwargs.get("timeout")
        level = kwargs.get("level", 1)

        result = sandbox.execute(
            command=command,
            cwd=cwd,
            timeout=timeout,
            level=level,
        )

        return {
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "command": result.command,
        }

    registry.register(exec_def)
    executor.register_handler("shell_exec", _exec_handler)

    # ── shell_dry_run ───────────────────────────────────────

    dry_def = ToolDefinition(
        name="shell_dry_run",
        description=(
            "Valide une commande shell sans l'exécuter. "
            "Retourne un rapport détaillé de validation."
        ),
        category="system",
        parameters=[
            ToolParameter(
                name="command",
                type="str",
                description="Commande shell à valider",
                required=True,
            ),
        ],
    )

    def _dry_handler(**kwargs: Any) -> dict:
        """Handler pour shell_dry_run.

        Args:
            **kwargs: Paramètres de validation.

        Returns:
            Dict avec le rapport de validation.
        """
        sandbox = ShellSandbox.get_instance()
        command = kwargs.get("command", "")

        result = sandbox.dry_run(command=command)

        return {
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "command": result.command,
        }

    registry.register(dry_def)
    executor.register_handler("shell_dry_run", _dry_handler)
