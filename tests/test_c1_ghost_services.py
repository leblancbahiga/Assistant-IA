"""Tests C1 V18.1 — débranchement des services fantômes (archon_refiner, trace_collector).

Cible : src/kernel/pipeline_steps.py (step Validate)

Vérifie que le step Validate s'exécute sans exception quand les services
archon_refiner / trace_collector sont absents du kernel, qu'un log WARNING
explicite est émis (observabilité AGENTS.md §14-15), et que le comportement
de ctx.response est inchangé.
"""

import logging

import pytest

from src.kernel import NuruKernel, Validate
from src.kernel.pipeline import PipelineContext

VALIDATE_LOGGER = "src.kernel.pipeline_steps"

ARCHON_WARNING = "ArchonRefiner désactivé (service non enregistré, API incompatible) — V18.1"
TRACE_WARNING = "TraceCollector désactivé (service non enregistré, appel async sans await) — V18.1"


@pytest.fixture(autouse=True)
def clean_kernel_and_flags():
    """Kernel vide (aucun service enregistré) + flags de throttle reset.

    Le throttle étant un attribut de classe, chaque test doit le réinitialiser
    pour pouvoir observer les WARNING.
    """
    NuruKernel._instance = None
    NuruKernel._initialized = False
    Validate._archon_refiner_warned = False
    Validate._trace_collector_warned = False
    yield
    NuruKernel._instance = None
    NuruKernel._initialized = False


def _make_ctx(response: str = "Réponse de test") -> PipelineContext:
    ctx = PipelineContext(query="Quelle est la mission de l'IITA ?")
    ctx.response = response
    ctx.intent = "RAG"
    ctx.model_used = "phi-4-mini"
    ctx.tokens_generated = 42
    ctx.tokens_prompt = 128
    return ctx


class TestValidateGhostServicesDebranches:
    """Le step Validate vit sans les services fantômes."""

    @pytest.mark.asyncio
    async def test_validate_runs_without_ghost_services(self, caplog):
        """Aucun service archon_refiner/trace_collector → pas d'exception, WARNING émis."""
        step = Validate()
        ctx = _make_ctx()

        with caplog.at_level(logging.WARNING, logger=VALIDATE_LOGGER):
            out_ctx, result = await step.run(ctx)

        # Pas d'exception : le contexte et le résultat sont retournés.
        assert result is not None
        assert out_ctx is ctx

        # Les deux WARNING de désactivation sont émis.
        warnings = [r.getMessage() for r in caplog.records]
        assert any(ARCHON_WARNING in w for w in warnings), warnings
        assert any(TRACE_WARNING in w for w in warnings), warnings

    @pytest.mark.asyncio
    async def test_validate_response_unchanged(self, caplog):
        """ctx.response n'est ni modifié ni écrasé par les services fantômes."""
        step = Validate()
        ctx = _make_ctx(response="Réponse RAG générée par Phi-4-mini")

        with caplog.at_level(logging.WARNING, logger=VALIDATE_LOGGER):
            out_ctx, _ = await step.run(ctx)

        assert out_ctx.response == "Réponse RAG générée par Phi-4-mini"

    @pytest.mark.asyncio
    async def test_warning_emitted_once_per_process(self, caplog):
        """Le WARNING est throttlé : une seule émission par process, pas par requête."""
        step = Validate()
        ctx1 = _make_ctx(response="Première réponse")
        ctx2 = _make_ctx(response="Deuxième réponse")

        with caplog.at_level(logging.WARNING, logger=VALIDATE_LOGGER):
            await step.run(ctx1)
            await step.run(ctx2)

        archon_count = sum(1 for r in caplog.records if ARCHON_WARNING in r.getMessage())
        trace_count = sum(1 for r in caplog.records if TRACE_WARNING in r.getMessage())
        assert archon_count == 1, f"attendu 1 WARNING archon, obtenu {archon_count}"
        assert trace_count == 1, f"attendu 1 WARNING trace, obtenu {trace_count}"

    @pytest.mark.asyncio
    async def test_no_keyerror_from_get_service(self, caplog):
        """Aucun _get_service('archon_refiner'/'trace_collector') ne lève KeyError."""
        import src.kernel.pipeline_steps as steps_module

        source = inspect_source(steps_module)
        assert '_get_service("archon_refiner")' not in source
        assert '_get_service("trace_collector")' not in source


def inspect_source(module) -> str:
    """Retourne la source du module sans import supplémentaire."""
    import inspect

    return inspect.getsource(module)
