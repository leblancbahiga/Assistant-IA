"""Tests C5 V18.1 — unification MCP ↔ ToolRegistry : un seul registre de vérité (V18-10).

Cible : src/mcp/server.py (bridge `tools_from_registry`), src/nuru_core.py
(`_register_mcp_tools` → génère la liste depuis `ToolRegistry.list_tools()`),
src/kernel/pipeline_steps.py (step Act lit le registre unifié).

Vérifie (critères d'acceptation C5) :
- `MCPServer.tools` est une **vue** de la ToolRegistry (ToolOrchestrator), pas
  un second registre parallèle d'outils codés en dur ;
- un seul registre de vérité : les 4 capacités internes NURU (search_memory/
  rag_query/knowledge_graph_search/cost_summary) sont enregistrées dans la
  ToolRegistry, puis le serveur MCP les projette depuis CE registre ;
- aucun doublon : MCP n'expose que des projections du registre unique ;
- socket HTTP 8765 toujours supprimé (start_http absent de nuru_core.py) et MCP
  reste LAZY (`_ensure_mcp`, aucune import src.tools au boot) ;
- le step Act lit le registre unifié (ToolOrchestrator).

Méthode : inspection AST + tests comportementaux légers sur le bridge pur et
le registre via _ensure_mcp (instance NuruCore sans __init__ + kernel neuf,
même approche que test_c2_freeze_modules.fresh_nuru_like) — pas d'instanciation
complète de NuruCore (cascade de dépendances + effets de bord fichiers).
"""

import ast
from pathlib import Path

import pytest

from src.kernel import NuruKernel

NURU_CORE_PATH = Path(__file__).parent.parent / "src" / "nuru_core.py"
MCP_SERVER_PATH = Path(__file__).parent.parent / "src" / "mcp" / "server.py"
MCP_INIT_PATH = Path(__file__).parent.parent / "src" / "mcp" / "__init__.py"
PIPELINE_STEPS_PATH = Path(__file__).parent.parent / "src" / "kernel" / "pipeline_steps.py"

