"""Gestion fichiers CRUD avec sandbox workspace — NURU V12.

Classes:
    PathSafety: Niveaux de sécurité des chemins.
    FileOpResult: Résultat standard d'une opération fichier.
    FileOpsController: Contrôleur fichiers singleton avec sandbox workspace.

Fonctions:
    register_file_tools: Enregistre les 12 outils fichiers dans le registre.
"""

from __future__ import annotations

import fnmatch
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any

from src.core.events import EventBus
from src.tools.registry import ToolDefinition, ToolParameter, ToolExecutor, ToolRegistry

logger = logging.getLogger(__name__)

# ── Constantes ──────────────────────────────────────────────────

HOME: str = os.path.expanduser("~")
WORKSPACE_ROOT: str = os.path.join(HOME, "Nuru_Workspace")

# Niveau d'accès minimum requis pour les opérations destructives
DESTRUCTIVE_ACCESS_LEVEL: int = 3

SYSTEM_DIRS: tuple[str, ...] = (
    # macOS
    "/.ssh", "~/.ssh",
    "/.gnupg", "~/.gnupg",
    "/etc",
    "/System",
    "/private",
    "/dev",
    "/.Trash", "~/.Trash",
    "/var/db",
    "/var/root",
    "/Library/Keychains",
    "~/Library/Keychains",
    # Linux / général
    "/proc",
    "/sys",
    "/boot",
    "/lost+found",
    # Windows / cross-platform
    "/Windows",
    "/Program Files",
    "/Program Files (x86)",
    "/System32",
)

# Chemins système élargis (vérification par préfixe)
SYSTEM_PATH_PREFIXES: tuple[str, ...] = tuple(
    os.path.abspath(os.path.expanduser(d)).rstrip("/") + "/"
    for d in SYSTEM_DIRS
)


# ── PathSafety ───────────────────────────────────────────────────

class PathSafety(IntEnum):
    """Niveau de sécurité d'un chemin fichier.

    Values:
        WORKSPACE (0): Dans le workspace autorisé (~/Nuru_Workspace/).
        AUTHORIZED (1): Dans un dossier explicitement autorisé.
        SYSTEM (2): Dossier système potentiellement dangereux.
        BLOCKED (3): Dossier bloqué (interdit d'accès).
        OUTSIDE (4): Hors de tout scope (nécessite approbation).
    """
    WORKSPACE = 0
    AUTHORIZED = 1
    SYSTEM = 2
    BLOCKED = 3
    OUTSIDE = 4

    def __str__(self) -> str:
        labels = {
            0: "WORKSPACE",
            1: "AUTHORIZED",
            2: "SYSTEM",
            3: "BLOCKED",
            4: "OUTSIDE",
        }
        return labels.get(self.value, f"UNKNOWN({self.value})")


# ── FileOpResult ────────────────────────────────────────────────

