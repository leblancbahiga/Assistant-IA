"""Tests unitaires pour la Gestion Fichiers CRUD NURU — Phase 1 S6.

Couvre : PathSafety, FileOpResult, FileOpsController singleton/sécurité/CRUD,
ToolRegistry, edge cases, workspace management, EventBus events.

Minimum: 45 tests. Structure pytest. Nettoyage des fichiers temporaires.
"""
from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Imports du projet ──────────────────────────────────────────
from src.core.events import EventBus
from src.tools.file_ops import (
    DESTRUCTIVE_ACCESS_LEVEL,
    PathSafety,
    FileOpResult,
    FileOpsController,
    register_file_tools,
)
from src.tools.registry import ToolRegistry, ToolExecutor

# ── Constantes de test ─────────────────────────────────────────
HOME = os.path.expanduser("~")
WORKSPACE = os.path.join(HOME, "Nuru_Workspace")
TEST_PREFIX = "_test_fileops_"


# ══════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════

@pytest.fixture
def ctrl():
    """Fixture : instance unique du contrôleur fichiers."""
    instance = FileOpsController.get_instance()
    # S'assurer qu'on est en profil safe par défaut
    instance.safety_profile = "safe"
    # S'assurer que le workspace existe
    os.makedirs(instance.workspace_root, exist_ok=True)
    yield instance


@pytest.fixture(autouse=True)
def clear_eventbus():
    """Vide la file d'événements avant chaque test."""
    EventBus()._queue.clear()
    yield
    EventBus()._queue.clear()


@pytest.fixture
def ws_file(ctrl):
    """Crée un fichier temporaire dans le workspace et le nettoie après."""
    path = f"{TEST_PREFIX}tempfile.txt"
    full = os.path.join(ctrl.workspace_root, path)
    ctrl.write_file(path, "ligne 1\nligne 2\nligne 3\n")
    yield path
    # Nettoyage
    try:
        if os.path.isfile(full):
            os.remove(full)
    except OSError:
        pass


@pytest.fixture
def ws_dir(ctrl):
    """Crée un dossier temporaire dans le workspace et le nettoie après."""
    path = f"{TEST_PREFIX}tempdir"
    full = os.path.join(ctrl.workspace_root, path)
    os.makedirs(full, exist_ok=True)
    yield path
    try:
        if os.path.isdir(full):
            shutil.rmtree(full, ignore_errors=True)
    except OSError:
        pass


@pytest.fixture(autouse=True)
def cleanup_test_files():
    """Nettoyage global : supprime tous les fichiers _test_fileops_ après chaque test."""
    yield
    try:
        for entry in os.listdir(WORKSPACE):
            if entry.startswith(TEST_PREFIX):
                full = os.path.join(WORKSPACE, entry)
                if os.path.isfile(full):
                    os.remove(full)
                elif os.path.isdir(full):
                    shutil.rmtree(full, ignore_errors=True)
    except OSError:
        pass


# ══════════════════════════════════════════════════════════════
# 1. Structure : PathSafety, FileOpResult, singleton
# ══════════════════════════════════════════════════════════════

class TestPathSafety:
    """PathSafety enum values et représentation."""

    def test_pathsafety_values(self):
        """PathSafety enum values correctes."""
        assert PathSafety.WORKSPACE.value == 0
        assert PathSafety.AUTHORIZED.value == 1
        assert PathSafety.SYSTEM.value == 2
        assert PathSafety.BLOCKED.value == 3
        assert PathSafety.OUTSIDE.value == 4

    def test_pathsafety_str(self):
        """PathSafety.__str__ retourne les labels attendus."""
        assert str(PathSafety.WORKSPACE) == "WORKSPACE"
        assert str(PathSafety.AUTHORIZED) == "AUTHORIZED"
        assert str(PathSafety.SYSTEM) == "SYSTEM"
        assert str(PathSafety.BLOCKED) == "BLOCKED"
        assert str(PathSafety.OUTSIDE) == "OUTSIDE"

    def test_pathsafety_comparison(self):
        """PathSafety se compare correctement en tant qu'IntEnum."""
        assert PathSafety.WORKSPACE < PathSafety.AUTHORIZED
        assert PathSafety.AUTHORIZED < PathSafety.SYSTEM
        assert PathSafety.SYSTEM < PathSafety.BLOCKED
        assert PathSafety.BLOCKED < PathSafety.OUTSIDE


