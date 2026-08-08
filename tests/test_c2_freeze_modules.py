"""Tests C2 V18.1 — gel V18-21 : instanciation différée des modules morts.

Cible : src/nuru_core.py + src/config.py

Vérifie :
- flag unique `freeze_dead_modules` présent et True par défaut (GELÉ) ;
- plus aucun import top-level des modules gelés dans nuru_core.py ;
- socket MCP HTTP 8765 supprimé (start_http absent du code) ;
- les instanciations de __init__ et les boucles background gatées par le flag ;
- les méthodes _ensure_*() instancient + enregistrent au kernel à la demande,
  sont idempotentes (chemin rollback / consommateurs actifs).

Méthode : inspection AST (précédent test_nuru_core_lora_init.py) + tests
comportementaux légers sur les _ensure_*() — pas d'instanciation complète de
NuruCore (cascade de dépendances + effets de bord fichiers, cf. C1). La
non-importation effective au boot (sys.modules) et le delta RAM sont mesurés
hors pytest (process isolé, méthode architecte spec V18.1 C2 §2.6).
"""

import ast
from pathlib import Path

import pytest

from src.config import config
from src.kernel import NuruKernel

NURU_CORE_PATH = Path(__file__).parent.parent / "src" / "nuru_core.py"
CONFIG_PATH = Path(__file__).parent.parent / "src" / "config.py"