@dataclass
class FileOpResult:
    """Résultat standard d'une opération fichier.

    Attributes:
        success: L'opération a réussi.
        message: Message descriptif du résultat.
        path: Chemin du fichier/dossier concerné.
        details: Dictionnaire de détails (stats, taille, etc.).
        error: Message d'erreur si échec.
        duration_ms: Durée d'exécution en millisecondes.
    """
    success: bool
    message: str
    path: str | None = None
    details: dict | None = None
    error: str | None = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convertit le résultat en dictionnaire pour le LLM."""
        return {
            "success": self.success,
            "message": self.message,
            "path": self.path,
            "details": self.details,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


# ── FileOpsController ───────────────────────────────────────────

class FileOpsController:
    """Contrôleur fichiers CRUD avec sandbox workspace.

    Singleton thread-safe. Gère les opérations fichiers dans un
    workspace restreint avec validation de sécurité, blocklist de
    dossiers système, et intégration EventBus.

    Utilisation::
        ctrl = FileOpsController.get_instance()
        result = ctrl.read_file("mon_fichier.txt")
        if result.success:
            print(result.details["content"])
    """

    _instance: FileOpsController | None = None
    _singleton_lock: threading.Lock = threading.Lock()
    _initialized: bool = False

    def __new__(cls, *args: Any, **kwargs: Any) -> FileOpsController:
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

        # Workspace par défaut
        self._workspace_root: str = WORKSPACE_ROOT
        self._ensure_workspace()

        # Dossiers explicitement autorisés (en plus du workspace)
        self._authorized_dirs: set[str] = set()

        # Verrou pour les chemins autorisés
        self._auth_lock: threading.Lock = threading.Lock()

        # Profil de sécurité : "safe" (0-2), "power" (3), "admin" (4-5)
        self._safety_profile: str = "safe"

        # Shell sandbox optionnel (importé tardivement pour éviter circular)
        self._shell_sandbox: Any = None

        logger.debug(
            "FileOpsController initialisé — workspace: %s",
            self._workspace_root,
        )

    # ── Singleton helper ───────────────────────────────────────

    @classmethod
    def get_instance(cls) -> FileOpsController:
        """Retourne l'instance unique du contrôleur fichiers.

        Returns:
            L'instance unique de FileOpsController.
        """
        return cls()

    # ── Propriétés ─────────────────────────────────────────────

    @property
    def workspace_root(self) -> str:
        """Retourne la racine du workspace."""
        return self._workspace_root

    @workspace_root.setter
    def workspace_root(self, value: str) -> None:
        """Définit la racine du workspace (crée si nécessaire)."""
        resolved = os.path.abspath(os.path.expanduser(value))
        os.makedirs(resolved, exist_ok=True)
        self._workspace_root = resolved

    @property
    def authorized_dirs(self) -> set[str]:
        """Retourne l'ensemble des dossiers autorisés."""
        return self._authorized_dirs.copy()

    @property
    def safety_profile(self) -> str:
        """Retourne le profil de sécurité actuel.

        Profils:
            - "safe" (0-2) : opérations destructives refusées
            - "power" (3)  : opérations destructives approuvées
            - "admin" (4-5): toutes les opérations autorisées
        """
        return self._safety_profile

    @safety_profile.setter
    def safety_profile(self, value: str) -> None:
        """Définit le profil de sécurité.

        Args:
            value: "safe", "power", ou "admin".
        """
        valid = {"safe", "power", "admin"}
        if value not in valid:
            raise ValueError(
                f"Profil invalide: '{value}'. "
                f"Doit être l'un de: {', '.join(sorted(valid))}"
            )
        self._safety_profile = value
        logger.info("Profil de sécurité fichier: %s", value)

    # ── Initialisation ─────────────────────────────────────────

    def _ensure_workspace(self) -> None:
        """S'assure que le workspace existe (crée si nécessaire)."""
        try:
            os.makedirs(self._workspace_root, exist_ok=True)
        except OSError as e:
            logger.warning(
                "Impossible de créer le workspace %s: %s",
                self._workspace_root,
                e,
            )

    def get_safety_level(self) -> int:
        """Retourne le niveau de sécurité numérique.

        Returns:
            0-2 pour "safe", 3 pour "power", 4-5 pour "admin".
        """
        levels = {"safe": 1, "power": 3, "admin": 5}
        return levels.get(self._safety_profile, 1)

    # ── Workspace management ───────────────────────────────────

    def get_workspace_info(self) -> FileOpResult:
        """Retourne les statistiques du workspace et ses sous-dossiers.

        Returns:
            FileOpResult avec les détails du workspace dans details.
        """
        start = time.time()
        bus = EventBus()

        try:
            ws = self._workspace_root
            if not os.path.isdir(ws):
                duration = (time.time() - start) * 1000
                return FileOpResult(
                    success=True,
                    message="Le workspace n'existe pas encore",
                    path=ws,
                    details={
                        "exists": False,
                        "path": ws,
                        "size_bytes": 0,
                        "file_count": 0,
                        "dir_count": 0,
                        "subdirs": [],
                    },
                    duration_ms=duration,
                )

            # Statistiques
            total_size = 0
            file_count = 0
            dir_count = 0
            subdirs: list[str] = []

            for root, dirs, files in os.walk(ws):
                # Évite les dossiers cachés
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                rel = os.path.relpath(root, ws)
                if rel != ".":
                    subdirs.append(rel)
                for f in files:
                    fpath = os.path.join(root, f)
                    try:
                        total_size += os.path.getsize(fpath)
                        file_count += 1
                    except OSError:
                        pass
                dir_count += len(dirs)

            # Taille du workspace racine
            try:
                ws_size = sum(
                    os.path.getsize(os.path.join(ws, f))
                    for f in os.listdir(ws)
                    if os.path.isfile(os.path.join(ws, f))
                )
            except OSError:
                ws_size = 0

            duration = (time.time() - start) * 1000
            details = {
                "exists": True,
                "path": ws,
                "size_bytes": total_size,
                "file_count": file_count,
                "dir_count": dir_count,
                "subdirs": sorted(subdirs),
                "workspace_root_size_bytes": ws_size,
                "authorized_dirs": list(self._authorized_dirs),
                "safety_profile": self._safety_profile,
            }

            bus.emit_sync("file:workspace_info", details)
            return FileOpResult(
                success=True,
                message=f"Workspace: {ws} ({file_count} fichiers, {dir_count} dossiers)",
                path=ws,
                details=details,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {"error": str(e)})
            return FileOpResult(
                success=False,
                message="Erreur lors de la récupération des infos workspace",
                error=str(e),
                duration_ms=duration,
            )

    def authorize_directory(self, path: str) -> FileOpResult:
        """Ajoute un dossier à la liste des dossiers autorisés.

        Args:
            path: Chemin du dossier à autoriser.

        Returns:
            FileOpResult indiquant le succès de l'opération.
        """
        start = time.time()
        bus = EventBus()

        try:
            resolved = os.path.abspath(os.path.expanduser(path))

            # Vérifie que le dossier existe
            if not os.path.isdir(resolved):
                duration = (time.time() - start) * 1000
                return FileOpResult(
                    success=False,
                    message=f"Le dossier n'existe pas: {resolved}",
                    path=resolved,
                    error="DirectoryNotFound",
                    duration_ms=duration,
                )

            # Vérifie que ce n'est pas un dossier système
            safety, _ = self.check_path_safety(resolved)
            if safety in (PathSafety.SYSTEM, PathSafety.BLOCKED):
                duration = (time.time() - start) * 1000
                return FileOpResult(
                    success=False,
                    message=f"Impossible d'autoriser un dossier système: {resolved}",
                    path=resolved,
                    error="SystemPathBlocked",
                    duration_ms=duration,
                )

            with self._auth_lock:
                # Normalise et stocke
                normalized = resolved.rstrip("/") + "/"
                self._authorized_dirs.add(normalized)

            duration = (time.time() - start) * 1000
            bus.emit_sync("file:authorized", {"path": resolved})
            return FileOpResult(
                success=True,
                message=f"Dossier autorisé: {resolved}",
                path=resolved,
                details={"authorized_path": resolved},
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {"error": str(e)})
            return FileOpResult(
                success=False,
                message="Erreur lors de l'autorisation du dossier",
                error=str(e),
                duration_ms=duration,
            )

    def deauthorize_directory(self, path: str) -> FileOpResult:
        """Retire un dossier de la liste des dossiers autorisés.

        Args:
            path: Chemin du dossier à retirer.

        Returns:
            FileOpResult indiquant le succès de l'opération.
        """
        start = time.time()

        try:
            resolved = os.path.abspath(os.path.expanduser(path))
            normalized = resolved.rstrip("/") + "/"

            with self._auth_lock:
                if normalized in self._authorized_dirs:
                    self._authorized_dirs.discard(normalized)
                    duration = (time.time() - start) * 1000
                    return FileOpResult(
                        success=True,
                        message=f"Dossier retiré des autorisés: {resolved}",
                        path=resolved,
                        details={"deauthorized_path": resolved},
                        duration_ms=duration,
                    )
                else:
                    duration = (time.time() - start) * 1000
                    return FileOpResult(
                        success=False,
                        message=f"Le dossier n'était pas dans la liste des autorisés: {resolved}",
                        path=resolved,
                        error="NotAuthorized",
                        duration_ms=duration,
                    )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return FileOpResult(
                success=False,
                message="Erreur lors du retrait d'autorisation",
                error=str(e),
                duration_ms=duration,
            )

    # ── Security checks ────────────────────────────────────────

    def check_path_safety(self, path: str) -> tuple[PathSafety, str]:
        """Évalue le niveau de danger d'un chemin fichier.

        Analyse le chemin pour déterminer s'il est dans le workspace,
        dans un dossier autorisé, système, bloqué, ou hors scope.

        Args:
            path: Chemin à évaluer.

        Returns:
            Tuple (niveau de sécurité, description).
        """
        if not path or not path.strip():
            return PathSafety.OUTSIDE, "Chemin vide"

        try:
            resolved = os.path.abspath(os.path.expanduser(path))
        except (ValueError, OSError):
            return PathSafety.OUTSIDE, "Chemin invalide"

        # 1. Vérification blocklist (correspondance exacte ou préfixe)
        for prefix in SYSTEM_PATH_PREFIXES:
            if resolved.startswith(prefix) or resolved == prefix.rstrip("/"):
                # Certains chemins système sont seulement "SYSTEM" (pas bloqués)
                # La blocklist stricte couvre les dossiers critiques
                if self._is_blocked_path(resolved):
                    return PathSafety.BLOCKED, (
                        f"Chemin bloqué: {resolved} "
                        f"(dossier système interdit)"
                    )
                return PathSafety.SYSTEM, (
                    f"Chemin système: {resolved}"
                )

        # 2. Vérification workspace
        ws_norm = os.path.abspath(self._workspace_root).rstrip("/") + "/"
        if resolved.startswith(ws_norm):
            return PathSafety.WORKSPACE, f"Dans le workspace: {resolved}"

        # 3. Vérification dossiers autorisés
        with self._auth_lock:
            for auth_dir in self._authorized_dirs:
                if resolved.startswith(auth_dir):
                    return PathSafety.AUTHORIZED, (
                        f"Dans un dossier autorisé: {resolved}"
                    )

        # 4. Hors scope
        return PathSafety.OUTSIDE, (
            f"Chemin hors workspace: {resolved} "
            f"(besoin d'autorisation)"
        )

    def _is_blocked_path(self, resolved: str) -> bool:
        """Vérifie si un chemin résolu est dans la blocklist stricte.

        Chemins totalement interdits d'accès.

        Args:
            resolved: Chemin absolu normalisé.

        Returns:
            True si le chemin est bloqué.
        """
        blocked_dirs: tuple[str, ...] = (
            os.path.abspath(os.path.expanduser(d))
            for d in (
                "/.ssh", "~/.ssh",
                "/.gnupg", "~/.gnupg",
                "/etc",
                "/dev",
                "/proc",
                "/sys",
                "/.Trash", "~/.Trash",
                "/Library/Keychains", "~/Library/Keychains",
                "/var/db",
                "/var/root",
            )
        )
        for blocked in blocked_dirs:
            if resolved == blocked.rstrip("/") or resolved.startswith(blocked + "/"):
                return True
        return False

    def resolve_path(self, path: str) -> str:
        """Résout un chemin (relatif → workspace, absolu → normalisé).

        Si le chemin est relatif, il est résolu dans le workspace.
        Les chemins absolus sont utilisés tels quels après normalisation.

        Args:
            path: Chemin à résoudre (relatif ou absolu).

        Returns:
            Chemin absolu normalisé.

        Raises:
            ValueError: Si le chemin est vide, invalide, ou traversal.
            PermissionError: Si le chemin est dans la blocklist.
        """
        if not path or not path.strip():
            raise ValueError("Chemin vide")

        # Nettoyer le chemin
        clean = path.strip()

        # Détection de path traversal
        if self._has_path_traversal(clean):
            raise ValueError(
                f"Path traversal détecté: {clean}"
            )

        # Résoudre ~
        expanded = os.path.expanduser(clean)

        # Si chemin absolu, normaliser directement
        if os.path.isabs(expanded):
            resolved = os.path.normpath(expanded)
        else:
            # Relatif → résoudre dans le workspace
            resolved = os.path.normpath(
                os.path.join(self._workspace_root, expanded)
            )

        # Vérifier le niveau de sécurité
        safety, reason = self.check_path_safety(resolved)
        if safety == PathSafety.BLOCKED:
            raise PermissionError(reason)

        return resolved

    def _has_path_traversal(self, path: str) -> bool:
        """Détecte les tentatives de path traversal.

        Vérifie les patterns comme ../, ..\\, %2e%2e/, ..., etc.

        Args:
            path: Chemin à inspecter.

        Returns:
            True si un traversal est détecté.
        """
        # Patterns de traversal directs
        traversal_patterns = [
            r"\.\./",           # ../
            r"\.\.\\",          # ..\\ (Windows)
            r"\.\.[/\\]",       # .. suivi de séparateur
            r"%2e%2e[/\\]",     # URL-encoded ../
            r"%252e%252e[/\\]", # Double-encoded ../
            r"\.\.%00",         # Null byte + ..
        ]
        low = path.lower()
        for pattern in traversal_patterns:
            if re.search(pattern, low):
                return True

        # Vérification via normalisation
        try:
            # Si le chemin normalisé est plus court que l'original
            # et contient '..', c'est un traversal
            normalized = os.path.normpath(path)
            if ".." in normalized.split(os.sep):
                return True
        except (ValueError, OSError):
            return True

        return False

    # ── CRUD core ──────────────────────────────────────────────

    def read_file(
        self,
        filepath: str,
        encoding: str = "utf-8",
        offset: int | None = None,
        limit: int | None = None,
    ) -> FileOpResult:
        """Lit le contenu d'un fichier.

        Args:
            filepath: Chemin du fichier à lire.
            encoding: Encodage du fichier (défaut: utf-8).
            offset: Nombre de lignes à ignorer depuis le début.
            limit: Nombre maximum de lignes à lire.

        Returns:
            FileOpResult avec le contenu dans details["content"].
        """
        start = time.time()
        bus = EventBus()
        path_str = ""

        try:
            path_str = self.resolve_path(filepath)
            resolved = Path(path_str)

            if not resolved.exists():
                duration = (time.time() - start) * 1000
                bus.emit_sync("file:error", {
                    "operation": "read",
                    "path": filepath,
                    "error": "FileNotFound",
                })
                return FileOpResult(
                    success=False,
                    message=f"Fichier non trouvé: {path_str}",
                    path=path_str,
                    error="FileNotFound",
                    duration_ms=duration,
                )

            if not resolved.is_file():
                duration = (time.time() - start) * 1000
                return FileOpResult(
                    success=False,
                    message=f"Le chemin n'est pas un fichier: {path_str}",
                    path=path_str,
                    error="NotAFile",
                    duration_ms=duration,
                )

            # Vérifier les permissions
            if not os.access(str(resolved), os.R_OK):
                duration = (time.time() - start) * 1000
                return FileOpResult(
                    success=False,
                    message=f"Permission refusée: {path_str}",
                    path=path_str,
                    error="PermissionDenied",
                    duration_ms=duration,
                )

            # Lire le contenu
            try:
                content = resolved.read_text(encoding=encoding)
            except UnicodeDecodeError:
                # Fallback: lecture binaire
                try:
                    content = resolved.read_text(encoding="latin-1")
                    encoding = "latin-1"
                except Exception as e2:
                    duration = (time.time() - start) * 1000
                    return FileOpResult(
                        success=False,
                        message=f"Impossible de décoder le fichier: {e2}",
                        path=path_str,
                        error="EncodingError",
                        duration_ms=duration,
                    )

            # Appliquer offset/limit
            lines = content.splitlines(keepends=True)
            total_lines = len(lines)
            if offset is not None:
                lines = lines[offset:]
            if limit is not None:
                lines = lines[:limit]
            result_content = "".join(lines)
            read_lines = len(lines)

            stats = resolved.stat()
            duration = (time.time() - start) * 1000

            bus.emit_sync("file:read:complete", {
                "path": path_str,
                "size_bytes": stats.st_size,
                "encoding": encoding,
            })

            return FileOpResult(
                success=True,
                message=(
                    f"Fichier lu: {resolved.name} "
                    f"({read_lines}/{total_lines} lignes, "
                    f"{stats.st_size} octets)"
                ),
                path=path_str,
                details={
                    "content": result_content,
                    "size_bytes": stats.st_size,
                    "lines": read_lines,
                    "total_lines": total_lines,
                    "encoding": encoding,
                    "offset": offset,
                    "limit": limit,
                    "modified_at": stats.st_mtime,
                },
                duration_ms=duration,
            )

        except ValueError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "read",
                "path": filepath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Chemin invalide: {e}",
                path=path_str or filepath,
                error=str(e),
                duration_ms=duration,
            )
        except PermissionError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:blocked", {
                "operation": "read",
                "path": filepath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Accès refusé: {e}",
                path=path_str or filepath,
                error=str(e),
                duration_ms=duration,
            )
        except OSError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "read",
                "path": filepath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Erreur fichier: {e}",
                path=path_str or filepath,
                error=str(e),
                duration_ms=duration,
            )

    def write_file(
        self,
        filepath: str,
        content: str,
        encoding: str = "utf-8",
    ) -> FileOpResult:
        """Écrit du contenu dans un fichier (crée ou remplace).

        Args:
            filepath: Chemin du fichier à écrire.
            content: Contenu à écrire.
            encoding: Encodage (défaut: utf-8).

        Returns:
            FileOpResult indiquant le succès de l'écriture.
        """
        start = time.time()
        bus = EventBus()
        path_str = ""

        try:
            path_str = self.resolve_path(filepath)
            resolved = Path(path_str)

            # Crée les dossiers parent si nécessaire
            resolved.parent.mkdir(parents=True, exist_ok=True)

            # Écrire le contenu
            resolved.write_text(content, encoding=encoding)

            stats = resolved.stat()
            duration = (time.time() - start) * 1000

            bus.emit_sync("file:write:complete", {
                "path": path_str,
                "size_bytes": stats.st_size,
                "encoding": encoding,
            })

            return FileOpResult(
                success=True,
                message=(
                    f"Fichier écrit: {resolved.name} "
                    f"({stats.st_size} octets)"
                ),
                path=path_str,
                details={
                    "size_bytes": stats.st_size,
                    "encoding": encoding,
                    "lines": len(content.splitlines()),
                },
                duration_ms=duration,
            )

        except ValueError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "write",
                "path": filepath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Chemin invalide: {e}",
                path=path_str or filepath,
                error=str(e),
                duration_ms=duration,
            )
        except PermissionError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:blocked", {
                "operation": "write",
                "path": filepath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Accès refusé: {e}",
                path=path_str or filepath,
                error=str(e),
                duration_ms=duration,
            )
        except OSError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "write",
                "path": filepath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Erreur fichier: {e}",
                path=path_str or filepath,
                error=str(e),
                duration_ms=duration,
            )

    def append_file(
        self,
        filepath: str,
        content: str,
        encoding: str = "utf-8",
    ) -> FileOpResult:
        """Ajoute du contenu à la fin d'un fichier.

        Args:
            filepath: Chemin du fichier.
            content: Contenu à ajouter.
            encoding: Encodage (défaut: utf-8).

        Returns:
            FileOpResult indiquant le succès de l'opération.
        """
        start = time.time()
        bus = EventBus()
        path_str = ""

        try:
            path_str = self.resolve_path(filepath)
            resolved = Path(path_str)

            # Crée les dossiers parent si nécessaire
            resolved.parent.mkdir(parents=True, exist_ok=True)

            # Ajouter le contenu
            with open(str(resolved), "a", encoding=encoding) as f:
                f.write(content)

            stats = resolved.stat()
            duration = (time.time() - start) * 1000

            bus.emit_sync("file:write:complete", {
                "path": path_str,
                "operation": "append",
                "size_bytes": stats.st_size,
            })

            return FileOpResult(
                success=True,
                message=(
                    f"Contenu ajouté à: {resolved.name} "
                    f"({stats.st_size} octets)"
                ),
                path=path_str,
                details={
                    "size_bytes": stats.st_size,
                    "appended_bytes": len(content.encode(encoding)),
                },
                duration_ms=duration,
            )

        except ValueError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "append",
                "path": filepath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Chemin invalide: {e}",
                path=path_str or filepath,
                error=str(e),
                duration_ms=duration,
            )
        except PermissionError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:blocked", {
                "operation": "append",
                "path": filepath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Accès refusé: {e}",
                path=path_str or filepath,
                error=str(e),
                duration_ms=duration,
            )
        except OSError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "append",
                "path": filepath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Erreur fichier: {e}",
                path=path_str or filepath,
                error=str(e),
                duration_ms=duration,
            )

    def delete_file(
        self,
        filepath: str,
        secure: bool = False,
    ) -> FileOpResult:
        """Supprime un fichier.

        Nécessite le niveau d'accès >= 3 (opération destructive).
        Les chemins hors workspace nécessitent une approbation.

        Args:
            filepath: Chemin du fichier à supprimer.
            secure: Si True, écrase le fichier avant suppression.

        Returns:
            FileOpResult indiquant le succès de la suppression.
        """
        start = time.time()
        bus = EventBus()
        path_str = ""

        try:
            path_str = self.resolve_path(filepath)
            resolved = Path(path_str)

            if not resolved.exists():
                duration = (time.time() - start) * 1000
                return FileOpResult(
                    success=False,
                    message=f"Fichier non trouvé: {path_str}",
                    path=path_str,
                    error="FileNotFound",
                    duration_ms=duration,
                )

            if not resolved.is_file():
                duration = (time.time() - start) * 1000
                return FileOpResult(
                    success=False,
                    message=f"Le chemin n'est pas un fichier: {path_str}",
                    path=path_str,
                    error="NotAFile",
                    duration_ms=duration,
                )

            # Vérification du niveau de sécurité
            if self.get_safety_level() < DESTRUCTIVE_ACCESS_LEVEL:
                duration = (time.time() - start) * 1000
                return FileOpResult(
                    success=False,
                    message=(
                        f"Suppression refusée: niveau d'accès insuffisant "
                        f"({self.get_safety_level()} < {DESTRUCTIVE_ACCESS_LEVEL}). "
                        f"Passez en profil 'power' ou 'admin' pour supprimer."
                    ),
                    path=path_str,
                    error="AccessLevelTooLow",
                    details={"required_level": DESTRUCTIVE_ACCESS_LEVEL},
                    duration_ms=duration,
                )

            # Vérification sécurité du chemin
            safety, reason = self.check_path_safety(path_str)
            if safety != PathSafety.WORKSPACE:
                duration = (time.time() - start) * 1000
                return FileOpResult(
                    success=False,
                    message=(
                        f"Suppression hors workspace nécessite approbation. "
                        f"Safety={safety}: {reason}"
                    ),
                    path=path_str,
                    error="RequiresApproval",
                    details={"safety": str(safety), "reason": reason},
                    duration_ms=duration,
                )

            # Suppression sécurisée (écrasement)
            if secure:
                try:
                    stat_info = resolved.stat()
                    length = stat_info.st_size
                    # Écrire des zéros
                    with open(str(resolved), "wb") as f:
                        f.write(b"\x00" * length)
                    logger.debug("Écrasement sécurisé: %s (%d octets)", path_str, length)
                except OSError as e:
                    logger.warning("Écrasement sécurisé impossible: %s", e)

            # Suppression
            resolved.unlink()
            duration = (time.time() - start) * 1000

            bus.emit_sync("file:delete:complete", {
                "path": path_str,
                "secure": secure,
            })

            return FileOpResult(
                success=True,
                message=f"Fichier supprimé: {resolved.name}",
                path=path_str,
                details={"secure": secure},
                duration_ms=duration,
            )

        except ValueError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "delete",
                "path": filepath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Chemin invalide: {e}",
                path=path_str or filepath,
                error=str(e),
                duration_ms=duration,
            )
        except PermissionError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:blocked", {
                "operation": "delete",
                "path": filepath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Accès refusé: {e}",
                path=path_str or filepath,
                error=str(e),
                duration_ms=duration,
            )
        except OSError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "delete",
                "path": filepath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Erreur suppression: {e}",
                path=path_str or filepath,
                error=str(e),
                duration_ms=duration,
            )

    def move_file(
        self,
        src: str,
        dst: str,
    ) -> FileOpResult:
        """Déplace ou renomme un fichier ou dossier.

        Nécessite le niveau d'accès >= 3 (opération destructive).
        La destination hors workspace nécessite approbation.

        Args:
            src: Chemin source.
            dst: Chemin destination.

        Returns:
            FileOpResult indiquant le succès du déplacement.
        """
        start = time.time()
        bus = EventBus()
        src_path = ""
        dst_path = ""

        try:
            src_path = self.resolve_path(src)
            dst_path = self.resolve_path(dst)

            src_resolved = Path(src_path)
            dst_resolved = Path(dst_path)

            if not src_resolved.exists():
                duration = (time.time() - start) * 1000
                return FileOpResult(
                    success=False,
                    message=f"Source non trouvée: {src_path}",
                    path=src_path,
                    error="SourceNotFound",
                    duration_ms=duration,
                )

            # Vérification du niveau de sécurité
            if self.get_safety_level() < DESTRUCTIVE_ACCESS_LEVEL:
                duration = (time.time() - start) * 1000
                return FileOpResult(
                    success=False,
                    message=(
                        f"Déplacement refusé: niveau d'accès insuffisant "
                        f"({self.get_safety_level()} < {DESTRUCTIVE_ACCESS_LEVEL}). "
                        f"Passez en profil 'power' ou 'admin' pour déplacer."
                    ),
                    path=src_path,
                    error="AccessLevelTooLow",
                    details={"required_level": DESTRUCTIVE_ACCESS_LEVEL},
                    duration_ms=duration,
                )

            # Vérification sécurité des chemins
            src_safety, src_reason = self.check_path_safety(src_path)
            dst_safety, dst_reason = self.check_path_safety(dst_path)

            if src_safety not in (PathSafety.WORKSPACE, PathSafety.AUTHORIZED):
                duration = (time.time() - start) * 1000
                return FileOpResult(
                    success=False,
                    message=(
                        f"Source hors workspace nécessite approbation. "
                        f"Safety={src_safety}: {src_reason}"
                    ),
                    path=src_path,
                    error="RequiresApproval",
                    details={"safety": str(src_safety), "reason": src_reason},
                    duration_ms=duration,
                )

            if dst_safety == PathSafety.OUTSIDE:
                duration = (time.time() - start) * 1000
                return FileOpResult(
                    success=False,
                    message=(
                        f"Destination hors scope nécessite approbation. "
                        f"Safety={dst_safety}: {dst_reason}"
                    ),
                    path=dst_path,
                    error="RequiresApproval",
                    details={"safety": str(dst_safety), "reason": dst_reason},
                    duration_ms=duration,
                )

            # Créer le dossier parent de la destination
            dst_resolved.parent.mkdir(parents=True, exist_ok=True)

            # Déplacer
            src_resolved.rename(dst_resolved)
            duration = (time.time() - start) * 1000

            bus.emit_sync("file:moved", {
                "src": src_path,
                "dst": dst_path,
            })

            return FileOpResult(
                success=True,
                message=(
                    f"Déplacé: {src_resolved.name} → "
                    f"{dst_resolved.name}"
                ),
                path=dst_path,
                details={
                    "source": src_path,
                    "destination": dst_path,
                },
                duration_ms=duration,
            )

        except ValueError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "move",
                "src": src,
                "dst": dst,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Chemin invalide: {e}",
                path=src_path or src,
                error=str(e),
                duration_ms=duration,
            )
        except PermissionError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:blocked", {
                "operation": "move",
                "src": src,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Accès refusé: {e}",
                path=src_path or src,
                error=str(e),
                duration_ms=duration,
            )
        except OSError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "move",
                "src": src,
                "dst": dst,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Erreur déplacement: {e}",
                path=src_path or src,
                error=str(e),
                duration_ms=duration,
            )

    def copy_file(
        self,
        src: str,
        dst: str,
    ) -> FileOpResult:
        """Copie un fichier ou dossier.

        Args:
            src: Chemin source.
            dst: Chemin destination.

        Returns:
            FileOpResult indiquant le succès de la copie.
        """
        start = time.time()
        bus = EventBus()
        import shutil
        src_path = ""
        dst_path = ""

        try:
            src_path = self.resolve_path(src)
            dst_path = self.resolve_path(dst)

            src_resolved = Path(src_path)
            dst_resolved = Path(dst_path)

            if not src_resolved.exists():
                duration = (time.time() - start) * 1000
                return FileOpResult(
                    success=False,
                    message=f"Source non trouvée: {src_path}",
                    path=src_path,
                    error="SourceNotFound",
                    duration_ms=duration,
                )

            # Créer le dossier parent de la destination
            dst_resolved.parent.mkdir(parents=True, exist_ok=True)

            # Copier
            if src_resolved.is_dir():
                shutil.copytree(str(src_resolved), str(dst_resolved), dirs_exist_ok=True)
            else:
                shutil.copy2(str(src_resolved), str(dst_resolved))

            duration = (time.time() - start) * 1000

            bus.emit_sync("file:copied", {
                "src": src_path,
                "dst": dst_path,
            })

            return FileOpResult(
                success=True,
                message=(
                    f"Copié: {src_resolved.name} → "
                    f"{dst_resolved.name}"
                ),
                path=dst_path,
                details={
                    "source": src_path,
                    "destination": dst_path,
                },
                duration_ms=duration,
            )

        except ValueError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "copy",
                "src": src,
                "dst": dst,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Chemin invalide: {e}",
                path=src_path or src,
                error=str(e),
                duration_ms=duration,
            )
        except PermissionError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:blocked", {
                "operation": "copy",
                "src": src,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Accès refusé: {e}",
                path=src_path or src,
                error=str(e),
                duration_ms=duration,
            )
        except (shutil.Error, OSError) as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "copy",
                "src": src,
                "dst": dst,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Erreur copie: {e}",
                path=src_path or src,
                error=str(e),
                duration_ms=duration,
            )

    def create_directory(
        self,
        dirpath: str,
        parents: bool = True,
    ) -> FileOpResult:
        """Crée un dossier.

        Args:
            dirpath: Chemin du dossier à créer.
            parents: Crée les dossiers parent si nécessaire.

        Returns:
            FileOpResult indiquant le succès de la création.
        """
        start = time.time()
        bus = EventBus()
        path_str = ""

        try:
            path_str = self.resolve_path(dirpath)
            resolved = Path(path_str)

            if resolved.exists():
                if resolved.is_dir():
                    duration = (time.time() - start) * 1000
                    return FileOpResult(
                        success=True,
                        message=f"Le dossier existe déjà: {resolved.name}",
                        path=path_str,
                        details={"exists": True},
                        duration_ms=duration,
                    )
                else:
                    duration = (time.time() - start) * 1000
                    return FileOpResult(
                        success=False,
                        message=(
                            f"Un fichier existe déjà à ce chemin: {path_str}"
                        ),
                        path=path_str,
                        error="PathExistsAsFile",
                        duration_ms=duration,
                    )

            # Créer le dossier
            if parents:
                resolved.mkdir(parents=True, exist_ok=True)
            else:
                resolved.mkdir(parents=False, exist_ok=False)

            duration = (time.time() - start) * 1000

            bus.emit_sync("file:mkdir", {
                "path": path_str,
                "parents": parents,
            })

            return FileOpResult(
                success=True,
                message=f"Dossier créé: {resolved.name}",
                path=path_str,
                details={"parents": parents},
                duration_ms=duration,
            )

        except ValueError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "mkdir",
                "path": dirpath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Chemin invalide: {e}",
                path=path_str or dirpath,
                error=str(e),
                duration_ms=duration,
            )
        except PermissionError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:blocked", {
                "operation": "mkdir",
                "path": dirpath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Accès refusé: {e}",
                path=path_str or dirpath,
                error=str(e),
                duration_ms=duration,
            )
        except FileExistsError:
            duration = (time.time() - start) * 1000
            return FileOpResult(
                success=False,
                message=f"Le dossier existe déjà: {path_str}",
                path=path_str or dirpath,
                error="DirectoryExists",
                duration_ms=duration,
            )
        except OSError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "mkdir",
                "path": dirpath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Erreur création dossier: {e}",
                path=path_str or dirpath,
                error=str(e),
                duration_ms=duration,
            )

    def list_directory(
        self,
        dirpath: str,
        recursive: bool = False,
        pattern: str | None = None,
    ) -> FileOpResult:
        """Liste le contenu d'un dossier.

        Args:
            dirpath: Chemin du dossier à lister.
            recursive: Lister récursivement.
            pattern: Filtre par glob pattern (ex: '*.py').

        Returns:
            FileOpResult avec la liste des entrées dans details["entries"].
        """
        start = time.time()
        bus = EventBus()
        path_str = ""

        try:
            path_str = self.resolve_path(dirpath)
            resolved = Path(path_str)

            if not resolved.exists():
                duration = (time.time() - start) * 1000
                return FileOpResult(
                    success=False,
                    message=f"Dossier non trouvé: {path_str}",
                    path=path_str,
                    error="DirectoryNotFound",
                    duration_ms=duration,
                )

            if not resolved.is_dir():
                duration = (time.time() - start) * 1000
                return FileOpResult(
                    success=False,
                    message=f"Le chemin n'est pas un dossier: {path_str}",
                    path=path_str,
                    error="NotADirectory",
                    duration_ms=duration,
                )

            entries: list[dict[str, Any]] = []

            if recursive:
                for item in resolved.rglob("*"):
                    if pattern and not fnmatch.fnmatch(item.name, pattern):
                        continue
                    try:
                        rel = item.relative_to(resolved)
                        stat_info = item.stat()
                        entries.append(self._entry_to_dict(item, rel, stat_info))
                    except OSError:
                        continue
            else:
                for item in resolved.iterdir():
                    if pattern and not fnmatch.fnmatch(item.name, pattern):
                        continue
                    try:
                        stat_info = item.stat()
                        entries.append(self._entry_to_dict(item, item.name, stat_info))
                    except OSError:
                        continue

            # Trier: dossiers puis fichiers, alphabétique
            entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))

            duration = (time.time() - start) * 1000

            return FileOpResult(
                success=True,
                message=(
                    f"Listé: {resolved.name} "
                    f"({len(entries)} entrées)"
                ),
                path=path_str,
                details={
                    "entries": entries,
                    "count": len(entries),
                    "recursive": recursive,
                    "pattern": pattern,
                },
                duration_ms=duration,
            )

        except ValueError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "list",
                "path": dirpath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Chemin invalide: {e}",
                path=path_str or dirpath,
                error=str(e),
                duration_ms=duration,
            )
        except PermissionError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:blocked", {
                "operation": "list",
                "path": dirpath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Accès refusé: {e}",
                path=path_str or dirpath,
                error=str(e),
                duration_ms=duration,
            )
        except OSError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "list",
                "path": dirpath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Erreur liste: {e}",
                path=path_str or dirpath,
                error=str(e),
                duration_ms=duration,
            )

    def _entry_to_dict(
        self,
        item: Path,
        rel_name: str,
        stat_info: os.stat_result,
    ) -> dict[str, Any]:
        """Convertit une entrée de dossier en dictionnaire.

        Args:
            item: Chemin complet de l'entrée.
            rel_name: Nom relatif de l'entrée.
            stat_info: Informations stat du fichier.

        Returns:
            Dict avec les métadonnées de l'entrée.
        """
        return {
            "name": item.name,
            "path": str(item),
            "rel_path": str(rel_name),
            "is_dir": item.is_dir(),
            "is_file": item.is_file(),
            "is_symlink": item.is_symlink(),
            "size_bytes": stat_info.st_size,
            "modified_at": stat_info.st_mtime,
            "created_at": getattr(stat_info, "st_birthtime", None),
        }

    def get_file_info(self, filepath: str) -> FileOpResult:
        """Retourne les informations détaillées d'un fichier ou dossier.

        Args:
            filepath: Chemin du fichier/dossier.

        Returns:
            FileOpResult avec les métadonnées dans details.
        """
        start = time.time()
        bus = EventBus()
        path_str = ""

        try:
            path_str = self.resolve_path(filepath)
            resolved = Path(path_str)

            if not resolved.exists():
                duration = (time.time() - start) * 1000
                return FileOpResult(
                    success=False,
                    message=f"Fichier non trouvé: {path_str}",
                    path=path_str,
                    error="FileNotFound",
                    duration_ms=duration,
                )

            stat_info = resolved.stat()
            is_dir = resolved.is_dir()
            is_file = resolved.is_file()
            is_symlink = resolved.is_symlink()

            details: dict[str, Any] = {
                "name": resolved.name,
                "path": path_str,
                "is_dir": is_dir,
                "is_file": is_file,
                "is_symlink": is_symlink,
                "size_bytes": stat_info.st_size,
                "modified_at": stat_info.st_mtime,
                "accessed_at": stat_info.st_atime,
                "created_at": getattr(stat_info, "st_birthtime", None),
                "permissions": oct(stat_info.st_mode)[-3:],
                "owner_uid": stat_info.st_uid,
                "owner_gid": stat_info.st_gid,
            }

            if is_file:
                try:
                    # Compter les lignes sans tout charger
                    with open(str(resolved), "rb") as f:
                        line_count = sum(1 for _ in f)
                    details["lines"] = line_count
                except OSError:
                    pass

            if is_dir:
                try:
                    details["entries_count"] = len(list(resolved.iterdir()))
                except OSError:
                    pass

            duration = (time.time() - start) * 1000

            return FileOpResult(
                success=True,
                message=(
                    f"Info: {resolved.name} "
                    f"({'dossier' if is_dir else 'fichier'}, "
                    f"{stat_info.st_size} octets)"
                ),
                path=path_str,
                details=details,
                duration_ms=duration,
            )

        except ValueError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "info",
                "path": filepath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Chemin invalide: {e}",
                path=path_str or filepath,
                error=str(e),
                duration_ms=duration,
            )
        except PermissionError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:blocked", {
                "operation": "info",
                "path": filepath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Accès refusé: {e}",
                path=path_str or filepath,
                error=str(e),
                duration_ms=duration,
            )
        except OSError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "info",
                "path": filepath,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Erreur: {e}",
                path=path_str or filepath,
                error=str(e),
                duration_ms=duration,
            )

    # ── Search ──────────────────────────────────────────────────

    def search_files(
        self,
        pattern: str,
        root: str | None = None,
        file_type: str | None = None,
    ) -> FileOpResult:
        """Recherche des fichiers par nom (glob pattern).

        Args:
            pattern: Glob pattern pour filtrer les fichiers (ex: '*.py').
            root: Dossier racine de recherche (défaut: workspace).
            file_type: Filtrer par type ('file', 'dir', 'symlink').

        Returns:
            FileOpResult avec la liste des fichiers trouvés.
        """
        start = time.time()
        bus = EventBus()
        root_path = ""

        try:
            # Racine de recherche
            if root:
                root_path = self.resolve_path(root)
            else:
                root_path = self._workspace_root

            root_resolved = Path(root_path)

            if not root_resolved.exists() or not root_resolved.is_dir():
                duration = (time.time() - start) * 1000
                return FileOpResult(
                    success=False,
                    message=f"Dossier de recherche invalide: {root_path}",
                    path=root_path,
                    error="InvalidSearchRoot",
                    duration_ms=duration,
                )

            results: list[dict[str, Any]] = []

            # Parcourir récursivement
            for item in root_resolved.rglob(pattern):
                try:
                    # Filtrer par type
                    if file_type == "file" and not item.is_file():
                        continue
                    if file_type == "dir" and not item.is_dir():
                        continue
                    if file_type == "symlink" and not item.is_symlink():
                        continue

                    rel = item.relative_to(root_resolved)
                    stat_info = item.stat()
                    results.append({
                        "name": item.name,
                        "path": str(item),
                        "rel_path": str(rel),
                        "is_dir": item.is_dir(),
                        "is_file": item.is_file(),
                        "size_bytes": stat_info.st_size,
                        "modified_at": stat_info.st_mtime,
                    })
                except OSError:
                    continue

            duration = (time.time() - start) * 1000

            return FileOpResult(
                success=True,
                message=(
                    f"Recherche '{pattern}': "
                    f"{len(results)} résultat(s)"
                ),
                path=root_path,
                details={
                    "results": results,
                    "count": len(results),
                    "pattern": pattern,
                    "root": root_path,
                    "file_type": file_type,
                },
                duration_ms=duration,
            )

        except ValueError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "search_files",
                "pattern": pattern,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Chemin invalide: {e}",
                path=root_path or root or "",
                error=str(e),
                duration_ms=duration,
            )
        except PermissionError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:blocked", {
                "operation": "search_files",
                "pattern": pattern,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Accès refusé: {e}",
                path=root_path or root or "",
                error=str(e),
                duration_ms=duration,
            )
        except OSError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "search_files",
                "pattern": pattern,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Erreur recherche: {e}",
                path=root_path or root or "",
                error=str(e),
                duration_ms=duration,
            )

    def search_content(
        self,
        pattern: str,
        root: str | None = None,
        file_glob: str | None = None,
    ) -> FileOpResult:
        """Recherche du contenu texte dans les fichiers.

        Args:
            pattern: Expression régulière à rechercher.
            root: Dossier racine de recherche (défaut: workspace).
            file_glob: Filtre par glob pattern (ex: '*.py').

        Returns:
            FileOpResult avec les correspondances trouvées.
        """
        start = time.time()
        bus = EventBus()
        root_path = ""

        try:
            # Racine de recherche
            if root:
                root_path = self.resolve_path(root)
            else:
                root_path = self._workspace_root

            root_resolved = Path(root_path)

            if not root_resolved.exists() or not root_resolved.is_dir():
                duration = (time.time() - start) * 1000
                return FileOpResult(
                    success=False,
                    message=f"Dossier de recherche invalide: {root_path}",
                    path=root_path,
                    error="InvalidSearchRoot",
                    duration_ms=duration,
                )

            # Compiler la regex
            try:
                regex = re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                duration = (time.time() - start) * 1000
                return FileOpResult(
                    success=False,
                    message=f"Pattern regex invalide: {e}",
                    path=root_path,
                    error="InvalidRegex",
                    duration_ms=duration,
                )

            matches: list[dict[str, Any]] = []
            file_count = 0
            match_count = 0

            # Parcourir les fichiers
            for item in root_resolved.rglob("*"):
                if not item.is_file():
                    continue

                # Filtrer par glob
                if file_glob and not fnmatch.fnmatch(item.name, file_glob):
                    continue

                # Ignorer les fichiers binaires volumineux
                try:
                    if item.stat().st_size > 10 * 1024 * 1024:  # 10 MB
                        continue
                except OSError:
                    continue

                try:
                    content = item.read_text(encoding="utf-8", errors="replace")
                    file_count += 1

                    for line_no, line in enumerate(content.splitlines(), 1):
                        if regex.search(line):
                            rel = item.relative_to(root_resolved)
                            matches.append({
                                "file": str(item),
                                "rel_path": str(rel),
                                "line": line_no,
                                "content": line.strip(),
                            })
                            match_count += 1
                except (OSError, UnicodeDecodeError):
                    continue

            duration = (time.time() - start) * 1000

            return FileOpResult(
                success=True,
                message=(
                    f"Recherche contenu '{pattern}': "
                    f"{match_count} correspondance(s) "
                    f"dans {file_count} fichier(s)"
                ),
                path=root_path,
                details={
                    "matches": matches,
                    "match_count": match_count,
                    "file_count": file_count,
                    "pattern": pattern,
                    "root": root_path,
                    "file_glob": file_glob,
                },
                duration_ms=duration,
            )

        except ValueError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "search_content",
                "pattern": pattern,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Chemin invalide: {e}",
                path=root_path or root or "",
                error=str(e),
                duration_ms=duration,
            )
        except PermissionError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:blocked", {
                "operation": "search_content",
                "pattern": pattern,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Accès refusé: {e}",
                path=root_path or root or "",
                error=str(e),
                duration_ms=duration,
            )
        except OSError as e:
            duration = (time.time() - start) * 1000
            bus.emit_sync("file:error", {
                "operation": "search_content",
                "pattern": pattern,
                "error": str(e),
            })
            return FileOpResult(
                success=False,
                message=f"Erreur recherche contenu: {e}",
                path=root_path or root or "",
                error=str(e),
                duration_ms=duration,
            )