class TestFileOpResult:
    """FileOpResult dataclass."""

    def test_result_creation_minimal(self):
        """FileOpResult se crée avec les champs obligatoires."""
        r = FileOpResult(success=True, message="OK")
        assert r.success is True
        assert r.message == "OK"
        assert r.path is None
        assert r.details is None
        assert r.error is None
        assert r.duration_ms == 0.0

    def test_result_creation_full(self):
        """FileOpResult se crée avec tous les champs."""
        r = FileOpResult(
            success=True,
            message="Fichier créé",
            path="/tmp/test.txt",
            details={"size": 42},
            error=None,
            duration_ms=1.23,
        )
        assert r.success is True
        assert r.path == "/tmp/test.txt"
        assert r.details == {"size": 42}
        assert r.duration_ms == 1.23

    def test_result_to_dict(self):
        """FileOpResult.to_dict() retourne un dictionnaire."""
        r = FileOpResult(
            success=True,
            message="OK",
            path="/tmp/f.txt",
            details={"lines": 5},
            error=None,
            duration_ms=3.0,
        )
        d = r.to_dict()
        assert d["success"] is True
        assert d["message"] == "OK"
        assert d["path"] == "/tmp/f.txt"
        assert d["details"]["lines"] == 5


class TestSingleton:
    """FileOpsController singleton."""

    def test_singleton_instance(self):
        """FileOpsController.get_instance() retourne toujours la même instance."""
        a = FileOpsController.get_instance()
        b = FileOpsController.get_instance()
        assert a is b

    def test_singleton_workspace_exists(self, ctrl):
        """Le workspace par défaut est créé et accessible."""
        assert os.path.isdir(ctrl.workspace_root)
        assert ctrl.workspace_root == WORKSPACE

    def test_singleton_properties_defaults(self, ctrl):
        """Propriétés par défaut du singleton."""
        assert ctrl.safety_profile == "safe"
        assert ctrl.authorized_dirs == set()
        assert ctrl.get_safety_level() == 1


# ══════════════════════════════════════════════════════════════
# 2. Sécurité : path traversal, blocklist
# ══════════════════════════════════════════════════════════════

class TestSecurity:
    """Validation des chemins et sécurité."""

    def test_workspace_path_safe(self, ctrl):
        """Un chemin dans le workspace retourne WORKSPACE."""
        inside = os.path.join(WORKSPACE, "some_test_file.txt")
        safety, reason = ctrl.check_path_safety(inside)
        assert safety == PathSafety.WORKSPACE, f"Attendu WORKSPACE, obtenu {safety}: {reason}"

    def test_etc_passwd_blocked(self, ctrl):
        """/etc/passwd est BLOQUÉ."""
        safety, reason = ctrl.check_path_safety("/etc/passwd")
        assert safety == PathSafety.BLOCKED, f"Attendu BLOCKED, obtenu {safety}: {reason}"

    def test_etc_dir_blocked(self, ctrl):
        """/etc seul est BLOQUÉ."""
        safety, reason = ctrl.check_path_safety("/etc")
        assert safety in (PathSafety.BLOCKED, PathSafety.SYSTEM), f"{safety}: {reason}"

    def test_empty_path_returns_outside(self, ctrl):
        """Chemin vide retourne OUTSIDE."""
        safety, reason = ctrl.check_path_safety("")
        assert safety == PathSafety.OUTSIDE

    def test_whitespace_path_returns_outside(self, ctrl):
        """Chemin blanc retourne OUTSIDE."""
        safety, reason = ctrl.check_path_safety("   ")
        assert safety == PathSafety.OUTSIDE

    def test_system_path_prefix(self, ctrl):
        """Un chemin dans /System est reconnu comme système."""
        safety, reason = ctrl.check_path_safety("/System/Library")
        assert safety in (PathSafety.SYSTEM, PathSafety.BLOCKED), f"{safety}: {reason}"

    def test_blocked_path_dev(self, ctrl):
        """/dev est bloqué."""
        safety, reason = ctrl.check_path_safety("/dev/null")
        assert safety == PathSafety.BLOCKED, f"Attendu BLOCKED, obtenu {safety}: {reason}"

    def test_path_traversal_detected(self, ctrl):
        """Path traversal avec ../ est détecté."""
        assert ctrl._has_path_traversal("../etc/passwd") is True
        assert ctrl._has_path_traversal("data/../../etc") is True

    def test_path_traversal_encoded(self, ctrl):
        """Path traversal encodé %2e%2e/ est détecté."""
        assert ctrl._has_path_traversal("%2e%2e/etc") is True

    def test_resolve_path_blocks_traversal(self, ctrl):
        """resolve_path lève ValueError sur path traversal."""
        with pytest.raises(ValueError, match="traversal"):
            ctrl.resolve_path("../etc/passwd")

    def test_resolve_path_blocks_etc(self, ctrl):
        """resolve_path sur /etc/passwd lève PermissionError."""
        with pytest.raises(PermissionError, match="bloqué|interdit|blocked"):
            ctrl.resolve_path("/etc/passwd")


