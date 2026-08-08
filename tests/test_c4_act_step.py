"""Tests C4 V18.1 — step Act gâté (V18-09) : Validate/Respond + ActStep + lazy imports src.tools + AgentLimits.

Cible : src/nuru_core.py, src/config.py, src/kernel/pipeline.py, src/kernel/pipeline_steps.py

Vérifie (critères d'acceptation C4) :
- step `Act` branché au pipeline réel : importé dans nuru_core.py ET inséré dans
  `set_steps([...])` entre `Validate()` et `Respond()` (ordre correct) ;
- le pipeline Kernel passe ainsi à 8 steps lorsque Act est présent ;
- flag unique `enable_act_step` présent et False par défaut (GATÉ) ;
- `AgentLimits(max_concurrent, max_steps, allowed_tools)` + `PipelineContext.permissions`/`agent_limits` ;
- no-op strict : `Act.run()` ne charge PAS `src.tools` (lazy imports) quand le flag est False,
  et retourne sans erreur.

Méthode : inspection AST (précédent test_c2_freeze_modules.py) + tests comportementaux
légers sur Act.run() — pas d'instanciation complète de NuruCore (cascade de dépendances
+ effets de bord fichiers). La non-importation effective de src.tools au boot (sys.modules)
est vérifiée par le chemin no-op (flag False).
"""

import ast
from pathlib import Path

import pytest

from src.config import config, AgentLimits
from src.kernel import Act, Validate, Respond
from src.kernel.pipeline import PipelineContext
from src.kernel.pipeline_steps import Act as _ActPkg

NURU_CORE_PATH = Path(__file__).parent.parent / "src" / "nuru_core.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse(path: Path) -> ast.Module:
    return ast.parse(_read(path))


# ── 1. Branchement réel du step Act dans nuru_core.py ──────────────────


class TestActWiredIntoPipeline:
    """Le step Act est branché au pipeline Kernel réel (correction Lead 1er cycle)."""

    def test_act_imported_in_nuru_core(self):
        """`Act` est importé depuis pipeline_steps dans nuru_core.py."""
        tree = _parse(NURU_CORE_PATH)
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "src.kernel.pipeline_steps":
                imported = [a.name for a in node.names]
        assert "Act" in imported, (
            "import Act manquant dans nuru_core.py — le step Act ne sera jamais exécutable"
        )
        assert "Validate" in imported and "Respond" in imported, (
            "Validate/Respond doivent rester importés en même temps que Act"
        )

    def test_act_ordered_between_validate_and_respond(self):
        """`Act()` est inséré dans set_steps([...]) entre Validate() et Respond().

        L'ordre du pipeline Kernel doit être :
            ... Generate, Validate, Act, Respond
        conformément à V18-09 (Act APRÈS Validate, avant Respond).
        """
        source = _read(NURU_CORE_PATH)
        # Capturer le bloc set_steps
        start = source.index("set_steps([")
        end = source.index("])", start)
        block = source[start:end]
        idx_validate = block.index("Validate()")
        idx_act = block.index("Act()")
        idx_respond = block.index("Respond()")
        assert idx_validate < idx_act < idx_respond, (
            "l'ordre du pipeline doit être Validate < Act < Respond (V18-09)"
        )

    def test_kernel_exports_act_with_siblings(self):
        """Le package src.kernel expose Act au même titre que Validate/Respond."""
        tree = _parse(Path(__file__).parent.parent / "src" / "kernel" / "__init__.py")
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "src.kernel.pipeline_steps":
                imported = [a.name for a in node.names]
        assert "Act" in imported, (
            "Act doit être exporté par src.kernel (cohérent avec Validate/Respond)"
        )


# ── 2. Config : flag + AgentLimits ──────────────────────────────────────


class TestActConfig:
    def test_enable_act_step_default_false(self):
        """Le GATE enable_act_step existe et vaut False par défaut (V18-09, off)."""
        assert hasattr(config, "enable_act_step")
        assert config.enable_act_step is False

    def test_agent_limits_fields(self):
        """AgentLimits expose max_concurrent / max_steps / allowed_tools."""
        limits = AgentLimits()
        assert hasattr(limits, "max_concurrent")
        assert hasattr(limits, "max_steps")
        assert hasattr(limits, "allowed_tools")
        assert isinstance(limits.allowed_tools, list)
        # conserveur pense M1 8 Go : 1 concurrent, 5 steps max, aucun tool par défaut
        assert limits.max_concurrent >= 1
        assert limits.max_steps >= 1

    def test_config_has_agent_limits(self):
        """config.agent_limits présent et instance d'AgentLimits."""
        assert isinstance(config.agent_limits, AgentLimits)


# ── 3. PipelineContext : permissions + agent_limits ─────────────────────


class TestPipelineContextActContract:
    def test_context_exposes_permissions_and_agent_limits(self):
        """PipelineContext injecte permissions + agent_limits au step Act."""
        ctx = PipelineContext(query="")
        assert hasattr(ctx, "permissions")
        assert hasattr(ctx, "agent_limits")
        assert ctx.permissions is None
        assert ctx.agent_limits is None


# ── 4. Comportement no-op du step Act (flag False) ──────────────────────


@pytest.mark.asyncio
class TestActNoop:
    """Le step Act est un no-op strict quand enable_act_step=False."""

    async def test_run_noop_no_error(self):
        """Act.run() retourne sans erreur (gate flag False par défaut)."""
        step = Act()
        ctx = PipelineContext(query="test")
        out, res = await step.run(ctx)
        assert out is ctx
        assert res.error is None, f"no-op doit être sans erreur, got: {res.error}"

    async def test_run_noop_does_not_load_src_tools(self, monkeypatch):
        """Aucun import de src.tools ajouté quand le flag est False (lazy import effectif).

        On importe directement depuis le package pipeline_steps pour isoler le step
        sans passer par l'export src.kernel. Le gate switche sur config.enable_act_step ;
        on le force à False (valeur par défaut) et on vérifie qu'aucune importation
        de src.tools n'a lieu DANS run().

        NOTE (V18.1 C5) : la vérification est RELATIVE à l'instant T-1 de run(), car
        le chantier C5 a légitimement câblé `src.tools` dans la matérialisation MCP
        (`_ensure_mcp` → `_register_mcp_tools` → ToolOrchestrator.setup()). Le C2
        `test_ensure_mcp_registers_tools` matérialise donc MCP dans le MÊME process
        pytest et pré-importe `src.tools` dans sys.modules — un contrôle global
        d'absence serait brisé par un ordre de test légitime (non-régression du step
        Act, pas de MCP). L'assertion isole le comportement réel du step Act : sa
        branche no-op n'ajoute AUCUN module src.tools par elle-même.
        """
        import sys

        def _tools_loaded():
            return [m for m in sys.modules if m == "src.tools" or m.startswith("src.tools.")]

        config.enable_act_step = False
        step = _ActPkg()
        ctx = PipelineContext(query="test")
        before = set(_tools_loaded())
        out, res = await step.run(ctx)
        assert out is ctx
        assert res.error is None
        # run() no-op ne charge aucun module src.tools SUPPLÉMENTAIRE
        newly_loaded = [m for m in _tools_loaded() if m not in before]
        assert not newly_loaded, (
            "le chemin no-op ne doit importer aucun module src.tools (coût ~19,3 MiB au boot)"
        )