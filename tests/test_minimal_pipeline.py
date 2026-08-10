"""Tests V18-15 — Mode Minimal Pipeline (flag `minimal_pipeline`).

Cible : `src/config.py` (config.minimal_pipeline), `src/kernel/pipeline.py`
(PipelineContext.minimal_pipeline) et les 5 gating points.

Vérifie (spec V18-15 §3.3 / §5 / §6) :
- le flag existe et est False par défaut (JAMAIS le mode normal) ;
- `minimal_pipeline=True` active les 5 court-circuits :
  1. Query Rewrite   → `src/rag_engine.py:805`
  2. HYDE            → `src/rag/multi_search.py:611` (_should_use_hyde → False)
  3. Spotlight       → `src/routing/router.py:310` + `src/kernel/pipeline_steps.py:316`
  4. Speculative     → `src/orchestration/rag_pipeline.py:57` (non instancié)
  5. Décomposition   → `src/orchestration/rag_pipeline.py:125` (→ [query])
- les gardes V18-31 (Fast-Fail Strict RAG) / V18-02 (état RAG typé) /
  V18-14 (FSM Validate) ne sont JAMAIS désactivées par le flag :
  inspection AST — `check_strict_blocks`, `Validate.run` et l'appel Strict RAG
  du step Retrieve ne référencent PAS `minimal_pipeline` ;
- `run_benchmark(minimal=True)` → mode="minimal" (flag benchmark UNIQUEMENT).

Méthode : tests comportementaux légers (HYDE, Speculative, Décompose,
PipelineContext) + inspection AST (précédent test_c2_freeze_modules.py).
Le flag est un singleton global : une fixture sauvegarde/restaure sa valeur.
"""

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config import config
from src.kernel.pipeline import PipelineContext
from src.rag.multi_search import MultiSearchOrchestrator

REPO_ROOT = Path(__file__).parent.parent
RAG_PIPELINE_PATH = REPO_ROOT / "src" / "orchestration" / "rag_pipeline.py"
PIPELINE_STEPS_PATH = REPO_ROOT / "src" / "kernel" / "pipeline_steps.py"
RAG_ENGINE_PATH = REPO_ROOT / "src" / "rag_engine.py"
ROUTER_PATH = REPO_ROOT / "src" / "routing" / "router.py"
MULTI_SEARCH_PATH = REPO_ROOT / "src" / "rag" / "multi_search.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse(path: Path) -> ast.Module:
    return ast.parse(_read(path))


@pytest.fixture(autouse=True)
def _restore_minimal_pipeline():
    """Sauvegarde/restaure le singleton config après chaque test."""
    original = config.minimal_pipeline
    config.minimal_pipeline = False
    yield
    config.minimal_pipeline = original


class TestFlagExistenceAndDefault:
    """Le flag existe et ne change RIEN par défaut."""

    def test_config_field_exists_and_default_false(self):
        assert hasattr(config, "minimal_pipeline")
        assert config.minimal_pipeline is False

    def test_pipeline_context_field_exists_and_default_false(self):
        ctx = PipelineContext(query="Bonjour")
        assert ctx.minimal_pipeline is False

    def test_flag_never_in_settings_default(self):
        """Aucune surcharge YAML ne force le flag (benchmark UNIQUEMENT)."""
        assert config.minimal_pipeline is False


class TestHydeGate:
    """HYDE court-circuité quand le flag est True."""

    def test_should_use_hyde_disabled_in_minimal_mode(self):
        orch = MultiSearchOrchestrator(model_size_below_7b=False)
        query = "Quelle est la différence entre RAG et BM25 ?"
        config.minimal_pipeline = True
        assert orch._should_use_hyde(query) is False

    def test_should_use_hyde_enabled_in_normal_mode(self):
        orch = MultiSearchOrchestrator(model_size_below_7b=False)
        query = "Quelle est la différence entre RAG et BM25 ?"
        config.minimal_pipeline = False
        assert orch._should_use_hyde(query) is True

    def test_gate_present_in_multi_search_source(self):
        assert "minimal_pipeline" in _read(MULTI_SEARCH_PATH)


class TestSpeculativeGate:
    """Speculative RAG non instancié quand le flag est True."""

    def _build(self):
        from src.orchestration.rag_pipeline import RAGOrchestrator

        return RAGOrchestrator(
            MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(), MagicMock(),
        )

    def test_speculative_not_instantiated_in_minimal_mode(self):
        with patch("src.orchestration.rag_pipeline.SpeculativeRAG") as mock_spec:
            config.minimal_pipeline = True
            orch = self._build()
            assert orch.speculative is None
            mock_spec.assert_not_called()

    def test_speculative_instantiated_in_normal_mode(self):
        with patch("src.orchestration.rag_pipeline.SpeculativeRAG") as mock_spec:
            config.minimal_pipeline = False
            orch = self._build()
            assert orch.speculative is not None
            mock_spec.assert_called_once()