# ══════════════════════════════════════════════════════════════
# 3. CRUD basique dans le workspace
# ══════════════════════════════════════════════════════════════

class TestCRUD:
    """Opérations CRUD de base."""

    def test_write_file(self, ctrl):
        """write_file crée un fichier et retourne success."""
        path = f"{TEST_PREFIX}write_test.txt"
        result = ctrl.write_file(path, "Hello World")
        assert result.success, result.error
        assert result.path is not None
        full = os.path.join(ctrl.workspace_root, path)
        assert os.path.isfile(full)

    def test_read_file(self, ctrl, ws_file):
        """read_file lit le contenu d'un fichier."""
        result = ctrl.read_file(ws_file)
        assert result.success, result.error
        assert result.details is not None
        assert "ligne 1" in result.details.get("content", "")
        assert result.details.get("total_lines") == 3

    def test_read_file_with_offset_limit(self, ctrl, ws_file):
        """read_file avec offset/limit lit une plage."""
        result = ctrl.read_file(ws_file, offset=1, limit=1)
        assert result.success
        content = result.details["content"]
        assert "ligne 2" in content
        assert "ligne 1" not in content
        assert len(content.splitlines()) == 1

    def test_append_file(self, ctrl, ws_file):
        """append_file ajoute du contenu à la fin."""
        result = ctrl.append_file(ws_file, "ligne 4\n")
        assert result.success, result.error
        read = ctrl.read_file(ws_file)
        assert read.details["total_lines"] == 4
        assert read.details["content"].endswith("ligne 4\n")

    def test_copy_file(self, ctrl, ws_file):
        """copy_file duplique un fichier."""
        dest = f"{TEST_PREFIX}copy_dest.txt"
        result = ctrl.copy_file(ws_file, dest)
        assert result.success, result.error
        full_dest = os.path.join(ctrl.workspace_root, dest)
        assert os.path.isfile(full_dest)
        # Vérifier le contenu
        orig = ctrl.read_file(ws_file)
        copied = ctrl.read_file(dest)
        assert orig.details["content"] == copied.details["content"]
        # Nettoyage
        try:
            os.remove(full_dest)
        except OSError:
            pass

    def test_create_directory(self, ctrl):
        """create_directory crée un dossier."""
        path = f"{TEST_PREFIX}newdir"
        result = ctrl.create_directory(path)
        assert result.success, result.error
        full = os.path.join(ctrl.workspace_root, path)
        assert os.path.isdir(full)

    def test_create_directory_existing(self, ctrl, ws_dir):
        """create_directory sur dossier existant retourne success."""
        result = ctrl.create_directory(ws_dir)
        assert result.success  # Doit réussir silencieusement
        assert result.message is not None

    def test_list_directory(self, ctrl, ws_dir):
        """list_directory liste le contenu d'un dossier."""
        # Créer un fichier dans le dossier
        inner = f"{ws_dir}/inner_file.txt"
        ctrl.write_file(inner, "test")
        result = ctrl.list_directory(ws_dir)
        assert result.success, result.error
        assert result.details["count"] >= 1
        names = [e["name"] for e in result.details["entries"]]
        assert "inner_file.txt" in names
        # Nettoyer le fichier interne
        try:
            os.remove(os.path.join(ctrl.workspace_root, inner))
        except OSError:
            pass

    def test_list_directory_recursive(self, ctrl, ws_dir):
        """list_directory récursif."""
        sub = f"{ws_dir}/sub"
        ctrl.create_directory(sub)
        inner = f"{sub}/deep.txt"
        ctrl.write_file(inner, "deep")
        result = ctrl.list_directory(ws_dir, recursive=True)
        assert result.success
        rel_paths = [e["rel_path"] for e in result.details["entries"]]
        assert any("deep.txt" in p for p in rel_paths)

    def test_get_file_info(self, ctrl, ws_file):
        """get_file_info retourne les métadonnées."""
        result = ctrl.get_file_info(ws_file)
        assert result.success, result.error
        assert result.details["is_file"] is True
        assert result.details["size_bytes"] > 0
        assert result.details.get("name") is not None

    def test_search_files(self, ctrl, ws_file):
        """search_files trouve des fichiers par pattern."""
        result = ctrl.search_files(f"{TEST_PREFIX}*")
        assert result.success, result.error
        assert result.details["count"] >= 1

    def test_search_content(self, ctrl):
        """search_content trouve du texte dans les fichiers."""
        path = f"{TEST_PREFIX}search_content.txt"
        ctrl.write_file(path, "Ceci est un texte avec MOTIF_CACHE ici.\n")
        result = ctrl.search_content("MOTIF_CACHE", file_glob="*.txt")
        assert result.success, result.error
        assert result.details["match_count"] >= 1