# ── ToolRegistry handlers ───────────────────────────────────────

def register_file_tools(
    registry: ToolRegistry,
    executor: ToolExecutor,
) -> None:
    """Enregistre les 12 outils de gestion fichiers dans le ToolRegistry.

    Outils enregistrés:
    - file_read : Lit un fichier texte.
    - file_write : Écrit/crée un fichier texte.
    - file_append : Ajoute du texte à un fichier.
    - file_delete : Supprime un fichier (nécessite approbation).
    - file_move : Déplace/renomme un fichier (nécessite approbation).
    - file_copy : Copie un fichier ou dossier.
    - file_mkdir : Crée un dossier.
    - file_list : Liste le contenu d'un dossier.
    - file_info : Obtient les métadonnées d'un fichier/dossier.
    - file_search : Recherche des fichiers par nom.
    - file_workspace_info : Obtient les statistiques du workspace.
    - file_authorize_directory : Ajoute un dossier aux autorisés.

    Les handlers sont enregistrés dans le ToolExecutor fourni.

    Args:
        registry: Registre d'outils (ToolRegistry).
        executor: Exécuteur d'outils (ToolExecutor).
    """

    # ── file_read ──────────────────────────────────────────────

    read_def = ToolDefinition(
        name="file_read",
        description=(
            "Lit le contenu d'un fichier texte. "
            "Support offset/limit pour les gros fichiers. "
            "Détecte automatiquement l'encodage (utf-8, latin-1). "
            "Retourne le contenu, la taille, et le nombre de lignes."
        ),
        category="system",
        parameters=[
            ToolParameter(
                name="path",
                type="str",
                description=(
                    "Chemin du fichier à lire. "
                    "Relatif → résolu dans Nuru_Workspace. "
                    "Absolu → utilisé tel quel si autorisé."
                ),
                required=True,
            ),
            ToolParameter(
                name="encoding",
                type="str",
                description=(
                    "Encodage du fichier (défaut: utf-8). "
                    "Utilisez 'latin-1' pour les fichiers legacy."
                ),
                required=False,
                default="utf-8",
            ),
            ToolParameter(
                name="offset",
                type="int",
                description=(
                    "Nombre de lignes à ignorer depuis le début. "
                    "Utile pour la pagination."
                ),
                required=False,
                default=None,
            ),
            ToolParameter(
                name="limit",
                type="int",
                description=(
                    "Nombre maximum de lignes à lire. "
                    "Utile pour les gros fichiers."
                ),
                required=False,
                default=None,
            ),
        ],
    )

    def _read_handler(**kwargs: Any) -> dict:
        ctrl = FileOpsController.get_instance()
        path = kwargs.get("path", "")
        encoding = kwargs.get("encoding", "utf-8")
        offset = kwargs.get("offset")
        limit = kwargs.get("limit")
        result = ctrl.read_file(
            filepath=path,
            encoding=encoding,
            offset=offset,
            limit=limit,
        )
        return result.to_dict()

    registry.register(read_def)
    executor.register_handler("file_read", _read_handler)

    # ── file_write ─────────────────────────────────────────────

    write_def = ToolDefinition(
        name="file_write",
        description=(
            "Écrit du contenu dans un fichier. "
            "Crée le fichier s'il n'existe pas, remplace s'il existe. "
            "Crée automatiquement les dossiers parent."
        ),
        category="system",
        parameters=[
            ToolParameter(
                name="path",
                type="str",
                description="Chemin du fichier à écrire.",
                required=True,
            ),
            ToolParameter(
                name="content",
                type="str",
                description="Contenu à écrire dans le fichier.",
                required=True,
            ),
            ToolParameter(
                name="encoding",
                type="str",
                description="Encodage du fichier (défaut: utf-8).",
                required=False,
                default="utf-8",
            ),
        ],
    )

    def _write_handler(**kwargs: Any) -> dict:
        ctrl = FileOpsController.get_instance()
        path = kwargs.get("path", "")
        content = kwargs.get("content", "")
        encoding = kwargs.get("encoding", "utf-8")
        result = ctrl.write_file(
            filepath=path,
            content=content,
            encoding=encoding,
        )
        return result.to_dict()

    registry.register(write_def)
    executor.register_handler("file_write", _write_handler)

    # ── file_append ────────────────────────────────────────────

    append_def = ToolDefinition(
        name="file_append",
        description=(
            "Ajoute du contenu à la fin d'un fichier existant. "
            "Crée le fichier et ses dossiers parent si nécessaire."
        ),
        category="system",
        parameters=[
            ToolParameter(
                name="path",
                type="str",
                description="Chemin du fichier.",
                required=True,
            ),
            ToolParameter(
                name="content",
                type="str",
                description="Contenu à ajouter à la fin du fichier.",
                required=True,
            ),
            ToolParameter(
                name="encoding",
                type="str",
                description="Encodage (défaut: utf-8).",
                required=False,
                default="utf-8",
            ),
        ],
    )

    def _append_handler(**kwargs: Any) -> dict:
        ctrl = FileOpsController.get_instance()
        path = kwargs.get("path", "")
        content = kwargs.get("content", "")
        encoding = kwargs.get("encoding", "utf-8")
        result = ctrl.append_file(
            filepath=path,
            content=content,
            encoding=encoding,
        )
        return result.to_dict()

    registry.register(append_def)
    executor.register_handler("file_append", _append_handler)

    # ── file_delete ────────────────────────────────────────────

    delete_def = ToolDefinition(
        name="file_delete",
        description=(
            "Supprime un fichier. "
            "REQUIERS APPROBATION — opération destructive. "
            "Nécessite le profil 'power' ou 'admin'. "
            "Ne fonctionne que dans le workspace par défaut."
        ),
        category="system",
        parameters=[
            ToolParameter(
                name="path",
                type="str",
                description="Chemin du fichier à supprimer.",
                required=True,
            ),
            ToolParameter(
                name="secure",
                type="bool",
                description=(
                    "Écraser le fichier avec des zéros avant "
                    "suppression (plus sécurisé, plus lent)."
                ),
                required=False,
                default=False,
            ),
        ],
    )

    def _delete_handler(**kwargs: Any) -> dict:
        ctrl = FileOpsController.get_instance()
        path = kwargs.get("path", "")
        secure = bool(kwargs.get("secure", False))
        result = ctrl.delete_file(
            filepath=path,
            secure=secure,
        )
        return result.to_dict()

    registry.register(delete_def)
    executor.register_handler("file_delete", _delete_handler)

    # ── file_move ──────────────────────────────────────────────

    move_def = ToolDefinition(
        name="file_move",
        description=(
            "Déplace ou renomme un fichier/dossier. "
            "REQUIERS APPROBATION — opération destructive. "
            "Nécessite le profil 'power' ou 'admin'."
        ),
        category="system",
        parameters=[
            ToolParameter(
                name="src",
                type="str",
                description="Chemin source (fichier ou dossier à déplacer).",
                required=True,
            ),
            ToolParameter(
                name="dst",
                type="str",
                description="Chemin destination.",
                required=True,
            ),
        ],
    )

    def _move_handler(**kwargs: Any) -> dict:
        ctrl = FileOpsController.get_instance()
        src = kwargs.get("src", "")
        dst = kwargs.get("dst", "")
        result = ctrl.move_file(src=src, dst=dst)
        return result.to_dict()

    registry.register(move_def)
    executor.register_handler("file_move", _move_handler)

    # ── file_copy ──────────────────────────────────────────────

    copy_def = ToolDefinition(
        name="file_copy",
        description=(
            "Copie un fichier ou dossier vers une destination. "
            "Utilise shutil.copy2 pour préserver les métadonnées. "
            "Pour les dossiers, copie récursivement."
        ),
        category="system",
        parameters=[
            ToolParameter(
                name="src",
                type="str",
                description="Chemin source (fichier ou dossier).",
                required=True,
            ),
            ToolParameter(
                name="dst",
                type="str",
                description="Chemin destination.",
                required=True,
            ),
        ],
    )

    def _copy_handler(**kwargs: Any) -> dict:
        ctrl = FileOpsController.get_instance()
        src = kwargs.get("src", "")
        dst = kwargs.get("dst", "")
        result = ctrl.copy_file(src=src, dst=dst)
        return result.to_dict()

    registry.register(copy_def)
    executor.register_handler("file_copy", _copy_handler)

    # ── file_mkdir ─────────────────────────────────────────────

    mkdir_def = ToolDefinition(
        name="file_mkdir",
        description=(
            "Crée un nouveau dossier. "
            "Crée automatiquement les dossiers parent. "
            "Ne fait rien si le dossier existe déjà."
        ),
        category="system",
        parameters=[
            ToolParameter(
                name="path",
                type="str",
                description="Chemin du dossier à créer.",
                required=True,
            ),
            ToolParameter(
                name="parents",
                type="bool",
                description=(
                    "Créer les dossiers parent si nécessaire "
                    "(comme mkdir -p)."
                ),
                required=False,
                default=True,
            ),
        ],
    )

    def _mkdir_handler(**kwargs: Any) -> dict:
        ctrl = FileOpsController.get_instance()
        path = kwargs.get("path", "")
        parents = kwargs.get("parents", True)
        result = ctrl.create_directory(dirpath=path, parents=parents)
        return result.to_dict()

    registry.register(mkdir_def)
    executor.register_handler("file_mkdir", _mkdir_handler)

    # ── file_list ──────────────────────────────────────────────

    list_def = ToolDefinition(
        name="file_list",
        description=(
            "Liste le contenu d'un dossier. "
            "Support récursif et filtrage par glob pattern. "
            "Retourne les entrées triées (dossiers puis fichiers)."
        ),
        category="system",
        parameters=[
            ToolParameter(
                name="path",
                type="str",
                description="Chemin du dossier à lister (défaut: workspace).",
                required=True,
            ),
            ToolParameter(
                name="recursive",
                type="bool",
                description="Lister récursivement tous les sous-dossiers.",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="pattern",
                type="str",
                description=(
                    "Filtre par nom (glob pattern). "
                    "Ex: '*.py' pour les fichiers Python."
                ),
                required=False,
                default=None,
            ),
        ],
    )

    def _list_handler(**kwargs: Any) -> dict:
        ctrl = FileOpsController.get_instance()
        path = kwargs.get("path", "")
        recursive = bool(kwargs.get("recursive", False))
        pattern = kwargs.get("pattern")
        result = ctrl.list_directory(
            dirpath=path,
            recursive=recursive,
            pattern=pattern,
        )
        return result.to_dict()

    registry.register(list_def)
    executor.register_handler("file_list", _list_handler)

    # ── file_info ──────────────────────────────────────────────

    info_def = ToolDefinition(
        name="file_info",
        description=(
            "Obtient les informations détaillées d'un fichier ou dossier. "
            "Retourne taille, permissions, dates, type, nombre de lignes."
        ),
        category="system",
        parameters=[
            ToolParameter(
                name="path",
                type="str",
                description="Chemin du fichier ou dossier.",
                required=True,
            ),
        ],
    )

    def _info_handler(**kwargs: Any) -> dict:
        ctrl = FileOpsController.get_instance()
        path = kwargs.get("path", "")
        result = ctrl.get_file_info(filepath=path)
        return result.to_dict()

    registry.register(info_def)
    executor.register_handler("file_info", _info_handler)

    # ── file_search ────────────────────────────────────────────

    search_def = ToolDefinition(
        name="file_search",
        description=(
            "Recherche des fichiers par nom (glob pattern). "
            "Parcourt récursivement le dossier spécifié. "
            "Peut filtrer par type (fichier/dossier/symlink)."
        ),
        category="system",
        parameters=[
            ToolParameter(
                name="pattern",
                type="str",
                description=(
                    "Glob pattern pour filtrer les noms de fichiers. "
                    "Ex: '*.py', '*config*', '*.{txt,md}'"
                ),
                required=True,
            ),
            ToolParameter(
                name="root",
                type="str",
                description=(
                    "Dossier racine de la recherche "
                    "(défaut: Nuru_Workspace)."
                ),
                required=False,
                default=None,
            ),
            ToolParameter(
                name="file_type",
                type="str",
                description=(
                    "Filtrer par type: 'file', 'dir', ou 'symlink' "
                    "(défaut: tous les types)."
                ),
                required=False,
                default=None,
            ),
        ],
    )

    def _search_handler(**kwargs: Any) -> dict:
        ctrl = FileOpsController.get_instance()
        pattern = kwargs.get("pattern", "")
        root = kwargs.get("root")
        file_type = kwargs.get("file_type")
        result = ctrl.search_files(
            pattern=pattern,
            root=root,
            file_type=file_type,
        )
        return result.to_dict()

    registry.register(search_def)
    executor.register_handler("file_search", _search_handler)

    # ── file_workspace_info ────────────────────────────────────

    ws_def = ToolDefinition(
        name="file_workspace_info",
        description=(
            "Obtient les statistiques complètes du workspace "
            "Nuru_Workspace : taille, nombre de fichiers, "
            "sous-dossiers, dossiers autorisés, profil de sécurité."
        ),
        category="system",
        parameters=[],
    )

    def _ws_handler(**kwargs: Any) -> dict:
        ctrl = FileOpsController.get_instance()
        result = ctrl.get_workspace_info()
        return result.to_dict()

    registry.register(ws_def)
    executor.register_handler("file_workspace_info", _ws_handler)

    # ── file_authorize_directory ───────────────────────────────

    auth_def = ToolDefinition(
        name="file_authorize_directory",
        description=(
            "Ajoute un dossier à la liste des dossiers autorisés. "
            "Permet au contrôleur fichiers d'accéder à des dossiers "
            "en dehors du workspace par défaut. "
            "Ne peut pas autoriser les dossiers système."
        ),
        category="system",
        parameters=[
            ToolParameter(
                name="path",
                type="str",
                description=(
                    "Chemin absolu du dossier à autoriser. "
                    "Le dossier doit exister."
                ),
                required=True,
            ),
        ],
    )

    def _auth_handler(**kwargs: Any) -> dict:
        ctrl = FileOpsController.get_instance()
        path = kwargs.get("path", "")
        result = ctrl.authorize_directory(path=path)
        return result.to_dict()

    registry.register(auth_def)
    executor.register_handler("file_authorize_directory", _auth_handler)

    logger.info("12 outils fichiers enregistrés dans le ToolRegistry")