FROZEN_TOP_LEVEL_IMPORTS = (
    "src.knowledge.graph",
    "src.proactive.engine",
    "src.proactive.routines",
    "src.mcp.server",
    "src.mcp.client",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse(path: Path) -> ast.Module:
    return ast.parse(_read(path))


def _method(tree: ast.Module, name: str):
    """Retourne la méthode `name` (sync ou async) dans l'arbre."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"méthode {name} introuvable dans nuru_core.py")


def _source_segment(tree: ast.Module, node: ast.AST) -> str:
    return ast.get_source_segment(_read(NURU_CORE_PATH), node) or ""


# ── Flag unique (config.py) ─────────────────────────────────────────────


class TestConfigFlag:
    def test_flag_exists_and_default_frozen(self):
        """freeze_dead_modules existe et vaut True par défaut (GELÉ, V18-21)."""
        assert hasattr(config, "freeze_dead_modules")
        assert config.freeze_dead_modules is True

    def test_flag_is_bool_field(self):
        """freeze_dead_modules est déclaré comme champ booléen."""
        tree = _parse(CONFIG_PATH)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id == "freeze_dead_modules":
                    assert (
                        isinstance(node.annotation, ast.Name)
                        and node.annotation.id == "bool"
                    ), "freeze_dead_modules doit être un champ bool"
                    found = True
        assert found, "freeze_dead_modules doit être déclaré dans config.py"


# ── Import différé (nuru_core.py) ───────────────────────────────────────


class TestLazyImports:
    def test_no_top_level_import_of_frozen_modules(self):
        """Aucun import top-level des modules gelés dans nuru_core.py.

        Les seuls imports restants sont LOCAUX dans les _ensure_*()
        (T-C2-3 structurel : c'est ce qui vide sys.modules au boot).
        """
        tree = _parse(NURU_CORE_PATH)

        top_level_imports = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    top_level_imports.append(alias.name)

        for mod in FROZEN_TOP_LEVEL_IMPORTS:
            assert mod not in top_level_imports, (
                f"import top-level de {mod} encore présent — le gel V18-21 exige "
                "un import lazy dans _ensure_*()"
            )

    def test_local_imports_present_in_ensure_methods(self):
        """Chaque _ensure_* contient l'import lazy de son module."""
        source = _read(NURU_CORE_PATH)
        assert "from src.knowledge.graph import KnowledgeGraph" in source
        assert "from src.proactive.engine import ProactiveEngine" in source
        assert "from src.proactive.routines import RoutineScheduler, RoutinePreset" in source
        assert "from src.mcp.server import MCPServer" in source
        assert "from src.mcp.client import MCPClient" in source


# ── Socket MCP 8765 (nuru_core.py) ──────────────────────────────────────


class TestSocket8765Removed:
    def test_start_http_absent(self):
        """start_http(port=8765) a disparu du code (suppression définitive)."""
        source = _read(NURU_CORE_PATH)
        assert "start_http" not in source, (
            "start_http(port=8765) doit être supprimé — zéro client connecté (V18-21)"
        )


# ── Gates d'instanciation et de boucles (nuru_core.py) ──────────────────


class TestInitGates:
    def test_init_calls_ensure_under_flag(self):
        """__init__ instancie les modules gelés UNIQUEMENT si le flag est off."""
        tree = _parse(NURU_CORE_PATH)
        init = _method(tree, "__init__")

        ensure_calls = [
            "_ensure_knowledge_graph",
            "_ensure_sleep_cycle",
            "_ensure_proactive",
            "_ensure_routines",
            "_ensure_mcp",
        ]
        for call in ensure_calls:
            # chaque appel doit exister DANS __init__ et sous un If freeze_dead_modules
            found = False
            for node in ast.walk(init):
                if isinstance(node, ast.If) and "freeze_dead_modules" in ast.unparse(node.test):
                    if f"self.{call}()" in ast.unparse(node):
                        found = True
                        break
            assert found, (
                f"{call} doit être appelé depuis __init__ sous "
                "`if not config.freeze_dead_modules:`"
            )

    def test_start_background_tasks_gates_loops_and_removes_mcp(self):
        """Les boucles sleep/proactive sont gatées ; le bloc MCP HTTP a disparu."""
        tree = _parse(NURU_CORE_PATH)
        sbt = _method(tree, "start_background_tasks")
        source = _source_segment(tree, sbt)

        # les deux boucles sont créées sous gate flag
        for loop in ("_sleep_cycle_loop", "_proactive_collect_loop"):
            assert "if not config.freeze_dead_modules:" in source, (
                f"start_background_tasks doit gater {loop} derrière freeze_dead_modules"
            )
            assert f"{loop}()" in source, (
                f"start_background_tasks doit référencer {loop}"
            )
        # plus aucun start_http
        assert "start_http" not in source

    def test_loop_bodies_defense_in_depth(self):
        """Les deux boucles retournent immédiatement si le flag est on (défense)."""
        tree = _parse(NURU_CORE_PATH)
        for method in ("_sleep_cycle_loop", "_proactive_collect_loop"):
            fn = _method(tree, method)
            first = next(
                stmt for stmt in fn.body
                if not (
                    isinstance(stmt, ast.Expr)
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)
                )
            )
            assert isinstance(first, ast.If), (
                f"{method} doit commencer par une garde de gel"
            )
            assert "freeze_dead_modules" in ast.unparse(first.test)


# ── Consommateur actif : process_query → lazy sleep_cycle ────────────────


class TestProcessQuerySleepCycle:
    def test_uses_lazy_ensure(self):
        """process_query passe par _ensure_sleep_cycle() (consommateur actif)."""
        tree = _parse(NURU_CORE_PATH)
        pq = _method(tree, "process_query")
        source = _source_segment(tree, pq)
        assert "_ensure_sleep_cycle().user_activity_detected()" in source
        assert "k('sleep_cycle').user_activity_detected()" not in source


# ── Comportement des _ensure_*() (lazy, idempotent, registre kernel) ─────


@pytest.fixture()
def fresh_nuru_like():
    """Instance NuruCore sans __init__ + kernel neuf (évite la cascade)."""
    from src.nuru_core import NuruCore

    NuruKernel._instance = None
    NuruKernel._initialized = False
    n = NuruCore.__new__(NuruCore)
    n._kernel = NuruKernel()
    n.k = n._kernel.get
    yield n
    NuruKernel._instance = None
    NuruKernel._initialized = False


class TestEnsureLazyBehavior:
    def test_ensure_sleep_cycle_registers_and_idempotent(self, fresh_nuru_like):
        n = fresh_nuru_like
        assert n._kernel.has("sleep_cycle") is False

        sc = n._ensure_sleep_cycle()
        assert sc is not None
        assert n._kernel.get("sleep_cycle") is sc
        assert n._ensure_sleep_cycle() is sc, "_ensure_sleep_cycle doit être idempotent"

    def test_ensure_proactive_registers_collectors(self, fresh_nuru_like):
        n = fresh_nuru_like
        engine = n._ensure_proactive()
        assert engine is not None
        assert n._kernel.get("proactive") is engine
        # les collecteurs ont été enregistrés (clock + memory)
        assert len(engine._collectors) >= 2, (
            "_ensure_proactive doit brancher les collecteurs (_register_proactive_collectors)"
        )
        assert n._ensure_proactive() is engine

    def test_ensure_routines_loads_default_preset(self, fresh_nuru_like):
        n = fresh_nuru_like
        routines = n._ensure_routines()
        assert routines is not None
        assert n._kernel.get("routines") is routines
        assert len(routines.get_active()) == 2, (
            "le preset par défaut (matin + soir) doit être chargé"
        )
        assert n._ensure_routines() is routines

    def test_ensure_mcp_registers_tools(self, fresh_nuru_like):
        n = fresh_nuru_like
        server = n._ensure_mcp()
        assert server is not None
        assert n._kernel.has("mcp_server") is False  # non enregistré au kernel
        assert n.mcp_client is not None
        assert len(n.mcp_server.tools) >= 4, (
            "les outils MCP internes doivent être enregistrés (_register_mcp_tools)"
        )
        assert n._ensure_mcp() is server

    def test_ensure_knowledge_graph_creates_and_registers(self, fresh_nuru_like, monkeypatch):
        """_ensure_knowledge_graph instancie + init + enregistre (mocké, pas de DB)."""
        import sys
        import types
        from unittest.mock import MagicMock

        n = fresh_nuru_like
        fake_kg = MagicMock()
        fake_module = types.ModuleType("src.knowledge.graph")
        setattr(fake_module, "KnowledgeGraph", lambda: fake_kg)
        monkeypatch.setitem(sys.modules, "src.knowledge.graph", fake_module)

        kg = n._ensure_knowledge_graph()
        assert kg is fake_kg
        fake_kg.init.assert_called_once()
        assert n._kernel.get("knowledge_graph") is kg
        assert n._ensure_knowledge_graph() is kg