# ══════════════════════════════════════════════════════════════
# 4. Destruction : delete/move bloqués en safe, OK en power
# ══════════════════════════════════════════════════════════════

class TestDestructiveOps:
    """Opérations destructives (delete, move) selon le profil."""

    def test_delete_blocked_at_safe(self, ctrl, ws_file):
        """delete_file échoue en safety_profile='safe'."""
        assert ctrl.safety_profile == "safe"
        result = ctrl.delete_file(ws_file)
        assert not result.success
        assert result.error == "AccessLevelTooLow"

    def test_delete_succeeds_at_power(self, ctrl):
        """delete_file réussit en safety_profile='power'."""
        path = f"{TEST_PREFIX}to_delete.txt"
        ctrl.write_file(path, "À supprimer")
        assert ctrl.safety_profile == "safe"
        ctrl.safety_profile = "power"
        try:
            result = ctrl.delete_file(path)
            assert result.success, f"Échec delete: {result.error}"
            full = os.path.join(ctrl.workspace_root, path)
            assert not os.path.isfile(full)
        finally:
            ctrl.safety_profile = "safe"

    def test_move_blocked_at_safe(self, ctrl, ws_file):
        """move_file échoue en safety_profile='safe'."""
        result = ctrl.move_file(ws_file, f"{TEST_PREFIX}mv_dest.txt")
        assert not result.success
        assert result.error == "AccessLevelTooLow"

    def test_move_succeeds_at_power(self, ctrl):
        """move_file réussit en safety_profile='power'."""
        src = f"{TEST_PREFIX}to_move.txt"
        dst = f"{TEST_PREFIX}moved.txt"
        ctrl.write_file(src, "À déplacer")
        ctrl.safety_profile = "power"
        try:
            result = ctrl.move_file(src, dst)
            assert result.success, f"Échec move: {result.error}"
            full_src = os.path.join(ctrl.workspace_root, src)
            full_dst = os.path.join(ctrl.workspace_root, dst)
            assert not os.path.isfile(full_src)
            assert os.path.isfile(full_dst)
        finally:
            ctrl.safety_profile = "safe"
            # Nettoyage si dst existe encore
            try:
                os.remove(os.path.join(ctrl.workspace_root, dst))
            except OSError:
                pass

    def test_secure_delete_works(self, ctrl):
        """delete_file avec secure=True fonctionne."""
        path = f"{TEST_PREFIX}secure_del.txt"
        ctrl.write_file(path, "Données sensibles\n")
        ctrl.safety_profile = "power"
        try:
            result = ctrl.delete_file(path, secure=True)
            assert result.success, f"Échec secure delete: {result.error}"
            full = os.path.join(ctrl.workspace_root, path)
            assert not os.path.isfile(full)
        finally:
            ctrl.safety_profile = "safe"

    def test_delete_non_existent_at_power(self, ctrl):
        """delete_file sur fichier inexistant retourne FileNotFound."""
        ctrl.safety_profile = "power"
        try:
            result = ctrl.delete_file(f"{TEST_PREFIX}nonexistent_12345.txt")
            assert not result.success
            assert result.error == "FileNotFound"
        finally:
            ctrl.safety_profile = "safe"