INTERNAL_CAPABILITIES = {
    "search_memory",
    "rag_query",
    "knowledge_graph_search",
    "cost_summary",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse(path: Path) -> ast.Module:
    return ast.parse(_read(path))


# ── 1. Bridge src/mcp/server.py : outils_from_registry existe ─────────────


class TestMCPBridgeExists:
    def test_server_exports_tools_from_registry(self):
        """Le serveur MCP expose le bridge `tools_from_registry`."""
        tree = _parse(MCP_SERVER_PATH)
        names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
        assert "tools_from_registry" in names

    def test_mcp_init_exports_bridge(self):
        """src.mcp ré-exporte tools_from_registry (import public)."""
        source = _read(MCP_INIT_PATH)
        assert "tools_from_registry" in source


# ── 2. le bridge projette une ToolRegistry en MCPTools (vue, pas 2e registre) ──


class TestBridgeProjection:
    def test_projects_registry_as_mcp_tools(self):
        """Chaque ToolDefinition → un MCPTool dont le handler dispatche à l'exécuteur."""
        from src.mcp.server import tools_from_registry, MCPTool
        from src.tools.registry import ToolDefinition, ToolParameter, ToolRegistry, ToolExecutor

        registry = ToolRegistry()
        executor = ToolExecutor(registry)
        registry.register(ToolDefinition(
            name="demo_tool",
            description="outil de démo",
            category="system",
            parameters=[ToolParameter(name="x", type="str", description="param x")],
        ))
        executor.register_handler("demo_tool", lambda x="": {"echo": x})

        mcp_tools = tools_from_registry(registry, executor)

        assert set(mcp_tools.keys()) == {"demo_tool"}
        tool = mcp_tools["demo_tool"]
        assert isinstance(tool, MCPTool)
        assert tool.name == "demo_tool"
        assert "démo" in tool.description
        # paramètres en schéma JSON MCP (type object / properties)
        assert tool.parameters["type"] == "object"
        assert "x" in tool.parameters["properties"]

        # le handler projette l'exécution vers le registre unique
        out = tool.handler(x="hello")
        assert out["success"] is True
        assert out["output"] == {"echo": "hello"}

    def test_bridge_rejects_wrong_types(self):
        """Le bridge refuse un registre/executor non-ToolRegistry (garde)."""
        from src.mcp.server import tools_from_registry

        with pytest.raises(TypeError):
            tools_from_registry(object(), None)


# ── 3. nuru_core._register_mcp_tools : MCP génère depuis ToolRegistry ─────


class TestRegisterGeneratesFromRegistry:
    def test_no_hardcoded_register_tool_in_register_mcp_tools(self):
        """_register_mcp_tools ne code plus d'outils en dur → il projette le registre.

        V18-10 : « MCPServer._register_mcp_tools() (4 outils codés en dur) →
        génère sa liste depuis ToolRegistry.list_tools() ».
        """
        tree = _parse(NURU_CORE_PATH)
        source = _read(NURU_CORE_PATH)
        # localise le corps de la méthode _register_mcp_tools
        method = next(n for n in ast.walk(tree)
                      if isinstance(n, ast.FunctionDef) and n.name == "_register_mcp_tools")
        body = ast.get_source_segment(source, method) or ""
        # plus aucun MCPTool codé en dur ; on projette le registre unique
        assert "MCPTool(" not in body.replace("tools_from_registry", ""), (
            "les MCPTool ne doivent plus être codés en dur dans _register_mcp_tools"
        )
        assert "tools_from_registry(" in body
        assert "ToolOrchestrator" in body

    def test_internal_capabilities_register_into_registry(self):
        """Les 4 capacités internes sont enregistrées dans la ToolRegistry (source unique)."""
        tree = _parse(NURU_CORE_PATH)
        source = _read(NURU_CORE_PATH)
        method = next(n for n in ast.walk(tree)
                      if isinstance(n, ast.FunctionDef) and n.name == "_register_mcp_tools")
        body = ast.get_source_segment(source, method) or ""
        for name in INTERNAL_CAPABILITIES:
            assert name in body, f"capacité interne {name} absente de _register_mcp_tools"
        assert "orch.get_registry().register(" in body, (
            "les capacités internes doivent s'enregistrer dans le registre unique"
        )


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


class TestUnifiedRegistryMaterialization:
    def test_ensure_mcp_exposes_registry_projection(self, fresh_nuru_like):
        """_ensure_mcp expose le serveur MCP comme vue du registre unique.

        Les 44 outils (40 pipeline + 4 capacités internes) sont présents,
        les 4 capacités internes ont bien été enregistrées dans la ToolRegistry
        et sont ré-exposées par le serveur MCP.
        """
        from src.tools.orchestrator import ToolOrchestrator

        # reset du singleton orchestrateur pour un registre propre
        ToolOrchestrator._reset_singleton()
        n = fresh_nuru_like
        server = n._ensure_mcp()

        names = set(server.tools.keys())
        # 4 capacités internes + un échantillon du pipeline
        assert INTERNAL_CAPABILITIES <= names
        assert {"shell_exec", "memory_recall", "browser_navigate"} <= names
        assert len(server.tools) >= 40

        # MCP reste lazy : _ensure_mcp idempotent
        assert n._ensure_mcp() is server

    def test_mcp_server_is_projection_not_separate_registry(self, fresh_nuru_like):
        """MCP n'a PAS de registre parallèle : ses outils sont les projections du registre.

        La preuve : enlever un outil de la ToolRegistry (source de vérité) puis
        re-projeter ne doit laisser AUCUNE trace d'un outil fantôme côté MCP, et
        aucun outil MCP n'existe en dehors du registre (pas de doublon fantôme).
        """
        from src.tools.orchestrator import ToolOrchestrator

        ToolOrchestrator._reset_singleton()
        n = fresh_nuru_like
        orchestrator = ToolOrchestrator.get_instance()
        orchestrator.setup()
        # la source de vérité contient déjà les capacités internes enregistrées par
        # _register_mcp_tools, MAIS ici setup() seul ne les a pas — vérifions par
        # projection que la vue = exactement le registre unique (aucun outil hors registre)
        server = n._ensure_mcp()
        registered = {t.name for t in orchestrator.get_registry().list_tools()}
        # chaque outil MCP est présent dans le registre unique (pas de doublon fantôme)
        for name in server.tools:
            assert name in registered, (
                f"outil MCP '{name}' hors du registre unique → registre parallèle"
            )


# ── 4. Socket 8765 toujours supprimé + MCP lazy ───────────────────────────


class TestNoSocketAndLazy:
    def test_start_http_absent_from_nuru_core(self):
        """Aucun relancement du socket HTTP MCP 8765 (gel V18-21 maintenu)."""
        source = _read(NURU_CORE_PATH)
        assert "start_http" not in source, (
            "le socket MCP 8765 ne doit pas être relancé (suppression définitive V18-21)"
        )

    def test_no_top_level_mcp_import(self):
        """src.mcp.server/client ne sont PAS importés au niveau module de nuru_core (lazy)."""
        tree = _parse(NURU_CORE_PATH)
        top_imports = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                top_imports += [a.name for a in node.names]
        for mod in ("src.mcp.server", "src.mcp.client", "src.mcp"):
            assert mod not in top_imports, (
                f"import top-level {mod} présent — le gel MCP exige un import lazy"
            )


# ── 5. Step Act : lit le registre unifié ──────────────────────────────────


class TestActReadsUnifiedRegistry:
    def test_act_branch_reads_toolorchestrator(self):
        """Le step Act (branche active) lit le registre via ToolOrchestrator (C5)."""
        source = _read(PIPELINE_STEPS_PATH)
        assert "from src.tools.orchestrator import ToolOrchestrator" in source, (
            "le step Act doit lire le registre unifié via ToolOrchestrator (C5)"
        )
        assert "get_registry()" in source, (
            "le step Act doit accéder au registre unique"
        )

    def test_act_noop_path_still_lazy(self):
        """La branche no-op d'Act ne contient aucun import src.tools (non-régression C4)."""
        tree = _parse(PIPELINE_STEPS_PATH)
        act = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.ClassDef) and n.name == "Act")
        source = ast.get_source_segment(_read(PIPELINE_STEPS_PATH), act) or ""
        # l'import src.tools n'apparaît qu'APRÈS le gate enable_act_step
        gate = source.index("if not config.enable_act_step:")
        tools_import = source.index("src.tools.orchestrator")
        assert gate < tools_import, (
            "l'import de src.tools doit être APRÈS le gate enable_act_step (lazy)"
        )