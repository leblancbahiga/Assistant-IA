"""Contrôle du système d'exploitation macOS — Applications, fenêtres,
paramètres système, simulation clavier/souris.

Classes:
    AppAction: Actions disponibles sur les applications.
    WindowAction: Actions disponibles sur les fenêtres.
    SystemControlType: Contrôles système disponibles.
    AppResult: Résultat standard d'une opération OS.
    WindowInfo: Informations sur une fenêtre.
    AppInfo: Informations sur une application détectée.
    OSController: Contrôleur OS singleton (macOS).

Fonctions:
    register_os_tools: Enregistre les outils OS dans le registre.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any

from src.core.events import EventBus
from src.tools.registry import ToolDefinition, ToolParameter, ToolExecutor, ToolRegistry

logger = logging.getLogger(__name__)

# ── Constantes ──────────────────────────────────────────────────

DEFAULT_OSASCRIPT_TIMEOUT: int = 15
MAX_SCAN_DEPTH: int = 3
APP_RESULT_TIMEOUT: float = 3.0

# Chemins de scan pour discover_apps()
APP_PATHS: list[str] = [
    "/Applications",
    "~/Applications",
    "/System/Applications",
    "/System/Library/CoreServices",
]


# ── Enums ────────────────────────────────────────────────────────


class AppAction(IntEnum):
    """Actions disponibles sur les applications.

    Values:
        OPEN (0): Ouvre l'application.
        CLOSE (1): Ferme l'application.
        FOCUS (2): Amène au premier plan.
        HIDE (3): Cache l'application.
        QUIT (4): Quitte proprement.
        FORCE_QUIT (5): Forcer la fermeture.
        LAUNCH (6): Lance sans amener au premier plan.
        ACTIVATE (7): Active (ouvre ou amène au premier plan).
    """

    OPEN = 0
    CLOSE = 1
    FOCUS = 2
    HIDE = 3
    QUIT = 4
    FORCE_QUIT = 5
    LAUNCH = 6
    ACTIVATE = 7


class WindowAction(IntEnum):
    """Actions disponibles sur les fenêtres.

    Values:
        LIST (0): Liste les fenêtres.
        MOVE (1): Déplace la fenêtre.
        RESIZE (2): Redimensionne la fenêtre.
        MINIMIZE (3): Minimise la fenêtre.
        MAXIMIZE (4): Maximise la fenêtre.
        CLOSE (5): Ferme la fenêtre.
        TILE_LEFT (6): Aligne à gauche (1/2 écran).
        TILE_RIGHT (7): Aligne à droite (1/2 écran).
        TILE_TOP_LEFT (8): Coin supérieur gauche.
        TILE_TOP_RIGHT (9): Coin supérieur droit.
        TILE_BOTTOM_LEFT (10): Coin inférieur gauche.
        TILE_BOTTOM_RIGHT (11): Coin inférieur droit.
        TILE_FULL (12): Plein écran.
        TILE_CENTER (13): Centre (1/3 écran).
    """

    LIST = 0
    MOVE = 1
    RESIZE = 2
    MINIMIZE = 3
    MAXIMIZE = 4
    CLOSE = 5
    TILE_LEFT = 6
    TILE_RIGHT = 7
    TILE_TOP_LEFT = 8
    TILE_TOP_RIGHT = 9
    TILE_BOTTOM_LEFT = 10
    TILE_BOTTOM_RIGHT = 11
    TILE_FULL = 12
    TILE_CENTER = 13


class SystemControlType(IntEnum):
    """Contrôles système disponibles.

    Values:
        VOLUME_GET (0): Récupère le volume.
        VOLUME_SET (1): Définit le volume.
        MUTE (2): Coupe le son.
        UNMUTE (3): Rétablit le son.
        TOGGLE_MUTE (4): Bascule muet.
        BRIGHTNESS_GET (5): Récupère la luminosité.
        BRIGHTNESS_SET (6): Définit la luminosité.
        LOCK_SCREEN (7): Verrouille l'écran.
        SLEEP_DISPLAY (8): Met l'écran en veille.
        SCREENSAVER (9): Active l'économiseur d'écran.
        EMPTY_TRASH (10): Vide la corbeille.
        SYSTEM_INFO (11): Récupère les infos système.
    """

    VOLUME_GET = 0
    VOLUME_SET = 1
    MUTE = 2
    UNMUTE = 3
    TOGGLE_MUTE = 4
    BRIGHTNESS_GET = 5
    BRIGHTNESS_SET = 6
    LOCK_SCREEN = 7
    SLEEP_DISPLAY = 8
    SCREENSAVER = 9
    EMPTY_TRASH = 10
    SYSTEM_INFO = 11


# ── Dataclasses ──────────────────────────────────────────────────


@dataclass
class AppResult:
    """Résultat standard d'une opération OS.

    Attributes:
        success: L'opération a réussi.
        data: Données additionnelles (liste, dict, etc.).
        error: Message d'erreur si échec.
        duration_ms: Durée d'exécution en millisecondes.
    """

    success: bool
    data: Any = None
    error: str | None = None
    duration_ms: float = 0.0


@dataclass
class WindowInfo:
    """Informations sur une fenêtre macOS.

    Attributes:
        app_name: Nom de l'application propriétaire.
        title: Titre de la fenêtre.
        x: Position X en pixels.
        y: Position Y en pixels.
        width: Largeur en pixels.
        height: Hauteur en pixels.
        minimized: La fenêtre est minimisée.
        focused: La fenêtre est au premier plan.
        window_id: Identifiant interne de la fenêtre.
    """

    app_name: str
    title: str
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    minimized: bool = False
    focused: bool = False
    window_id: int = 0


@dataclass
class AppInfo:
    """Informations sur une application macOS détectée.

    Attributes:
        name: Nom affiché de l'application.
        path: Chemin absolu du bundle .app.
        bundle_id: Identifiant de bundle (CFBundleIdentifier).
        version: Version de l'application.
        is_running: L'application est en cours d'exécution.
        pid: Identifiant de processus (si en cours).
    """

    name: str
    path: str
    bundle_id: str = ""
    version: str = ""
    is_running: bool = False
    pid: int = 0


# ── OSController ────────────────────────────────────────────────


class OSController:
    """Contrôleur OS singleton pour macOS.

    Fournit des méthodes unifiées pour :
    - Gestion des applications (ouvrir, fermer, focus, etc.)
    - Gestion des fenêtres (déplacer, redimensionner, tuiles)
    - Contrôles système (volume, luminosité, écran)
    - Simulation entrées (clavier, souris, clics)
    - Exécution AppleScript filtré

    Utilise AppleScript pour l'interaction avec le système et PyAutoGUI
    (en dépendance optionnelle) pour la simulation d'entrées.

    Utilisation::

        ctrl = OSController.get_instance()
        result = ctrl.open_app("Safari")
        if result.success:
            print("Safari ouvert")
    """

    _instance: OSController | None = None
    _singleton_lock: threading.Lock = threading.Lock()
    _initialized: bool = False

    def __new__(cls, *args: Any, **kwargs: Any) -> OSController:
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
        self._app_cache: dict[str, AppInfo] = {}
        self._cache_lock = threading.Lock()
        self._screen_size: tuple[int, int] | None = None
        logger.debug("OSController initialisé")

    # ── Singleton helper ──

    @classmethod
    def get_instance(cls) -> OSController:
        """Retourne l'instance unique du contrôleur OS.

        Returns:
            L'instance unique d'OSController.
        """
        return cls()

    # ── Découverte des applications ──

    def discover_apps(self) -> dict[str, AppInfo]:
        """Scanne les dossiers systèmes pour trouver les applications macOS.

        Parcourt /Applications, ~/Applications, /System/Applications
        et /System/Library/CoreServices à la recherche de bundles .app.
        Met à jour le cache interne.

        Returns:
            Dictionnaire {nom: AppInfo} des applications découvertes.
        """
        start = time.time()
        apps: dict[str, AppInfo] = {}

        for path_pattern in APP_PATHS:
            directory = os.path.expanduser(path_pattern)
            if not os.path.isdir(directory):
                continue
            try:
                self._scan_app_dir(directory, apps, depth=0)
            except PermissionError:
                logger.debug("Permission refusée: %s", directory)
                continue
            except OSError as e:
                logger.warning("Erreur scan %s: %s", directory, e)
                continue

        duration = (time.time() - start) * 1000
        logger.info(
            "Découverte: %d applications en %.0f ms", len(apps), duration
        )

        with self._cache_lock:
            self._app_cache = apps

        return apps

    def _scan_app_dir(
        self,
        directory: str,
        apps: dict[str, AppInfo],
        depth: int = 0,
    ) -> None:
        """Scanne récursivement un dossier pour les applications.

        Args:
            directory: Chemin du dossier à scanner.
            apps: Dictionnaire à remplir (nom -> AppInfo).
            depth: Profondeur actuelle (évite les récursions infinies).
        """
        if depth > MAX_SCAN_DEPTH:
            return
        try:
            for entry in os.scandir(directory):
                if entry.is_dir():
                    if entry.name.endswith(".app"):
                        info = self._parse_app_bundle(entry.path)
                        if info:
                            apps[info.name] = info
                    elif depth < MAX_SCAN_DEPTH:
                        self._scan_app_dir(entry.path, apps, depth + 1)
        except PermissionError:
            pass
        except OSError:
            pass

    def _parse_app_bundle(self, path: str) -> AppInfo | None:
        """Extrait les informations d'un bundle .app.

        Lit le fichier Info.plist pour obtenir le nom, le bundle ID
        et la version de l'application.

        Args:
            path: Chemin absolu du bundle .app.

        Returns:
            AppInfo si le bundle est valide, None sinon.
        """
        try:
            plist_path = os.path.join(path, "Contents", "Info.plist")
            if not os.path.isfile(plist_path):
                # Essayer de prendre le nom du dossier
                name = os.path.splitext(os.path.basename(path))[0]
                return AppInfo(name=name, path=path)

            # Lire le plist avec AppleScript ou plutil
            result = subprocess.run(
                [
                    "plutil",
                    "-convert",
                    "json",
                    "-o",
                    "-",
                    plist_path,
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                name = os.path.splitext(os.path.basename(path))[0]
                return AppInfo(name=name, path=path)

            import json as json_mod

            plist_data = json_mod.loads(result.stdout)
            name = plist_data.get(
                "CFBundleDisplayName",
                plist_data.get(
                    "CFBundleName",
                    os.path.splitext(os.path.basename(path))[0],
                ),
            )
            bundle_id = plist_data.get("CFBundleIdentifier", "")
            version = plist_data.get(
                "CFBundleShortVersionString",
                plist_data.get("CFBundleVersion", ""),
            )
            return AppInfo(
                name=name,
                path=path,
                bundle_id=bundle_id,
                version=version,
            )
        except Exception as e:
            logger.debug("Erreur parsing bundle %s: %s", path, e)
            name = os.path.splitext(os.path.basename(path))[0]
            return AppInfo(name=name, path=path)

    # ── Gestion des applications ──

    def list_running_apps(self) -> AppResult:
        """Liste les applications en cours d'exécution (hors processus d'arrière-plan).

        Utilise AppleScript pour interroger System Events.

        Returns:
            AppResult avec data=liste de noms d'applications.
        """
        script = (
            'tell application "System Events"\n'
            "    set appList to (name of every process whose background only is false)\n"
            "    return appList\n"
            "end tell"
        )
        return self._run_osascript_result(script)

    def open_app(
        self, name: str, path: str | None = None, wait: float = 3.0
    ) -> AppResult:
        """Ouvre ou active une application.

        Tente d'abord 'tell app "X" to activate', puis 'open -a "X"'
        en fallback.

        Args:
            name: Nom de l'application.
            path: Chemin optionnel (utilisé si l'activation par nom échoue).
            wait: Temps d'attente en secondes après ouverture.

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        bus = EventBus()

        # Essai par AppleScript
        script = f'tell application "{self._escape_applescript_string(name)}" to activate'
        result = self._run_osascript(script, timeout=int(wait + 2))
        duration = (time.time() - start) * 1000

        if result.returncode == 0:
            time.sleep(wait)
            bus.emit_sync("os:app:opened", {"name": name})
            return AppResult(
                success=True,
                data={"name": name, "method": "applescript"},
                duration_ms=duration,
            )

        # Fallback: open -a
        if path:
            open_path = path
        else:
            with self._cache_lock:
                cached = self._app_cache.get(name)
            open_path = cached.path if cached else ""

        if open_path:
            try:
                subprocess.run(
                    ["open", "-a", open_path],
                    capture_output=True,
                    text=True,
                    timeout=int(wait + 2),
                )
                time.sleep(wait)
                duration = (time.time() - start) * 1000
                bus.emit_sync("os:app:opened", {"name": name})
                return AppResult(
                    success=True,
                    data={"name": name, "method": "open"},
                    duration_ms=duration,
                )
            except subprocess.TimeoutExpired:
                pass
            except Exception as e:
                logger.warning("open -a échoué pour %s: %s", name, e)

        duration = (time.time() - start) * 1000
        return AppResult(
            success=False,
            error=f"Impossible d'ouvrir l'application '{name}'",
            duration_ms=duration,
        )

    def close_app(self, name: str, force: bool = False) -> AppResult:
        """Ferme une application.

        Utilise 'tell app "X" to quit' ou killall en fallback.

        Args:
            name: Nom de l'application.
            force: Forcer la fermeture (killall -9) si True.

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        bus = EventBus()
        escaped = self._escape_applescript_string(name)

        if force:
            # killall en force
            try:
                subprocess.run(
                    ["killall", "-9", name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                duration = (time.time() - start) * 1000
                bus.emit_sync("os:app:closed", {"name": name, "force": True})
                return AppResult(
                    success=True,
                    data={"name": name, "method": "killall"},
                    duration_ms=duration,
                )
            except Exception as e:
                return AppResult(
                    success=False,
                    error=str(e),
                    duration_ms=(time.time() - start) * 1000,
                )

        # Quit propre
        script = (
            f'tell application "{escaped}"\n'
            "    quit\n"
            "end tell"
        )
        result = self._run_osascript(script, timeout=10)
        duration = (time.time() - start) * 1000

        if result.returncode == 0:
            bus.emit_sync("os:app:closed", {"name": name})
            return AppResult(
                success=True,
                data={"name": name, "method": "quit"},
                duration_ms=duration,
            )

        # Fallback: killall
        try:
            subprocess.run(
                ["killall", name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            duration = (time.time() - start) * 1000
            bus.emit_sync("os:app:closed", {"name": name, "force": True})
            return AppResult(
                success=True,
                data={"name": name, "method": "killall"},
                duration_ms=duration,
            )
        except Exception as e:
            return AppResult(
                success=False,
                error=f"Fermeture échouée: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

    def focus_app(self, name: str) -> AppResult:
        """Amène une application au premier plan.

        Args:
            name: Nom de l'application.

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        escaped = self._escape_applescript_string(name)
        script = (
            f'tell application "{escaped}"\n'
            "    activate\n"
            "end tell"
        )
        result = self._run_osascript(script, timeout=10)
        duration = (time.time() - start) * 1000

        if result.returncode == 0:
            EventBus().emit_sync("os:app:focus", {"name": name})
            return AppResult(success=True, duration_ms=duration)

        return AppResult(
            success=False,
            error=f"Focus échoué pour '{name}'",
            duration_ms=duration,
        )

    def hide_app(self, name: str) -> AppResult:
        """Cache une application (visible = false).

        Args:
            name: Nom de l'application.

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        escaped = self._escape_applescript_string(name)
        script = (
            f'tell application "{escaped}"\n'
            "    set visible to false\n"
            "end tell"
        )
        result = self._run_osascript(script, timeout=10)
        duration = (time.time() - start) * 1000

        if result.returncode == 0:
            EventBus().emit_sync("os:app:hide", {"name": name})
            return AppResult(success=True, duration_ms=duration)

        return AppResult(
            success=False,
            error=f"Cache échoué pour '{name}'",
            duration_ms=duration,
        )

    def get_app_info(self, name: str) -> AppInfo | None:
        """Cherche les informations d'une application dans le cache.

        Si le cache est vide, lance discover_apps() d'abord.

        Args:
            name: Nom de l'application.

        Returns:
            AppInfo si trouvé, None sinon.
        """
        with self._cache_lock:
            if not self._app_cache:
                # Lazy-init du cache
                pass

        if not self._app_cache:
            self.discover_apps()

        with self._cache_lock:
            return self._app_cache.get(name)

    def is_app_running(self, name: str) -> bool:
        """Vérifie si une application est en cours d'exécution.

        Utilise AppleScript System Events.

        Args:
            name: Nom de l'application.

        Returns:
            True si l'application est active.
        """
        script = (
            'tell application "System Events"\n'
            f"    set appName to \"{self._escape_applescript_string(name)}\"\n"
            "    set isRunning to exists (processes where name is appName)\n"
            "    return isRunning\n"
            "end tell"
        )
        result = self._run_osascript(script)
        if result.returncode != 0:
            return False
        return "true" in result.stdout.lower()

    # ── Gestion des fenêtres ──

    def list_windows(self, app_name: str | None = None) -> AppResult:
        """Liste les fenêtres, optionnellement filtrées par application.

        Utilise AppleScript System Events.

        Args:
            app_name: Si fourni, liste uniquement les fenêtres de cette app.

        Returns:
            AppResult avec data=liste de WindowInfo.
        """
        start = time.time()

        if app_name:
            escaped = self._escape_applescript_string(app_name)
            script = (
                f'tell application "System Events"\n'
                f'    set procName to "{escaped}"\n'
                "    set outputList to {}\n"
                "    set foundProc to false\n"
                "    try\n"
                "        set targetProc to first process whose name is procName\n"
                "        set foundProc to true\n"
                "        set winList to every window of targetProc\n"
                "        repeat with w in winList\n"
                "            set winTitle to title of w\n"
                "            set {xPos, yPos} to position of w\n"
                "            set {wSize, hSize} to size of w\n"
                "            set winMinimized to minimized of w\n"
                '            set end of outputList to winTitle & "|||" & xPos & "|||" & yPos & "|||" & wSize & "|||" & hSize & "|||" & winMinimized as string\n'
                "        end repeat\n"
                "    on error errMsg\n"
                "        if not foundProc then\n"
                '            return "ERROR:not_found|||" & procName\n'
                "        else\n"
                '            return "ERROR:access|||" & errMsg\n'
                "        end if\n"
                "    end try\n"
                "    return outputList\n"
                "end tell"
            )
        else:
            script = (
                'tell application "System Events"\n'
                "    set outputList to {}\n"
                "    set allProcs to every process whose background only is false\n"
                "    repeat with procRef in allProcs\n"
                "        set procName to name of procRef\n"
                "        try\n"
                "            set winList to every window of procRef\n"
                "            repeat with w in winList\n"
                "                set winTitle to title of w\n"
                "                set {xPos, yPos} to position of w\n"
                "                set {wSize, hSize} to size of w\n"
                "                set winMinimized to minimized of w\n"
                '                set end of outputList to procName & "|||" & winTitle & "|||" & xPos & "|||" & yPos & "|||" & wSize & "|||" & hSize & "|||" & winMinimized as string\n'
                "            end repeat\n"
                "        on error errMsg\n"
                '            set end of outputList to "ERROR:access|||" & procName & "|||" & errMsg\n'
                "        end try\n"
                "    end repeat\n"
                "    return outputList\n"
                "end tell"
            )

        result = self._run_osascript(script, timeout=15)
        duration = (time.time() - start) * 1000

        if result.returncode != 0:
            return AppResult(
                success=False,
                error=result.stderr.strip() or "Erreur liste fenêtres",
                duration_ms=duration,
            )

        windows = self._parse_window_list(result.stdout, app_name)
        return AppResult(success=True, data=windows, duration_ms=duration)

    def _parse_window_list(
        self, applescript_output: str, app_name: str | None
    ) -> list[WindowInfo]:
        """Parse la sortie AppleScript en liste de WindowInfo.

        La sortie utilise le délimiteur ``|||`` entre les champs :
        - Avec app_name: Title|||x|||y|||w|||h|||minimized (une par ligne)
        - Sans app_name: App|||Title|||x|||y|||w|||h|||minimized (une par ligne)

        Si le format délimiteur n'est pas trouvé, tente le parsing
        du format liste AppleScript legacy.

        Args:
            applescript_output: Sortie brute d'AppleScript.
            app_name: Nom d'application (pour filtrage éventuel).

        Returns:
            Liste d'objets WindowInfo.
        """
        windows: list[WindowInfo] = []
        if not applescript_output or applescript_output.strip() in ("{}", ""):
            return windows

        lines = applescript_output.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line or line in ("{}", ""):
                continue

            # Ignorer les lignes d'erreur
            if line.startswith("ERROR:"):
                logger.debug("Erreur AppleScript fenêtres: %s", line)
                continue

            # Nouveau format: délimiteur |||
            if "|||" in line:
                parts = line.split("|||")
                if app_name and len(parts) >= 6:
                    # Format: Title|||x|||y|||w|||h|||minimized
                    try:
                        windows.append(
                            WindowInfo(
                                app_name=app_name,
                                title=parts[0].strip(),
                                x=int(parts[1].strip()),
                                y=int(parts[2].strip()),
                                width=int(parts[3].strip()),
                                height=int(parts[4].strip()),
                                minimized=parts[5].strip().lower() == "true",
                            )
                        )
                    except (ValueError, IndexError):
                        continue
                elif not app_name and len(parts) >= 7:
                    # Format: App|||Title|||x|||y|||w|||h|||minimized
                    try:
                        windows.append(
                            WindowInfo(
                                app_name=parts[0].strip(),
                                title=parts[1].strip(),
                                x=int(parts[2].strip()),
                                y=int(parts[3].strip()),
                                width=int(parts[4].strip()),
                                height=int(parts[5].strip()),
                                minimized=parts[6].strip().lower() == "true",
                            )
                        )
                    except (ValueError, IndexError):
                        continue
                continue

            # Format legacy (liste AppleScript)
            if app_name:
                match = re.search(
                    r'\{\s*"([^"]*)"\s*,\s*\{(\d+),\s*(\d+)\}\s*,\s*\{(\d+),\s*(\d+)\}\s*,\s*(true|false)\s*\}',
                    line,
                )
                if match:
                    windows.append(
                        WindowInfo(
                            app_name=app_name,
                            title=match.group(1),
                            x=int(match.group(2)),
                            y=int(match.group(3)),
                            width=int(match.group(4)),
                            height=int(match.group(5)),
                            minimized=match.group(6).lower() == "true",
                        )
                    )
            else:
                match = re.search(
                    r'\{\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*\{(\d+),\s*(\d+)\}\s*,\s*\{(\d+),\s*(\d+)\}\s*,\s*(true|false)\s*\}',
                    line,
                )
                if match:
                    windows.append(
                        WindowInfo(
                            app_name=match.group(1),
                            title=match.group(2),
                            x=int(match.group(3)),
                            y=int(match.group(4)),
                            width=int(match.group(5)),
                            height=int(match.group(6)),
                            minimized=match.group(7).lower() == "true",
                        )
                    )
        return windows

    def get_frontmost_window(self) -> AppResult:
        """Récupère la fenêtre active (au premier plan).

        Returns:
            AppResult avec data=WindowInfo de la fenêtre active.
        """
        start = time.time()
        script = (
            'tell application "System Events"\n'
            "    set frontProc to first process whose frontmost is true\n"
            "    set procName to name of frontProc\n"
            "    try\n"
            "        set frontWin to first window of frontProc\n"
            "        set winTitle to title of frontWin\n"
            "        set {xPos, yPos} to position of frontWin\n"
            "        set {wSize, hSize} to size of frontWin\n"
            "        set winMinimized to minimized of frontWin\n"
            '        set output to procName & "|||" & winTitle & "|||" & xPos & "|||" & yPos & "|||" & wSize & "|||" & hSize & "|||" & winMinimized as string\n'
            "        return output\n"
            "    on error\n"
            '        return procName & "|||" & "" & "|||" & "0" & "|||" & "0" & "|||" & "0" & "|||" & "0" & "|||" & "false"\n'
            "    end try\n"
            "end tell"
        )
        result = self._run_osascript(script, timeout=10)
        duration = (time.time() - start) * 1000

        if result.returncode != 0:
            return AppResult(
                success=False,
                error=result.stderr.strip() or "Aucune fenêtre active",
                duration_ms=duration,
            )

        # Parse: App|||Title|||x|||y|||w|||h|||minimized
        parts = result.stdout.strip().split("|||")
        if len(parts) >= 7:
            try:
                window = WindowInfo(
                    app_name=parts[0].strip(),
                    title=parts[1].strip(),
                    x=int(parts[2].strip()),
                    y=int(parts[3].strip()),
                    width=int(parts[4].strip()),
                    height=int(parts[5].strip()),
                    minimized=parts[6].strip().lower() == "true",
                    focused=True,
                )
                return AppResult(success=True, data=window, duration_ms=duration)
            except (ValueError, IndexError):
                pass

        return AppResult(
            success=False,
            error=f"Impossible de parser la fenêtre active: {result.stdout[:100]}",
            duration_ms=duration,
        )

    def move_window(
        self,
        app_name: str,
        title: str,
        x: int,
        y: int,
    ) -> AppResult:
        """Déplace une fenêtre à une position donnée.

        Args:
            app_name: Nom de l'application.
            title: Titre de la fenêtre.
            x: Nouvelle position X.
            y: Nouvelle position Y.

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        escaped_app = self._escape_applescript_string(app_name)
        escaped_title = self._escape_applescript_string(title)
        script = (
            f'tell application "System Events"\n'
            f'    set procName to "{escaped_app}"\n'
            f'    set winTitle to "{escaped_title}"\n'
            "    try\n"
            "        set targetProc to first process whose name is procName\n"
            "        set targetWin to first window of targetProc whose title is winTitle\n"
            f"        set position of targetWin to {{{x}, {y}}}\n"
            "        return true\n"
            "    on error errMsg\n"
            "        return errMsg\n"
            "    end try\n"
            "end tell"
        )
        result = self._run_osascript(script, timeout=10)
        duration = (time.time() - start) * 1000

        if result.returncode == 0 and "error" not in result.stdout.lower():
            EventBus().emit_sync(
                "os:window:moved",
                {"app": app_name, "title": title, "x": x, "y": y},
            )
            return AppResult(success=True, duration_ms=duration)

        return AppResult(
            success=False,
            error=result.stderr.strip() or "Déplacement échoué",
            duration_ms=duration,
        )

    def resize_window(
        self,
        app_name: str,
        title: str,
        width: int,
        height: int,
    ) -> AppResult:
        """Redimensionne une fenêtre.

        Args:
            app_name: Nom de l'application.
            title: Titre de la fenêtre.
            width: Nouvelle largeur en pixels.
            height: Nouvelle hauteur en pixels.

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        escaped_app = self._escape_applescript_string(app_name)
        escaped_title = self._escape_applescript_string(title)
        script = (
            f'tell application "System Events"\n'
            f'    set procName to "{escaped_app}"\n'
            f'    set winTitle to "{escaped_title}"\n'
            "    try\n"
            "        set targetProc to first process whose name is procName\n"
            "        set targetWin to first window of targetProc whose title is winTitle\n"
            f"        set size of targetWin to {{{width}, {height}}}\n"
            "        return true\n"
            "    on error errMsg\n"
            "        return errMsg\n"
            "    end try\n"
            "end tell"
        )
        result = self._run_osascript(script, timeout=10)
        duration = (time.time() - start) * 1000

        if result.returncode == 0 and "error" not in result.stdout.lower():
            EventBus().emit_sync(
                "os:window:resized",
                {
                    "app": app_name,
                    "title": title,
                    "width": width,
                    "height": height,
                },
            )
            return AppResult(success=True, duration_ms=duration)

        return AppResult(
            success=False,
            error=result.stderr.strip() or "Redimensionnement échoué",
            duration_ms=duration,
        )

    def minimize_window(
        self,
        app_name: str,
        title: str,
    ) -> AppResult:
        """Minimise une fenêtre.

        Args:
            app_name: Nom de l'application.
            title: Titre de la fenêtre.

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        escaped_app = self._escape_applescript_string(app_name)
        escaped_title = self._escape_applescript_string(title)
        script = (
            f'tell application "System Events"\n'
            f'    set procName to "{escaped_app}"\n'
            f'    set winTitle to "{escaped_title}"\n'
            "    try\n"
            "        set targetProc to first process whose name is procName\n"
            "        set targetWin to first window of targetProc whose title is winTitle\n"
            "        set minimized of targetWin to true\n"
            "        return true\n"
            "    on error errMsg\n"
            "        return errMsg\n"
            "    end try\n"
            "end tell"
        )
        result = self._run_osascript(script, timeout=10)
        duration = (time.time() - start) * 1000

        if result.returncode == 0 and "error" not in result.stdout.lower():
            EventBus().emit_sync(
                "os:window:minimized",
                {"app": app_name, "title": title},
            )
            return AppResult(success=True, duration_ms=duration)

        return AppResult(
            success=False,
            error=result.stderr.strip() or "Minimisation échouée",
            duration_ms=duration,
        )

    def maximize_window(
        self,
        app_name: str,
        title: str,
    ) -> AppResult:
        """Maximise une fenêtre (zoom).

        Utilise la commande 'zoom' d'AppleScript ou System Events.

        Args:
            app_name: Nom de l'application.
            title: Titre de la fenêtre.

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        escaped_app = self._escape_applescript_string(app_name)
        escaped_title = self._escape_applescript_string(title)

        # Méthode 1: tell app to set zoomed to true
        script1 = (
            f'tell application "{escaped_app}"\n'
            f'    set winTitle to "{escaped_title}"\n'
            "    try\n"
            "        set targetWin to first window whose title is winTitle\n"
            "        set zoomed of targetWin to true\n"
            "        return true\n"
            "    end try\n"
            "end tell"
        )
        result = self._run_osascript(script1, timeout=10)
        duration = (time.time() - start) * 1000

        if result.returncode == 0 and "true" in result.stdout.lower():
            EventBus().emit_sync(
                "os:window:maximized",
                {"app": app_name, "title": title},
            )
            return AppResult(success=True, duration_ms=duration)

        # Méthode 2: System Events - maximize button
        script2 = (
            f'tell application "System Events"\n'
            f'    set procName to "{escaped_app}"\n'
            f'    set winTitle to "{escaped_title}"\n'
            "    try\n"
            "        set targetProc to first process whose name is procName\n"
            "        set targetWin to first window of targetProc whose title is winTitle\n"
            "        set value of attribute \"AXFullScreen\" of targetWin to true\n"
            "        return true\n"
            "    on error errMsg\n"
            "        return errMsg\n"
            "    end try\n"
            "end tell"
        )
        result = self._run_osascript(script2, timeout=10)
        duration2 = (time.time() - start) * 1000

        if result.returncode == 0 and "error" not in result.stdout.lower():
            EventBus().emit_sync(
                "os:window:maximized",
                {"app": app_name, "title": title},
            )
            return AppResult(success=True, duration_ms=duration2)

        return AppResult(
            success=False,
            error="Maximisation échouée",
            duration_ms=duration2,
        )

    def close_window(
        self,
        app_name: str,
        title: str,
    ) -> AppResult:
        """Ferme une fenêtre par son titre.

        Args:
            app_name: Nom de l'application.
            title: Titre de la fenêtre.

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        escaped_app = self._escape_applescript_string(app_name)
        escaped_title = self._escape_applescript_string(title)
        script = (
            f'tell application "{escaped_app}"\n'
            f'    set winTitle to "{escaped_title}"\n'
            "    try\n"
            "        set targetWin to first window whose title is winTitle\n"
            "        close targetWin\n"
            "        return true\n"
            "    on error errMsg\n"
            "        return errMsg\n"
            "    end try\n"
            "end tell"
        )
        result = self._run_osascript(script, timeout=10)
        duration = (time.time() - start) * 1000

        if result.returncode == 0 and "error" not in result.stdout.lower():
            EventBus().emit_sync(
                "os:window:closed",
                {"app": app_name, "title": title},
            )
            return AppResult(success=True, duration_ms=duration)

        return AppResult(
            success=False,
            error=result.stderr.strip() or "Fermeture de fenêtre échouée",
            duration_ms=duration,
        )

    def tile_window(
        self,
        app_name: str,
        position: str,
        window_title: str | None = None,
    ) -> AppResult:
        """Positionne une fenêtre selon un preset (tuile).

        Calcule les coordonnées en fonction de la taille de l'écran.
        Positions supportées: left, right, full, top-left, top-right,
        bottom-left, bottom-right, center.

        Args:
            app_name: Nom de l'application.
            position: Position de tuile ('left', 'right', 'full',
                      'top-left', 'top-right', 'bottom-left',
                      'bottom-right', 'center').
            window_title: Titre de la fenêtre (utilise la première
                          fenêtre si None).

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()

        # Récupérer la taille de l'écran
        screen_w, screen_h = self._get_screen_size()
        if not screen_w or not screen_h:
            return AppResult(
                success=False,
                error="Impossible de déterminer la taille de l'écran",
                duration_ms=(time.time() - start) * 1000,
            )

        # Calculer la position selon le preset
        positions = {
            "left": (0, 0, screen_w // 2, screen_h),
            "right": (screen_w // 2, 0, screen_w // 2, screen_h),
            "full": (0, 0, screen_w, screen_h),
            "top-left": (0, 0, screen_w // 2, screen_h // 2),
            "top-right": (screen_w // 2, 0, screen_w // 2, screen_h // 2),
            "bottom-left": (0, screen_h // 2, screen_w // 2, screen_h // 2),
            "bottom-right": (
                screen_w // 2,
                screen_h // 2,
                screen_w // 2,
                screen_h // 2,
            ),
            "center": (
                screen_w // 6,
                0,
                screen_w * 2 // 3,
                screen_h,
            ),
        }

        if position.lower() not in positions:
            return AppResult(
                success=False,
                error=f"Position inconnue: {position}. "
                f"Options: {', '.join(positions.keys())}",
                duration_ms=(time.time() - start) * 1000,
            )

        pos = position.lower()
        new_x, new_y, new_w, new_h = positions[pos]

        escaped_app = self._escape_applescript_string(app_name)

        if window_title:
            escaped_title = self._escape_applescript_string(window_title)
            script = (
                f'tell application "System Events"\n'
                f'    set procName to "{escaped_app}"\n'
                f'    set winTitle to "{escaped_title}"\n'
                "    try\n"
                "        set targetProc to first process whose name is procName\n"
                "        set targetWin to first window of targetProc whose title is winTitle\n"
                f"        set position of targetWin to {{{new_x}, {new_y}}}\n"
                f"        set size of targetWin to {{{new_w}, {new_h}}}\n"
                "        return true\n"
                "    on error errMsg\n"
                "        return errMsg\n"
                "    end try\n"
                "end tell"
            )
        else:
            script = (
                f'tell application "System Events"\n'
                f'    set procName to "{escaped_app}"\n'
                "    try\n"
                "        set targetProc to first process whose name is procName\n"
                "        set targetWin to first window of targetProc\n"
                f"        set position of targetWin to {{{new_x}, {new_y}}}\n"
                f"        set size of targetWin to {{{new_w}, {new_h}}}\n"
                "        return true\n"
                "    on error errMsg\n"
                "        return errMsg\n"
                "    end try\n"
                "end tell"
            )

        result = self._run_osascript(script, timeout=10)
        duration = (time.time() - start) * 1000

        if result.returncode == 0 and "error" not in result.stdout.lower():
            EventBus().emit_sync(
                "os:window:tiled",
                {
                    "app": app_name,
                    "position": position,
                    "x": new_x,
                    "y": new_y,
                    "width": new_w,
                    "height": new_h,
                },
            )
            return AppResult(success=True, duration_ms=duration)

        return AppResult(
            success=False,
            error=result.stderr.strip() or "Tuilage échoué",
            duration_ms=duration,
        )

    # ── Contrôles système ──

    def get_volume(self) -> AppResult:
        """Récupère le volume système (0-100).

        Returns:
            AppResult avec data=niveau de volume (int 0-100).
        """
        start = time.time()
        script = (
            'set volumeInfo to (get volume settings)\n'
            'return output volume of volumeInfo'
        )
        result = self._run_osascript(script)
        duration = (time.time() - start) * 1000

        if result.returncode == 0 and result.stdout.strip():
            try:
                volume = int(result.stdout.strip())
                return AppResult(
                    success=True, data=volume, duration_ms=duration
                )
            except ValueError:
                pass

        return AppResult(
            success=False,
            error="Impossible de lire le volume",
            duration_ms=duration,
        )

    def set_volume(self, level: int) -> AppResult:
        """Définit le volume système (0-100).

        Args:
            level: Niveau de volume (0-100). Sera clampé.

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        level = max(0, min(100, level))
        script = f"set volume output volume {level}"
        result = self._run_osascript(script)
        duration = (time.time() - start) * 1000

        if result.returncode == 0:
            EventBus().emit_sync("os:volume:set", {"level": level})
            return AppResult(
                success=True,
                data={"level": level},
                duration_ms=duration,
            )

        return AppResult(
            success=False,
            error=result.stderr.strip() or "Échec réglage volume",
            duration_ms=duration,
        )

    def mute(self) -> AppResult:
        """Coupe le son (mute).

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        script = 'set volume output muted true'
        result = self._run_osascript(script)
        duration = (time.time() - start) * 1000

        if result.returncode == 0:
            EventBus().emit_sync("os:volume:mute", {})
            return AppResult(success=True, duration_ms=duration)

        return AppResult(
            success=False,
            error=result.stderr.strip() or "Échec mute",
            duration_ms=duration,
        )

    def unmute(self) -> AppResult:
        """Rétablit le son (unmute).

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        script = 'set volume output muted false'
        result = self._run_osascript(script)
        duration = (time.time() - start) * 1000

        if result.returncode == 0:
            EventBus().emit_sync("os:volume:unmute", {})
            return AppResult(success=True, duration_ms=duration)

        return AppResult(
            success=False,
            error=result.stderr.strip() or "Échec unmute",
            duration_ms=duration,
        )

    def toggle_mute(self) -> AppResult:
        """Bascule l'état muet (mute/unmute).

        Returns:
            AppResult avec data={'muted': bool}.
        """
        start = time.time()
        # Récupérer l'état actuel
        script = (
            'set volumeInfo to (get volume settings)\n'
            'return output muted of volumeInfo'
        )
        result = self._run_osascript(script)
        if result.returncode != 0:
            return AppResult(
                success=False,
                error="Impossible de lire l'état mute",
                duration_ms=(time.time() - start) * 1000,
            )

        is_muted = "true" in result.stdout.lower()
        if is_muted:
            return self.unmute()
        else:
            return self.mute()

    def get_brightness(self) -> AppResult:
        """Récupère la luminosité de l'écran (0-100).

        Utilise ioreg pour lire la valeur actuelle.

        Returns:
            AppResult avec data=niveau de luminosité (float 0-100).
        """
        start = time.time()
        try:
            # Utilise ioreg pour lire la luminosité
            result = subprocess.run(
                [
                    "ioreg",
                    "-r",
                    "-c",
                    "AppleDisplay",
                    "-d",
                    "1",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                # Chercher "Brightness" ou "IODisplayParameters"
                match = re.search(
                    r'"brightness"\s*=\s*([\d.]+)', result.stdout, re.IGNORECASE
                )
                if match:
                    brightness = float(match.group(1))
                    # Convertir de l'échelle ioreg (0-1 ou autre) à 0-100
                    if brightness <= 1.0:
                        brightness = brightness * 100
                    duration = (time.time() - start) * 1000
                    return AppResult(
                        success=True,
                        data=min(100, max(0, round(brightness))),
                        duration_ms=duration,
                    )

            # Fallback: AppleScript (certains Mac)
            script = (
                'tell application "System Events"\n'
                "    try\n"
                "        return brightness of display 1\n"
                "    end try\n"
                "end tell"
            )
            result2 = self._run_osascript(script)
            if result2.returncode == 0 and result2.stdout.strip():
                try:
                    b = float(result2.stdout.strip())
                    if 0 <= b <= 100:
                        duration = (time.time() - start) * 1000
                        return AppResult(
                            success=True, data=b, duration_ms=duration
                        )
                except ValueError:
                    pass

            return AppResult(
                success=False,
                error="Impossible de lire la luminosité",
                duration_ms=(time.time() - start) * 1000,
            )

        except Exception as e:
            return AppResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def set_brightness(self, level: float) -> AppResult:
        """Définit la luminosité de l'écran principal.

        Utilise AppleScript ou PyObjC selon disponibilité.

        Args:
            level: Niveau de luminosité (0-100).

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        level = max(0, min(100, level))

        try:
            # Méthode 1: ioreg + AppleScript (via brightness command)
            script = (
                f'tell application "System Events"\n'
                f"    set brightness of display 1 to {level}\n"
                "end tell"
            )
            result = self._run_osascript(script, timeout=5)
            if result.returncode == 0:
                EventBus().emit_sync(
                    "os:brightness:set", {"level": level}
                )
                return AppResult(
                    success=True,
                    data={"level": level},
                    duration_ms=(time.time() - start) * 1000,
                )
        except Exception:
            pass

        # Méthode 2: Commande système (si disponible)
        try:
            # Sur macOS Monterey+, on peut utiliser le CLI brightness
            result = subprocess.run(
                ["brightness", str(level / 100)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                EventBus().emit_sync(
                    "os:brightness:set", {"level": level}
                )
                return AppResult(
                    success=True,
                    data={"level": level},
                    duration_ms=(time.time() - start) * 1000,
                )
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.debug("brightness CLI échoué: %s", e)

        return AppResult(
            success=False,
            error="Impossible de régler la luminosité",
            duration_ms=(time.time() - start) * 1000,
        )

    def lock_screen(self) -> AppResult:
        """Verrouille l'écran (comme Cmd+Ctrl+Q).

        Utilise pmset displaysleepnow pour éteindre l'écran,
        ce qui déclenche le verrouillage.

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        try:
            result = subprocess.run(
                ["pmset", "displaysleepnow"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            duration = (time.time() - start) * 1000
            if result.returncode == 0:
                EventBus().emit_sync("os:screen:locked", {})
                return AppResult(success=True, duration_ms=duration)

            return AppResult(
                success=False,
                error=result.stderr.strip() or "Échec verrouillage",
                duration_ms=duration,
            )
        except Exception as e:
            return AppResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def sleep_display(self) -> AppResult:
        """Met l'écran en veille.

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        return self.lock_screen()

    def activate_screensaver(self) -> AppResult:
        """Active l'économiseur d'écran.

        Utilise AppleScript 'tell app "ScreenSaverEngine" to activate'.

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        script = (
            'tell application "ScreenSaverEngine"\n'
            "    activate\n"
            "end tell"
        )
        result = self._run_osascript(script, timeout=5)
        duration = (time.time() - start) * 1000

        if result.returncode == 0:
            EventBus().emit_sync("os:screensaver:activated", {})
            return AppResult(success=True, duration_ms=duration)

        return AppResult(
            success=False,
            error=result.stderr.strip() or "Échec activation écran de veille",
            duration_ms=duration,
        )

    def empty_trash(self) -> AppResult:
        """Vide la corbeille.

        Utilise AppleScript 'tell app "Finder" to empty trash'.

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        script = (
            'tell application "Finder"\n'
            "    empty trash\n"
            "end tell"
        )
        result = self._run_osascript(script, timeout=30)
        duration = (time.time() - start) * 1000

        if result.returncode == 0:
            EventBus().emit_sync("os:trash:emptied", {})
            return AppResult(success=True, duration_ms=duration)

        return AppResult(
            success=False,
            error=result.stderr.strip() or "Échec vidage corbeille",
            duration_ms=duration,
        )

    def get_system_info(self) -> AppResult:
        """Récupère les informations système (uptime, hostname, CPU, mémoire).

        Returns:
            AppResult avec data=dict contenant les informations système.
        """
        start = time.time()
        info: dict[str, Any] = {}

        try:
            # Hostname
            info["hostname"] = platform.node()

            # OS
            info["os"] = platform.platform()
            info["os_version"] = platform.mac_ver()[0]

            # Uptime
            uptime_result = subprocess.run(
                ["uptime"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if uptime_result.returncode == 0:
                info["uptime"] = uptime_result.stdout.strip()

            # CPU info
            cpu_result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if cpu_result.returncode == 0:
                info["cpu"] = cpu_result.stdout.strip()

            cpu_cores = subprocess.run(
                ["sysctl", "-n", "hw.ncpu"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if cpu_cores.returncode == 0:
                info["cpu_cores"] = int(cpu_cores.stdout.strip())

            # Memory
            mem_result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if mem_result.returncode == 0:
                mem_bytes = int(mem_result.stdout.strip())
                info["memory_gb"] = round(mem_bytes / (1024**3), 2)

            # Disk usage
            df_result = subprocess.run(
                ["df", "-h", "/"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if df_result.returncode == 0:
                lines = df_result.stdout.strip().split("\n")
                if len(lines) >= 2:
                    parts = lines[1].split()
                    if len(parts) >= 4:
                        info["disk_total"] = parts[1]
                        info["disk_used"] = parts[2]
                        info["disk_available"] = parts[3]
                        info["disk_used_percent"] = parts[4]

            # Python version
            info["python_version"] = sys.version.split()[0]

            duration = (time.time() - start) * 1000
            return AppResult(
                success=True,
                data=info,
                duration_ms=duration,
            )

        except Exception as e:
            return AppResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    # ── Simulation souris ──

    def click(
        self,
        x: int,
        y: int,
        button: str = "left",
        clicks: int = 1,
    ) -> AppResult:
        """Effectue un clic à une position donnée.

        Utilise PyAutoGUI (soft dependency). En cas d'échec,
        tente un AppleScript 'click at'.

        Args:
            x: Position X en pixels.
            y: Position Y en pixels.
            button: 'left', 'right', ou 'middle'.
            clicks: Nombre de clics (1 = simple, 2 = double).

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        try:
            import pyautogui as pg

            pg.click(x, y, button=button, clicks=clicks)
            duration = (time.time() - start) * 1000
            return AppResult(success=True, duration_ms=duration)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("PyAutoGUI click échoué: %s", e)

        # Fallback: AppleScript
        script = (
            f'tell application "System Events"\n'
            f"    click at {{{x}, {y}}}\n"
            "end tell"
        )
        result = self._run_osascript(script, timeout=5)
        duration = (time.time() - start) * 1000

        if result.returncode == 0:
            return AppResult(success=True, duration_ms=duration)

        return AppResult(
            success=False,
            error=result.stderr.strip() or "Clic échoué",
            duration_ms=duration,
        )

    def double_click(self, x: int, y: int) -> AppResult:
        """Effectue un double-clic.

        Args:
            x: Position X.
            y: Position Y.

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        return self.click(x, y, button="left", clicks=2)

    def right_click(self, x: int, y: int) -> AppResult:
        """Effectue un clic droit.

        Args:
            x: Position X.
            y: Position Y.

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        return self.click(x, y, button="right")

    def type_text(
        self, text: str, interval: float = 0.05
    ) -> AppResult:
        """Tape du texte au clavier.

        Utilise PyAutoGUI (soft dependency).

        Args:
            text: Texte à taper.
            interval: Délai entre chaque caractère (secondes).

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        try:
            import pyautogui as pg

            pg.write(text, interval=interval)
            duration = (time.time() - start) * 1000
            return AppResult(success=True, duration_ms=duration)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("PyAutoGUI type_text échoué: %s", e)

        # Fallback: AppleScript keystroke
        escaped = self._escape_applescript_string(text)
        script = (
            f'tell application "System Events"\n'
            f"    keystroke \"{escaped}\"\n"
            "end tell"
        )
        result = self._run_osascript(script, timeout=5)
        duration = (time.time() - start) * 1000

        if result.returncode == 0:
            return AppResult(success=True, duration_ms=duration)

        return AppResult(
            success=False,
            error=result.stderr.strip() or "Frappe texte échouée",
            duration_ms=duration,
        )

    def press_key(self, key: str) -> AppResult:
        """Presse une touche spéciale.

        Utilise PyAutoGUI (soft dependency).

        Touches supportées: enter, tab, escape, space, backspace, delete,
        up, down, left, right, home, end, pageup, pagedown, f1-f20,
        command, shift, control, option, caps_lock, function.

        Args:
            key: Nom de la touche.

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        try:
            import pyautogui as pg

            pg.press(key)
            duration = (time.time() - start) * 1000
            return AppResult(success=True, duration_ms=duration)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("PyAutoGUI press_key échoué: %s", e)

        # Fallback: AppleScript key code
        key_map = {
            "enter": 36,
            "tab": 48,
            "escape": 53,
            "space": 49,
            "backspace": 51,
            "delete": 117,
            "up": 126,
            "down": 125,
            "left": 123,
            "right": 124,
            "home": 115,
            "end": 119,
            "pageup": 116,
            "pagedown": 121,
            "return": 36,
        }
        key_code = key_map.get(key.lower())
        if key_code is not None:
            script = (
                f'tell application "System Events"\n'
                f"    key code {key_code}\n"
                "end tell"
            )
            result = self._run_osascript(script, timeout=5)
            duration = (time.time() - start) * 1000
            if result.returncode == 0:
                return AppResult(success=True, duration_ms=duration)

        return AppResult(
            success=False,
            error=f"Touche '{key}' non supportée",
            duration_ms=(time.time() - start) * 1000,
        )

    def hotkey(self, *keys: str) -> AppResult:
        """Exécute un raccourci clavier (combinaison de touches).

        Utilise PyAutoGUI (soft dependency).

        Args:
            *keys: Touches du raccourci (ex: 'command', 'c').

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        try:
            import pyautogui as pg

            pg.hotkey(*keys)
            duration = (time.time() - start) * 1000
            return AppResult(success=True, duration_ms=duration)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("PyAutoGUI hotkey échoué: %s", e)

        # Fallback: AppleScript
        # Convertir les noms PyAutoGUI en codes AppleScript
        key_map = {
            "command": "command down",
            "shift": "shift down",
            "control": "control down",
            "option": "option down",
            "alt": "option down",
            "cmd": "command down",
            "ctrl": "control down",
        }

        modifiers = []
        main_key = None
        for k in keys:
            k_lower = k.lower()
            if k_lower in key_map:
                modifiers.append(key_map[k_lower])
            elif len(k) == 1:
                main_key = k
            else:
                main_key = k_lower

        if main_key:
            mods = ", ".join(modifiers)
            if mods:
                as_script = (
                    f'tell application "System Events"\n'
                    f"    keystroke \"{main_key}\" using {{{mods}}}\n"
                    "end tell"
                )
            else:
                as_script = (
                    f'tell application "System Events"\n'
                    f"    keystroke \"{main_key}\"\n"
                    "end tell"
                )
            result = self._run_osascript(as_script, timeout=5)
            duration = (time.time() - start) * 1000
            if result.returncode == 0:
                return AppResult(success=True, duration_ms=duration)

        return AppResult(
            success=False,
            error=f"Hotkey {keys} échoué",
            duration_ms=(time.time() - start) * 1000,
        )

    def scroll(
        self, clicks: int, x: int | None = None, y: int | None = None
    ) -> AppResult:
        """Effectue un défilement (scroll).

        Utilise PyAutoGUI (soft dependency).

        Args:
            clicks: Nombre de "clics" de molette (positif = haut,
                    négatif = bas).
            x: Position X optionnelle.
            y: Position Y optionnelle.

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        try:
            import pyautogui as pg

            pg.scroll(clicks, x=x, y=y)
            duration = (time.time() - start) * 1000
            return AppResult(success=True, duration_ms=duration)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("PyAutoGUI scroll échoué: %s", e)

        return AppResult(
            success=False,
            error="Scroll nécessite PyAutoGUI",
            duration_ms=(time.time() - start) * 1000,
        )

    def drag(
        self, start_x: int, start_y: int, end_x: int, end_y: int
    ) -> AppResult:
        """Effectue un glisser-déposer (drag).

        Utilise PyAutoGUI (soft dependency).

        Args:
            start_x: Position X de départ.
            start_y: Position Y de départ.
            end_x: Position X d'arrivée.
            end_y: Position Y d'arrivée.

        Returns:
            AppResult indiquant le succès ou l'échec.
        """
        start = time.time()
        try:
            import pyautogui as pg

            pg.moveTo(start_x, start_y)
            pg.drag(end_x - start_x, end_y - start_y)
            duration = (time.time() - start) * 1000
            return AppResult(success=True, duration_ms=duration)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("PyAutoGUI drag échoué: %s", e)

        # Fallback: AppleScript drag
        script = (
            f'tell application "System Events"\n'
            f"    drag from {{{start_x}, {start_y}}} to {{{end_x}, {end_y}}}\n"
            "end tell"
        )
        result = self._run_osascript(script, timeout=5)
        duration = (time.time() - start) * 1000

        if result.returncode == 0:
            return AppResult(success=True, duration_ms=duration)

        return AppResult(
            success=False,
            error=result.stderr.strip() or "Drag échoué",
            duration_ms=duration,
        )

    def screenshot(
        self, region: tuple[int, int, int, int] | None = None
    ) -> AppResult:
        """Capture une capture d'écran.

        Utilise PyAutoGUI (soft dependency). Retourne l'image
        sous forme de tableau numpy.

        Args:
            region: Tuple (x, y, width, height) pour une capture
                    partielle. None = plein écran.

        Returns:
            AppResult avec data=Image PIL/PyAutoGUI.
        """
        start = time.time()
        try:
            import pyautogui as pg

            img = pg.screenshot(region=region)
            duration = (time.time() - start) * 1000
            return AppResult(success=True, data=img, duration_ms=duration)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("PyAutoGUI screenshot échoué: %s", e)

        # Fallback: screencapture CLI
        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp_path = tmp.name
        tmp.close()

        try:
            cmd = ["screencapture", "-x"]
            if region:
                # region = {x, y, w, h} -> screencapture -R x,y,w,h
                rx, ry, rw, rh = region
                cmd.extend(["-R", f"{rx},{ry},{rw},{rh}"])
            cmd.append(tmp_path)

            subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if os.path.isfile(tmp_path) and os.path.getsize(tmp_path) > 0:
                # Charger l'image avec PIL si disponible
                try:
                    from PIL import Image

                    img = Image.open(tmp_path)
                    duration = (time.time() - start) * 1000
                    return AppResult(
                        success=True, data=img, duration_ms=duration
                    )
                except ImportError:
                    duration = (time.time() - start) * 1000
                    return AppResult(
                        success=True,
                        data={"path": tmp_path},
                        duration_ms=duration,
                    )

            return AppResult(
                success=False,
                error="Capture d'écran échouée",
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return AppResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    # ── AppleScript ──

    def run_applescript(
        self, script: str, timeout: int = DEFAULT_OSASCRIPT_TIMEOUT
    ) -> AppResult:
        """Exécute un script AppleScript arbitraire (filtré).

        Valide le script avant exécution (pas de sudo, rm, etc.).

        Args:
            script: Script AppleScript à exécuter.
            timeout: Timeout en secondes (défaut: 15).

        Returns:
            AppResult avec data=stdout du script.
        """
        start = time.time()

        # Validation
        valid, reason = self._validate_applescript(script)
        if not valid:
            duration = (time.time() - start) * 1000
            return AppResult(
                success=False,
                error=f"Script refusé: {reason}",
                duration_ms=duration,
            )

        result = self._run_osascript(script, timeout=timeout)
        duration = (time.time() - start) * 1000

        if result.returncode == 0:
            EventBus().emit_sync(
                "os:applescript:executed",
                {"script_length": len(script)},
            )
            return AppResult(
                success=True,
                data=result.stdout.strip(),
                duration_ms=duration,
            )

        return AppResult(
            success=False,
            error=result.stderr.strip() or "AppleScript échoué",
            data=result.stdout.strip(),
            duration_ms=duration,
        )

    # ── Helpers privés ──

    def _run_osascript(
        self, script: str, timeout: int = DEFAULT_OSASCRIPT_TIMEOUT
    ) -> subprocess.CompletedProcess:
        """Exécute un script AppleScript via osascript.

        Args:
            script: Script AppleScript.
            timeout: Timeout en secondes.

        Returns:
            CompletedProcess de subprocess.
        """
        try:
            return subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            logger.warning("AppleScript timeout (%ds)", timeout)
            return subprocess.CompletedProcess(
                args=[],
                returncode=1,
                stdout="",
                stderr=f"Timeout après {timeout}s",
            )
        except FileNotFoundError:
            logger.error("osascript non trouvé (macOS uniquement)")
            return subprocess.CompletedProcess(
                args=[],
                returncode=1,
                stdout="",
                stderr="osascript non trouvé",
            )
        except Exception as e:
            logger.error("Erreur osascript: %s", e)
            return subprocess.CompletedProcess(
                args=[],
                returncode=1,
                stdout="",
                stderr=str(e),
            )

    def _run_osascript_result(
        self, script: str, timeout: int = DEFAULT_OSASCRIPT_TIMEOUT
    ) -> AppResult:
        """Exécute un AppleScript et retourne un AppResult.

        Args:
            script: Script AppleScript.
            timeout: Timeout en secondes.

        Returns:
            AppResult formaté.
        """
        start = time.time()
        result = self._run_osascript(script, timeout=timeout)
        duration = (time.time() - start) * 1000

        if result.returncode == 0:
            # Parse la sortie liste AppleScript
            data = self._parse_applescript_list(result.stdout)
            return AppResult(
                success=True, data=data, duration_ms=duration
            )

        return AppResult(
            success=False,
            error=result.stderr.strip() or "Échec AppleScript",
            duration_ms=duration,
        )

    def _validate_applescript(self, script: str) -> tuple[bool, str]:
        """Valide un script AppleScript pour détecter les commandes dangereuses.

        Bloque les scripts contenant :
        - sudo, rm -rf /, commandes de destruction
        - do shell script avec commandes dangereuses
        - Tentatives d'escalade de privilèges

        Args:
            script: Script AppleScript à valider.

        Returns:
            Tuple (valide, raison). Si valide, raison est vide.
        """
        script_lower = script.lower()

        # Bloque les commandes shell dangereuses dans do shell script
        blocked_patterns = [
            r"sudo\s+",
            r"rm\s+-[a-z]*rf",
            r"rm\s+-[a-z]*f\s+/",
            r"dd\s+if=",
            r">\s*/dev/sd",
            r"diskutil\s+erase",
            r"shutdown\s",
            r"reboot\s",
            r"halt\s",
            r"poweroff\s",
            r"init\s+[06]",
            r":\(\s*\)\s*\{",
            r"wget.*\|.*(?:sh|bash)",
            r"curl.*\|.*(?:sh|bash)",
            r"chmod\s+777\s+/",
            r"chown\s+",
            r"passwd\s+",
            r"killall\s+-9\s+",
        ]

        for pattern in blocked_patterns:
            if re.search(pattern, script_lower):
                return False, f"Motif dangereux détecté: {pattern}"

        # Vérifier que le script ne contient pas de commandes interdites
        blocked_commands = [
            "sudo",
            "do shell script with administrator privileges",
        ]
        for cmd in blocked_commands:
            if cmd in script_lower:
                return False, f"Commande interdite: {cmd}"

        return True, ""

    def _escape_applescript_string(self, text: str) -> str:
        """Échappe les caractères spéciaux pour une chaîne AppleScript.

        Remplace les guillemets doubles et les backslashes.

        Args:
            text: Texte à échapper.

        Returns:
            Texte échappé pour AppleScript.
        """
        return text.replace("\\", "\\\\").replace('"', '\\"')

    def _parse_applescript_list(self, output: str) -> list[str]:
        """Parse une liste AppleScript simple en liste Python.

        Gère les formats:
        - {"item1", "item2", ...}
        - item1, item2, ...
        - item1\nitem2\n...

        Args:
            output: Sortie brute d'AppleScript.

        Returns:
            Liste de chaînes.
        """
        if not output or not output.strip():
            return []

        text = output.strip()

        # Format dict/liste AppleScript: {"a", "b", ...}
        if text.startswith("{") and text.endswith("}"):
            text = text[1:-1].strip()

        items = []
        for part in text.split(","):
            part = part.strip().strip('"').strip("'")
            if part:
                items.append(part)

        return items

    def _get_screen_size(self) -> tuple[int, int]:
        """Récupère la taille de l'écran principal.

        Utilise PyObjC (AppKit) ou AppleScript en fallback.

        Returns:
            Tuple (largeur, hauteur) en pixels.
        """
        if self._screen_size:
            return self._screen_size

        # Méthode 1: PyObjC
        try:
            from AppKit import NSScreen

            screen = NSScreen.mainScreen()
            if screen:
                frame = screen.frame()
                size = frame.size
                self._screen_size = (int(size.width), int(size.height))
                return self._screen_size
        except ImportError:
            pass
        except Exception as e:
            logger.debug("NSScreen échoué: %s", e)

        # Méthode 2: AppleScript
        script = (
            'tell application "System Events"\n'
            "    set screenSize to size of desktop 1\n"
            "    return screenSize\n"
            "end tell"
        )
        result = self._run_osascript(script)
        if result.returncode == 0:
            match = re.search(r"\{(\d+),\s*(\d+)\}", result.stdout)
            if match:
                w, h = int(match.group(1)), int(match.group(2))
                self._screen_size = (w, h)
                return self._screen_size

        # Méthode 3: PyAutoGUI
        try:
            import pyautogui as pg

            w, h = pg.size()
            self._screen_size = (int(w), int(h))
            return self._screen_size
        except ImportError:
            pass
        except Exception:
            pass

        # Valeur par défaut (macBook Pro 16")
        self._screen_size = (1920, 1080)
        return self._screen_size


# ── Fonction de registre ────────────────────────────────────────


def register_os_tools(
    registry: ToolRegistry, executor: ToolExecutor
) -> None:
    """Enregistre les outils de contrôle OS dans le ToolRegistry.

    Définit 8 outils :
    - ``os_open_app`` : Ouvre une application.
    - ``os_control_app`` : Contrôle une application (focus, hide, close...).
    - ``os_control_window`` : Contrôle une fenêtre (move, resize, tile...).
    - ``os_system_control`` : Contrôle système (volume, luminosité...).
    - ``os_applescript`` : Exécute un script AppleScript filtré.
    - ``os_discover_apps`` : Scanne les applications installées.
    - ``os_screenshot`` : Capture une capture d'écran.
    - ``os_type`` : Tape du texte au clavier.

    Les handlers sont enregistrés dans le ToolExecutor fourni.

    Args:
        registry: Registre d'outils (ToolRegistry).
        executor: Exécuteur d'outils (ToolExecutor).
    """

    # ── os_open_app ───────────────────────────────────────────

    open_app_def = ToolDefinition(
        name="os_open_app",
        description=(
            "Ouvre ou active une application macOS. "
            "Utilise AppleScript 'tell app to activate' ou 'open -a' "
            "en fallback."
        ),
        category="system",
        parameters=[
            ToolParameter(
                name="name",
                type="str",
                description=(
                    "Nom de l'application à ouvrir (ex: 'Safari', "
                    "'Notes', 'Finder')"
                ),
                required=True,
            ),
            ToolParameter(
                name="path",
                type="str",
                description=(
                    "Chemin optionnel vers le bundle .app "
                    "(utilisé si l'activation par nom échoue)"
                ),
                required=False,
                default="",
            ),
            ToolParameter(
                name="wait",
                type="int",
                description=(
                    "Temps d'attente en secondes après l'ouverture "
                    "(défaut: 3)"
                ),
                required=False,
                default=3,
            ),
        ],
    )

    def _open_app_handler(**kwargs: Any) -> dict:
        ctrl = OSController.get_instance()
        name = kwargs.get("name", "")
        path = kwargs.get("path") or None
        wait = float(kwargs.get("wait", 3.0))
        result = ctrl.open_app(name=name, path=path, wait=wait)
        return {
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }

    registry.register(open_app_def)
    executor.register_handler("os_open_app", _open_app_handler)

    # ── os_control_app ────────────────────────────────────────

    control_app_def = ToolDefinition(
        name="os_control_app",
        description=(
            "Contrôle une application macOS (focus, hide, close, etc.). "
            "Actions: 'open', 'close', 'focus', 'hide', 'quit', "
            "'force_quit', 'activate'."
        ),
        category="system",
        parameters=[
            ToolParameter(
                name="action",
                type="str",
                description=(
                    "Action à effectuer: 'open', 'close', 'focus', "
                    "'hide', 'quit', 'force_quit', 'activate'"
                ),
                required=True,
            ),
            ToolParameter(
                name="name",
                type="str",
                description="Nom de l'application cible",
                required=True,
            ),
        ],
    )

    def _control_app_handler(**kwargs: Any) -> dict:
        ctrl = OSController.get_instance()
        action = kwargs.get("action", "").lower()
        name = kwargs.get("name", "")

        action_map: dict[str, Any] = {
            "open": (ctrl.open_app, {"name": name}),
            "close": (ctrl.close_app, {"name": name}),
            "focus": (ctrl.focus_app, {"name": name}),
            "hide": (ctrl.hide_app, {"name": name}),
            "quit": (ctrl.close_app, {"name": name, "force": False}),
            "force_quit": (ctrl.close_app, {"name": name, "force": True}),
            "activate": (ctrl.open_app, {"name": name}),
        }

        if action not in action_map:
            return {
                "success": False,
                "data": None,
                "error": f"Action inconnue: {action}",
                "duration_ms": 0,
            }

        func, params = action_map[action]
        result = func(**params)
        return {
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }

    registry.register(control_app_def)
    executor.register_handler("os_control_app", _control_app_handler)

    # ── os_control_window ─────────────────────────────────────

    control_window_def = ToolDefinition(
        name="os_control_window",
        description=(
            "Contrôle une fenêtre macOS (déplacer, redimensionner, "
            "minimiser, fermer, tuile). "
            "Actions: 'move', 'resize', 'minimize', 'maximize', 'close', "
            "'list', 'frontmost', 'tile_left', 'tile_right', 'tile_full', "
            "'tile_top_left', 'tile_top_right', 'tile_bottom_left', "
            "'tile_bottom_right', 'tile_center'."
        ),
        category="system",
        parameters=[
            ToolParameter(
                name="action",
                type="str",
                description="Action à effectuer sur la fenêtre",
                required=True,
            ),
            ToolParameter(
                name="app",
                type="str",
                description=(
                    "Nom de l'application (requis pour move, resize, "
                    "minimize, maximize, close, tile)"
                ),
                required=False,
                default="",
            ),
            ToolParameter(
                name="x",
                type="int",
                description=(
                    "Position X en pixels (pour move et tile)"
                ),
                required=False,
                default=0,
            ),
            ToolParameter(
                name="y",
                type="int",
                description=(
                    "Position Y en pixels (pour move et tile)"
                ),
                required=False,
                default=0,
            ),
            ToolParameter(
                name="width",
                type="int",
                description="Largeur en pixels (pour resize)",
                required=False,
                default=0,
            ),
            ToolParameter(
                name="height",
                type="int",
                description="Hauteur en pixels (pour resize)",
                required=False,
                default=0,
            ),
            ToolParameter(
                name="title",
                type="str",
                description=(
                    "Titre de la fenêtre (pour move, resize, "
                    "minimize, maximize, close)"
                ),
                required=False,
                default="",
            ),
        ],
    )

    def _control_window_handler(**kwargs: Any) -> dict:
        ctrl = OSController.get_instance()
        action = kwargs.get("action", "").lower()
        app_name = kwargs.get("app", "")
        title = kwargs.get("title", "")

        window_actions: dict[str, Any] = {
            "list": (
                ctrl.list_windows,
                {"app_name": app_name or None},
            ),
            "frontmost": (ctrl.get_frontmost_window, {}),
            "move": (
                ctrl.move_window,
                {
                    "app_name": app_name,
                    "title": title,
                    "x": kwargs.get("x", 0),
                    "y": kwargs.get("y", 0),
                },
            ),
            "resize": (
                ctrl.resize_window,
                {
                    "app_name": app_name,
                    "title": title,
                    "width": kwargs.get("width", 800),
                    "height": kwargs.get("height", 600),
                },
            ),
            "minimize": (
                ctrl.minimize_window,
                {"app_name": app_name, "title": title},
            ),
            "maximize": (
                ctrl.maximize_window,
                {"app_name": app_name, "title": title},
            ),
            "close": (
                ctrl.close_window,
                {"app_name": app_name, "title": title},
            ),
            "tile_left": (
                ctrl.tile_window,
                {
                    "app_name": app_name,
                    "position": "left",
                    "window_title": title or None,
                },
            ),
            "tile_right": (
                ctrl.tile_window,
                {
                    "app_name": app_name,
                    "position": "right",
                    "window_title": title or None,
                },
            ),
            "tile_full": (
                ctrl.tile_window,
                {
                    "app_name": app_name,
                    "position": "full",
                    "window_title": title or None,
                },
            ),
            "tile_top_left": (
                ctrl.tile_window,
                {
                    "app_name": app_name,
                    "position": "top-left",
                    "window_title": title or None,
                },
            ),
            "tile_top_right": (
                ctrl.tile_window,
                {
                    "app_name": app_name,
                    "position": "top-right",
                    "window_title": title or None,
                },
            ),
            "tile_bottom_left": (
                ctrl.tile_window,
                {
                    "app_name": app_name,
                    "position": "bottom-left",
                    "window_title": title or None,
                },
            ),
            "tile_bottom_right": (
                ctrl.tile_window,
                {
                    "app_name": app_name,
                    "position": "bottom-right",
                    "window_title": title or None,
                },
            ),
            "tile_center": (
                ctrl.tile_window,
                {
                    "app_name": app_name,
                    "position": "center",
                    "window_title": title or None,
                },
            ),
        }

        if action not in window_actions:
            return {
                "success": False,
                "data": None,
                "error": f"Action fenêtre inconnue: {action}",
                "duration_ms": 0,
            }

        func, params = window_actions[action]
        result = func(**params)
        return {
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }

    registry.register(control_window_def)
    executor.register_handler("os_control_window", _control_window_handler)

    # ── os_system_control ─────────────────────────────────────

    system_control_def = ToolDefinition(
        name="os_system_control",
        description=(
            "Contrôle les paramètres système macOS. "
            "Actions: 'volume_get', 'volume_set', 'mute', 'unmute', "
            "'toggle_mute', 'brightness_get', 'brightness_set', "
            "'lock_screen', 'sleep_display', 'screensaver', "
            "'empty_trash', 'system_info'."
        ),
        category="system",
        parameters=[
            ToolParameter(
                name="action",
                type="str",
                description="Action système à exécuter",
                required=True,
            ),
            ToolParameter(
                name="value",
                type="int",
                description=(
                    "Valeur pour volume_set (0-100) ou "
                    "brightness_set (0-100)"
                ),
                required=False,
                default=50,
            ),
        ],
    )

    def _system_control_handler(**kwargs: Any) -> dict:
        ctrl = OSController.get_instance()
        action = kwargs.get("action", "").lower()
        value = kwargs.get("value", 50)

        sys_actions: dict[str, Any] = {
            "volume_get": (ctrl.get_volume, {}),
            "volume_set": (ctrl.set_volume, {"level": int(value)}),
            "mute": (ctrl.mute, {}),
            "unmute": (ctrl.unmute, {}),
            "toggle_mute": (ctrl.toggle_mute, {}),
            "brightness_get": (ctrl.get_brightness, {}),
            "brightness_set": (
                ctrl.set_brightness,
                {"level": float(value)},
            ),
            "lock_screen": (ctrl.lock_screen, {}),
            "sleep_display": (ctrl.sleep_display, {}),
            "screensaver": (ctrl.activate_screensaver, {}),
            "empty_trash": (ctrl.empty_trash, {}),
            "system_info": (ctrl.get_system_info, {}),
        }

        if action not in sys_actions:
            return {
                "success": False,
                "data": None,
                "error": f"Action système inconnue: {action}",
                "duration_ms": 0,
            }

        func, params = sys_actions[action]
        result = func(**params)
        return {
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }

    registry.register(system_control_def)
    executor.register_handler(
        "os_system_control", _system_control_handler
    )

    # ── os_applescript ────────────────────────────────────────

    applescript_def = ToolDefinition(
        name="os_applescript",
        description=(
            "Exécute un script AppleScript sur macOS. "
            "Le script est validé pour bloquer les commandes "
            "dangereuses (sudo, rm -rf, etc.). "
            "Retourne la sortie stdout du script."
        ),
        category="system",
        parameters=[
            ToolParameter(
                name="script",
                type="str",
                description="Script AppleScript à exécuter",
                required=True,
            ),
        ],
    )

    def _applescript_handler(**kwargs: Any) -> dict:
        ctrl = OSController.get_instance()
        script = kwargs.get("script", "")
        result = ctrl.run_applescript(script=script)
        return {
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }

    registry.register(applescript_def)
    executor.register_handler("os_applescript", _applescript_handler)

    # ── os_discover_apps ──────────────────────────────────────

    discover_def = ToolDefinition(
        name="os_discover_apps",
        description=(
            "Scanne les dossiers Applications macOS (/Applications, "
            "~/Applications, /System/Applications) et retourne la "
            "liste des applications installées avec leurs chemins."
        ),
        category="system",
        parameters=[],
    )

    def _discover_handler(**kwargs: Any) -> dict:
        ctrl = OSController.get_instance()
        apps = ctrl.discover_apps()
        return {
            "success": True,
            "data": {
                name: {
                    "path": info.path,
                    "bundle_id": info.bundle_id,
                    "version": info.version,
                }
                for name, info in apps.items()
            },
            "error": None,
            "duration_ms": 0,
        }

    registry.register(discover_def)
    executor.register_handler("os_discover_apps", _discover_handler)

    # ── os_screenshot ─────────────────────────────────────────

    screenshot_def = ToolDefinition(
        name="os_screenshot",
        description=(
            "Capture une capture d'écran macOS. "
            "Utilise PyAutoGUI (ou screencapture CLI en fallback)."
        ),
        category="system",
        parameters=[
            ToolParameter(
                name="region",
                type="list",
                description=(
                    "Zone à capturer [x, y, width, height] "
                    "(optionnel, défaut = plein écran)"
                ),
                required=False,
                default=[],
            ),
        ],
    )

    def _screenshot_handler(**kwargs: Any) -> dict:
        ctrl = OSController.get_instance()
        region_raw = kwargs.get("region", [])
        region: tuple[int, int, int, int] | None = None
        if (
            region_raw
            and isinstance(region_raw, list)
            and len(region_raw) == 4
        ):
            region = tuple(int(v) for v in region_raw)  # type: ignore[assignment]

        result = ctrl.screenshot(region=region)
        # Ne pas retourner l'image PIL directement (non sérialisable)
        return {
            "success": result.success,
            "data": (
                "Capture réussie"
                if result.success
                else result.data
            ),
            "error": result.error,
            "duration_ms": result.duration_ms,
        }

    registry.register(screenshot_def)
    executor.register_handler("os_screenshot", _screenshot_handler)

    # ── os_type ───────────────────────────────────────────────

    type_def = ToolDefinition(
        name="os_type",
        description=(
            "Tape du texte au clavier sur macOS. "
            "Utilise PyAutoGUI (soft dependency) ou AppleScript "
            "keystroke en fallback."
        ),
        category="system",
        parameters=[
            ToolParameter(
                name="text",
                type="str",
                description="Texte à taper",
                required=True,
            ),
            ToolParameter(
                name="interval",
                type="float",
                description=(
                    "Intervalle entre chaque caractère en secondes "
                    "(défaut: 0.05)"
                ),
                required=False,
                default=0.05,
            ),
        ],
    )

    def _type_handler(**kwargs: Any) -> dict:
        ctrl = OSController.get_instance()
        text = kwargs.get("text", "")
        interval = float(kwargs.get("interval", 0.05))
        result = ctrl.type_text(text=text, interval=interval)
        return {
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }

    registry.register(type_def)
    executor.register_handler("os_type", _type_handler)

    logger.info("8 outils OS enregistrés")