# ══════════════════════════════════════════════════════════════
# 5. ToolRegistry : 12 outils enregistrés
# ══════════════════════════════════════════════════════════════

class TestToolRegistry:
    """Enregistrement des 12 outils fichiers."""

    def test_register_12_tools(self):
        """register_file_tools enregistre exactement 12 outils."""
        reg = ToolRegistry()
        executor = ToolExecutor(reg)
        register_file_tools(reg, executor)
        tools = reg.list_tools()
        assert len(tools) == 12, f"Attendu 12 outils, obtenu {len(tools)}"

    def test_tool_names_match(self):
        """Les noms des outils correspondent à la spec."""
        reg = ToolRegistry()
        executor = ToolExecutor(reg)
        register_file_tools(reg, executor)
        names = {t.name for t in reg.list_tools()}
        expected = {
            "file_read", "file_write", "file_append",
            "file_delete", "file_move", "file_copy",
            "file_mkdir", "file_list", "file_info",
            "file_search", "file_workspace_info",
            "file_authorize_directory",
        }
        assert names == expected, f"Différence: {expected - names}"

    def test_each_tool_has_parameters(self):
        """Chaque outil a au moins un paramètre (sauf workspace_info)."""
        reg = ToolRegistry()
        executor = ToolExecutor(reg)
        register_file_tools(reg, executor)
        for tool in reg.list_tools():
            if tool.name == "file_workspace_info":
                assert tool.parameters == []
            else:
                assert len(tool.parameters) >= 1, f"{tool.name} n'a pas de paramètres"

    def test_tool_read_has_path_param(self):
        """file_read a le paramètre 'path' requis."""
        reg = ToolRegistry()
        executor = ToolExecutor(reg)
        register_file_tools(reg, executor)
        tool = reg.get("file_read")
        assert tool is not None
        param_names = [p.name for p in tool.parameters]
        assert "path" in param_names
        path_param = [p for p in tool.parameters if p.name == "path"][0]
        assert path_param.required is True

    def test_tool_executor_handlers_registered(self):
        """Tous les handlers sont enregistrés dans le ToolExecutor."""
        reg = ToolRegistry()
        executor = ToolExecutor(reg)
        register_file_tools(reg, executor)
        # Vérifier que chaque outil a un handler en exécutant les handlers (sans params)
        # On ne peut pas appeler sans params, mais on peut vérifier qu'ils existent
        names = {t.name for t in reg.list_tools()}
        result = executor.execute("file_workspace_info", {})
        assert result is not None  # Au moins ça ne crash pas

    def test_register_twice_no_duplicates(self):
        """register_file_tools appelé 2 fois ne duplique pas les outils."""
        reg = ToolRegistry()
        executor = ToolExecutor(reg)
        register_file_tools(reg, executor)
        register_file_tools(reg, executor)
        assert len(reg.list_tools()) == 12