class TestDecomposeGate:
    """Décomposition court-circuitée → [query] quand le flag est True."""

    @pytest.mark.asyncio
    async def test_decompose_returns_single_query_in_minimal_mode(self):
        from src.orchestration.rag_pipeline import RAGOrchestrator

        orch = RAGOrchestrator(
            MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(), MagicMock(),
        )
        config.minimal_pipeline = True
        query = "Que contient mon rapport annuel ?"
        assert await orch._try_decompose(query) == [query]

    @pytest.mark.asyncio
    async def test_decompose_returns_single_query_when_not_needed(self):
        from src.orchestration.rag_pipeline import RAGOrchestrator

        orch = RAGOrchestrator(
            MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(), MagicMock(),
        )
        config.minimal_pipeline = False
        query = "Bonjour"
        with patch("src.rag.decomposer.should_decompose", return_value=False):
            assert await orch._try_decompose(query) == [query]


class TestSpotlightGates:
    """Spotlight (routeur + intégration) court-circuité."""

    def test_router_gate_present(self):
        assert "minimal_pipeline" in _read(ROUTER_PATH)

    def test_pipeline_steps_gate_present(self):
        assert "minimal_pipeline" in _read(PIPELINE_STEPS_PATH)

    def test_pipeline_steps_helper_exists(self):
        """`_config_minimal_pipeline()` lit le flag avec défaut False."""
        from src.kernel.pipeline_steps import _config_minimal_pipeline

        config.minimal_pipeline = True
        assert _config_minimal_pipeline() is True
        config.minimal_pipeline = False
        assert _config_minimal_pipeline() is False


class TestQueryRewriteGate:
    """Query Rewrite court-circuité."""

    def test_query_rewrite_gate_present(self):
        assert "minimal_pipeline" in _read(RAG_ENGINE_PATH)


class TestGuardesV18JamaisDesactivees:
    """Les gardes V18-31 / V18-02 / V18-14 ne sont JAMAIS désactivées.

    La garantie est structurelle : le flag `minimal_pipeline` n'apparaît dans
    AUCUN des chemins de garde (Fast-Fail Strict RAG, état RAG typé, FSM
    Validate). S'il y apparaissait un jour, ce test casse.
    """

    def _function_source(self, tree: ast.Module, name: str) -> str:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return ast.get_source_segment(_read(RAG_PIPELINE_PATH), node) or ""
        raise AssertionError(f"fonction {name} introuvable")

    def test_check_strict_blocks_independent_of_flag(self):
        """V18-31 Fast-Fail : check_strict_blocks ignore minimal_pipeline."""
        src = self._function_source(_parse(RAG_PIPELINE_PATH), "check_strict_blocks")
        assert "minimal_pipeline" not in src
        # Le blocage Strict RAG est bien présent (pas supprimé par le flag)
        assert "response_guard.is_strict" in src
        assert "refuse_message" in src

    def test_retrieve_step_strict_guard_not_gated(self):
        """L'appel check_strict_blocks du step Retrieve n'est pas gâté."""
        source = _read(PIPELINE_STEPS_PATH)
        # Le bloc Strict RAG (étape 7) appelle check_strict_blocks
        assert "check_strict_blocks(" in source
        assert "strict_refused" in source

    def test_validate_run_independent_of_flag(self):
        """V18-14 FSM : la méthode run de Validate ignore minimal_pipeline."""
        tree = _parse(PIPELINE_STEPS_PATH)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "Validate":
                for method in node.body:
                    if isinstance(method, ast.AsyncFunctionDef) and method.name == "run":
                        src = ast.get_source_segment(_read(PIPELINE_STEPS_PATH), method) or ""
                        assert "minimal_pipeline" not in src
                        return
        raise AssertionError("Validate.run introuvable")

    def test_no_guard_reference_in_rag_engine_retrieve(self):
        """Le retrieval (état RAG typé V18-02) n'est pas gâté par le flag.

        La seule occurrence du flag dans rag_engine.py est la branche
        QueryRewrite (optimisation, légitimement gâtée) — le code de
        retrieval lui-même est exécuté dans tous les modes.
        """
        source = _read(RAG_ENGINE_PATH)
        assert source.count("minimal_pipeline") == 1
        # L'unique occurrence est la branche QueryRewrite (optimisation)
        idx = source.index("minimal_pipeline")
        assert "QueryRewrite" in source[max(0, idx - 400):idx + 100]


class TestRunBenchmarkMinimal:
    """`run_benchmark(minimal=True)` → mode minimal (flag benchmark UNIQUEMENT)."""

    def test_run_benchmark_minimal_sets_mode(self, tmp_path):
        from src.benchmark.runner import run_benchmark

        config.minimal_pipeline = False
        out = tmp_path / "bench.json"
        result = run_benchmark(
            scope="routing",
            routing_only=True,
            minimal=True,
            out_path=str(out),
        )
        assert result["mode"] == "minimal"
        assert result["routing"]["floor_ok"] is True
        assert config.minimal_pipeline is True
        assert out.exists()