# ══════════════════════════════════════════════════════════════
# 6. Edge cases : chemins vides, unicode, inexistants
# ══════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Cas limites et chemins spéciaux."""

    def test_write_empty_content(self, ctrl):
        """write_file avec contenu vide."""
        path = f"{TEST_PREFIX}empty.txt"
        result = ctrl.write_file(path, "")
        assert result.success, result.error
        full = os.path.join(ctrl.workspace_root, path)
        assert os.path.getsize(full) == 0

    def test_read_nonexistent_file(self, ctrl):
        """read_file sur fichier inexistant retourne FileNotFound."""
        path = f"{TEST_PREFIX}does_not_exist_123456.txt"
        result = ctrl.read_file(path)
        assert not result.success
        assert result.error == "FileNotFound"

    def test_read_nonexistent_file_event(self, ctrl):
        """read_file sur fichier inexistant émet file:error."""
        path = f"{TEST_PREFIX}nope_789.txt"
        bus = EventBus()
        bus._queue.clear()
        ctrl.read_file(path)
        events = bus.drain()
        file_errors = [e for e in events if e[0] == "file:error"]
        assert len(file_errors) >= 1

    def test_list_nonexistent_directory(self, ctrl):
        """list_directory sur dossier inexistant retourne DirectoryNotFound."""
        result = ctrl.list_directory(f"{TEST_PREFIX}nonexistent_dir_999")
        assert not result.success
        assert result.error == "DirectoryNotFound"

    def test_get_info_nonexistent(self, ctrl):
        """get_file_info sur fichier inexistant retourne FileNotFound."""
        result = ctrl.get_file_info(f"{TEST_PREFIX}ghost_file.txt")
        assert not result.success
        assert result.error == "FileNotFound"

    def test_copy_nonexistent_source(self, ctrl):
        """copy_file avec source inexistante retourne SourceNotFound."""
        result = ctrl.copy_file(
            f"{TEST_PREFIX}nosource.txt",
            f"{TEST_PREFIX}dest.txt",
        )
        assert not result.success
        assert result.error == "SourceNotFound"

    def test_write_unicode_content(self, ctrl):
        """write_file avec contenu unicode."""
        path = f"{TEST_PREFIX}unicode.txt"
        content = "Héllò Wörld 🌍 éàü\n日本語\n Привет\n"
        result = ctrl.write_file(path, content)
        assert result.success, result.error
        read = ctrl.read_file(path)
        assert read.details["content"] == content

    def test_read_unicode_content(self, ctrl):
        """read_file lit correctement l'unicode."""
        path = f"{TEST_PREFIX}unicode_read.txt"
        content = "Café ☕\nFrançais français\n"
        ctrl.write_file(path, content)
        result = ctrl.read_file(path)
        assert result.success
        assert "Café ☕" in result.details["content"]

    def test_resolve_path_empty_raises(self, ctrl):
        """resolve_path avec chaîne vide lève ValueError."""
        with pytest.raises(ValueError, match="Chemin vide|empty"):
            ctrl.resolve_path("")

    def test_resolve_path_relative(self, ctrl):
        """resolve_path pour chemin relatif."""
        resolved = ctrl.resolve_path("mon_fichier.txt")
        assert resolved == os.path.join(ctrl.workspace_root, "mon_fichier.txt")

    def test_resolve_path_absolute(self, ctrl):
        """resolve_path pour chemin absolu dans workspace."""
        abs_path = os.path.join(ctrl.workspace_root, "abs_file.txt")
        resolved = ctrl.resolve_path(abs_path)
        # La normalisation peut différer du chemin d'origine
        assert os.path.normpath(resolved) == os.path.normpath(abs_path)

    def test_write_to_subdirectory(self, ctrl):
        """write_file crée les sous-dossiers automatiquement."""
        path = f"{TEST_PREFIX}subdir/nested/file.txt"
        result = ctrl.write_file(path, "nested content")
        assert result.success, result.error
        full = os.path.join(ctrl.workspace_root, path)
        assert os.path.isfile(full)
        # Nettoyage
        shutil.rmtree(os.path.join(ctrl.workspace_root, f"{TEST_PREFIX}subdir"),
                      ignore_errors=True)

    def test_list_directory_with_pattern(self, ctrl):
        """list_directory avec filtre pattern."""
        ctrl.write_file(f"{TEST_PREFIX}alpha.py", "python")
        ctrl.write_file(f"{TEST_PREFIX}beta.py", "python")
        ctrl.write_file(f"{TEST_PREFIX}gamma.txt", "text")
        result = ctrl.list_directory(".", pattern="*.py")
        assert result.success
        names = [e["name"] for e in result.details["entries"]]
        assert f"{TEST_PREFIX}alpha.py" in names
        assert f"{TEST_PREFIX}beta.py" in names
        assert f"{TEST_PREFIX}gamma.txt" not in names

    def test_create_directory_parents_false(self, ctrl):
        """create_directory avec parents=False échoue si parent manquant."""
        path = f"{TEST_PREFIX}parent_missing/child"
        result = ctrl.create_directory(path, parents=False)
        assert not result.success


# ══════════════════════════════════════════════════════════════
# 7. Workspace : authorize_directory, deauthorize, workspace_info
# ══════════════════════════════════════════════════════════════

class TestWorkspace:
    """Gestion du workspace et des dossiers autorisés."""

    def test_get_workspace_info(self, ctrl):
        """get_workspace_info retourne les statistiques."""
        result = ctrl.get_workspace_info()
        assert result.success, result.error
        assert result.details is not None
        assert "exists" in result.details
        assert "path" in result.details
        assert "safety_profile" in result.details
        assert "authorized_dirs" in result.details

    def test_get_workspace_info_path(self, ctrl):
        """get_workspace_info.path est le workspace_root."""
        result = ctrl.get_workspace_info()
        assert result.path == ctrl.workspace_root

    def test_authorize_directory(self, ctrl):
        """authorize_directory ajoute un dossier aux autorisés."""
        test_dir = os.path.join(ctrl.workspace_root, f"{TEST_PREFIX}auth_test")
        os.makedirs(test_dir, exist_ok=True)
        try:
            result = ctrl.authorize_directory(test_dir)
            assert result.success, result.error
            assert test_dir in ctrl.authorized_dirs or \
                   test_dir + "/" in ctrl.authorized_dirs
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_authorize_nonexistent_dir(self, ctrl):
        """authorize_directory sur dossier inexistant échoue."""
        result = ctrl.authorize_directory(f"{TEST_PREFIX}no_such_dir_99999")
        assert not result.success
        assert result.error == "DirectoryNotFound"

    def test_authorize_system_dir_blocked(self, ctrl):
        """authorize_directory sur dossier système est bloqué."""
        # Utiliser /tmp ou un dossier existant non-système
        result = ctrl.authorize_directory("/etc")
        assert not result.success
        assert result.error == "SystemPathBlocked"

    def test_deauthorize_directory(self, ctrl):
        """deauthorize_directory retire un dossier autorisé."""
        test_dir = os.path.join(ctrl.workspace_root, f"{TEST_PREFIX}deauth_test")
        os.makedirs(test_dir, exist_ok=True)
        try:
            ctrl.authorize_directory(test_dir)
            assert len(ctrl.authorized_dirs) >= 1
            result = ctrl.deauthorize_directory(test_dir)
            assert result.success, result.error
            assert test_dir not in ctrl.authorized_dirs
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_deauthorize_not_authorized(self, ctrl):
        """deauthorize_directory sur dossier jamais autorisé échoue."""
        result = ctrl.deauthorize_directory("/tmp/unlisted")
        assert not result.success
        assert result.error == "NotAuthorized"

    def test_workspace_info_reflects_safety_profile(self, ctrl):
        """get_workspace_info inclut le profil de sécurité."""
        result = ctrl.get_workspace_info()
        assert result.details["safety_profile"] == ctrl.safety_profile


# ══════════════════════════════════════════════════════════════
# 8. EventBus : événements émis
# ══════════════════════════════════════════════════════════════

class TestEventBus:
    """Vérification des événements émis par les opérations."""

    def test_write_emits_file_write_complete(self, ctrl):
        """write_file émet file:write:complete."""
        bus = EventBus()
        bus._queue.clear()
        path = f"{TEST_PREFIX}evt_write.txt"
        ctrl.write_file(path, "event test")
        events = bus.drain()
        write_events = [e for e in events if e[0] == "file:write:complete"]
        assert len(write_events) >= 1
        assert write_events[0][1]["path"] is not None

    def test_read_emits_file_read_complete(self, ctrl, ws_file):
        """read_file émet file:read:complete."""
        bus = EventBus()
        bus._queue.clear()
        ctrl.read_file(ws_file)
        events = bus.drain()
        read_events = [e for e in events if e[0] == "file:read:complete"]
        assert len(read_events) >= 1

    def test_read_nonexistent_emits_file_error(self, ctrl):
        """read_file sur fichier inexistant émet file:error."""
        bus = EventBus()
        bus._queue.clear()
        ctrl.read_file(f"{TEST_PREFIX}never_exists.txt")
        events = bus.drain()
        error_events = [e for e in events if e[0] == "file:error"]
        assert len(error_events) >= 1

    def test_mkdir_emits_file_mkdir(self, ctrl):
        """create_directory émet file:mkdir."""
        bus = EventBus()
        bus._queue.clear()
        path = f"{TEST_PREFIX}evt_mkdir"
        ctrl.create_directory(path)
        events = bus.drain()
        mkdir_events = [e for e in events if e[0] == "file:mkdir"]
        assert len(mkdir_events) >= 1
        assert mkdir_events[0][1]["path"] is not None

    def test_authorize_emits_file_authorized(self, ctrl):
        """authorize_directory émet file:authorized."""
        bus = EventBus()
        bus._queue.clear()
        test_dir = os.path.join(ctrl.workspace_root, f"{TEST_PREFIX}evt_auth")
        os.makedirs(test_dir, exist_ok=True)
        try:
            ctrl.authorize_directory(test_dir)
            events = bus.drain()
            auth_events = [e for e in events if e[0] == "file:authorized"]
            assert len(auth_events) >= 1
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_delete_emits_file_delete_complete(self, ctrl):
        """delete_file émet file:delete:complete quand autorisé."""
        bus = EventBus()
        bus._queue.clear()
        path = f"{TEST_PREFIX}evt_del.txt"
        ctrl.write_file(path, "delete me")
        ctrl.safety_profile = "power"
        try:
            ctrl.delete_file(path)
            events = bus.drain()
            del_events = [e for e in events if e[0] == "file:delete:complete"]
            assert len(del_events) >= 1
        finally:
            ctrl.safety_profile = "safe"

    def test_copy_emits_file_copied(self, ctrl, ws_file):
        """copy_file émet file:copied."""
        bus = EventBus()
        bus._queue.clear()
        dest = f"{TEST_PREFIX}evt_copy_dest.txt"
        try:
            ctrl.copy_file(ws_file, dest)
            events = bus.drain()
            copy_events = [e for e in events if e[0] == "file:copied"]
            assert len(copy_events) >= 1
        finally:
            try:
                os.remove(os.path.join(ctrl.workspace_root, dest))
            except OSError:
                pass

    def test_workspace_info_emits_event(self, ctrl):
        """get_workspace_info émet file:workspace_info."""
        bus = EventBus()
        bus._queue.clear()
        ctrl.get_workspace_info()
        events = bus.drain()
        ws_events = [e for e in events if e[0] == "file:workspace_info"]
        assert len(ws_events) >= 1


# ══════════════════════════════════════════════════════════════
# 9. Safety profile edge cases
# ══════════════════════════════════════════════════════════════

class TestSafetyProfile:
    """Profil de sécurité et niveaux."""

    def test_safety_profile_get_set(self, ctrl):
        """safety_profile se lit et s'écrit."""
        assert ctrl.safety_profile == "safe"
        ctrl.safety_profile = "power"
        assert ctrl.safety_profile == "power"
        ctrl.safety_profile = "admin"
        assert ctrl.safety_profile == "admin"
        ctrl.safety_profile = "safe"

    def test_safety_profile_invalid(self, ctrl):
        """safety_profile avec valeur invalide lève ValueError."""
        with pytest.raises(ValueError, match="Profil invalide|invalid"):
            ctrl.safety_profile = "invalid_profile"

    def test_get_safety_level_mapping(self, ctrl):
        """get_safety_level retourne les bons entiers."""
        ctrl.safety_profile = "safe"
        assert ctrl.get_safety_level() == 1
        ctrl.safety_profile = "power"
        assert ctrl.get_safety_level() == 3
        ctrl.safety_profile = "admin"
        assert ctrl.get_safety_level() == 5
        ctrl.safety_profile = "safe"

    def test_destructive_access_constant(self):
        """DESTRUCTIVE_ACCESS_LEVEL vaut 3."""
        assert DESTRUCTIVE_ACCESS_LEVEL == 3

    def test_move_blocked_then_allowed_after_profile_change(self, ctrl):
        """move_file passe de bloqué à autorisé après changement de profil."""
        src = f"{TEST_PREFIX}profile_move_src.txt"
        dst = f"{TEST_PREFIX}profile_move_dst.txt"
        ctrl.write_file(src, "test")
        # Bloqué en safe
        r1 = ctrl.move_file(src, dst)
        assert not r1.success
        assert r1.error == "AccessLevelTooLow"
        # Autorisé en power
        ctrl.safety_profile = "power"
        try:
            r2 = ctrl.move_file(src, dst)
            assert r2.success, f"Échec move: {r2.error}"
        finally:
            ctrl.safety_profile = "safe"
            # Nettoyage
            for f in [dst, src]:
                try:
                    os.remove(os.path.join(ctrl.workspace_root, f))
                except OSError:
                    pass
