"""Tests pour le Kernel NURU V16 — registre de services + pipeline steps.

Cible : src/kernel/kernel.py, pipeline.py, pipeline_steps.py, registry.py
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

# Exporté depuis __init__.py
from src.kernel import (
    NuruKernel, ServiceRegistry, PipelineEngine,
    Route, Retrieve, Generate, Validate, Respond,
    ReceiveQuestion, BuildContext,
)
from src.kernel.pipeline import PipelineContext


# ═══════════════════════════════════════════════════════════════════
# 1. ServiceRegistry — unitaire
# ═══════════════════════════════════════════════════════════════════


class TestServiceRegistry:
    """Enregistrement et récupération de services."""

    def test_register_and_get(self):
        """Un service enregistré est récupérable."""
        registry = ServiceRegistry()
        service = MagicMock()
        registry.register("test_service", service)
        assert registry.get("test_service") is service

    def test_get_missing_raises(self):
        """Un service non enregistré lève KeyError."""
        registry = ServiceRegistry()
        with pytest.raises(KeyError):
            registry.get("inexistant")

    def test_get_or_none(self):
        """get_or_none retourne None pour un service manquant."""
        registry = ServiceRegistry()
        assert registry.get_or_none("inexistant") is None

    def test_has_service(self):
        """has retourne True pour un service enregistré."""
        registry = ServiceRegistry()
        assert not registry.has("test")
        registry.register("test", MagicMock())
        assert registry.has("test")

    def test_has_factory(self):
        """has retourne True aussi pour une factory enregistrée."""
        registry = ServiceRegistry()
        registry.register_factory("lazy", MagicMock)
        assert registry.has("lazy")

    def test_register_duplicate_raises(self):
        """Enregistrer deux fois le même nom lève ValueError."""
        registry = ServiceRegistry()
        registry.register("x", MagicMock())
        with pytest.raises(ValueError):
            registry.register("x", MagicMock())

    def test_register_replace(self):
        """Enregistrer avec replace=True remplace l'existant."""
        registry = ServiceRegistry()
        s1, s2 = MagicMock(), MagicMock()
        registry.register("x", s1)
        registry.register("x", s2, replace=True)
        assert registry.get("x") is s2

    def test_unregister(self):
        """unregister supprime le service."""
        registry = ServiceRegistry()
        registry.register("x", MagicMock())
        registry.unregister("x")
        assert not registry.has("x")

    def test_start_stop_service(self):
        """start/stop appellent les méthodes du service."""
        registry = ServiceRegistry()
        svc = MagicMock()
        registry.register("s", svc)
        registry.start("s")
        svc.start.assert_called_once()
        registry.stop("s")
        svc.stop.assert_called_once()

    def test_start_all(self):
        """start_all démarre tous les services."""
        registry = ServiceRegistry()
        s1, s2 = MagicMock(), MagicMock()
        registry.register("a", s1)
        registry.register("b", s2)
        registry.start_all()
        s1.start.assert_called_once()
        s2.start.assert_called_once()

    def test_factory_lazy_instantiation(self):
        """Une factory est appelée au premier get()."""
        registry = ServiceRegistry()
        factory = MagicMock(return_value=MagicMock())
        registry.register_factory("lazy", factory)
        svc = registry.get("lazy")
        factory.assert_called_once()
        assert registry.get("lazy") is svc  # même instance, mise en cache

    def test_names_property(self):
        """names retourne la liste des services."""
        registry = ServiceRegistry()
        registry.register("a", MagicMock())
        registry.register_factory("b", MagicMock)
        names = registry.names
        assert "a" in names
        assert any("b" in n for n in names)


# ═══════════════════════════════════════════════════════════════════
# 2. NuruKernel — proxy singleton
# ═══════════════════════════════════════════════════════════════════


class TestNuruKernel:
    """NuruKernel comme façade singleton."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Nettoie le singleton entre les tests."""
        NuruKernel._instance = None
        NuruKernel._initialized = False
        yield

    def test_singleton(self):
        """Deux instances sont le même objet."""
        k1 = NuruKernel()
        k2 = NuruKernel()
        assert k1 is k2

    def test_services_property(self):
        """kernel.services donne accès au ServiceRegistry."""
        kernel = NuruKernel()
        assert isinstance(kernel.services, ServiceRegistry)

    def test_typed_accessors_return_none_by_default(self):
        """Les accesseurs typés retournent None sans service."""
        kernel = NuruKernel()
        assert kernel.router is None
        assert kernel.rag_engine is None
        assert kernel.local_llm is None
        assert kernel.cloud_llm is None
        assert kernel.memory is None
        assert kernel.orchestrator is None

    def test_typed_accessors_after_register(self):
        """Les accesseurs typés retournent le service après enregistrement."""
        kernel = NuruKernel()
        svc = MagicMock()
        kernel.services.register("router", svc)
        assert kernel.router is svc


# ═══════════════════════════════════════════════════════════════════
# 3. PipelineEngine — Construction et exécution
# ═══════════════════════════════════════════════════════════════════


class TestPipelineConstruction:
    """Construction et configuration du PipelineEngine."""

    def test_create_pipeline(self):
        """PipelineEngine se crée sans argument."""
        engine = PipelineEngine()
        assert engine is not None

    def test_add_step(self):
        """add_step ajoute un step à la séquence."""
        engine = PipelineEngine()
        step = Route()
        engine.add_step(step)
        assert len(engine._steps) == 1

    def test_set_steps(self):
        """set_steps remplace tous les steps."""
        engine = PipelineEngine()
        steps = [Route(), Generate(), Respond()]
        engine.set_steps(steps)
        assert len(engine._steps) == 3

    def test_pipeline_context_required_query(self):
        """PipelineContext nécessite query."""
        with pytest.raises(TypeError):
            PipelineContext()
        ctx = PipelineContext(query="hello")
        assert ctx.query == "hello"

    def test_pipeline_context_defaults(self):
        """PipelineContext a des valeurs par défaut correctes."""
        ctx = PipelineContext(query="")
        assert ctx.intent == "GENERAL"
        assert ctx.response == ""
        assert ctx.rag_context == ""
        assert ctx.web_context == ""


class TestPipelineDataFlow:
    """Vérifie que le contexte circule entre les steps via run()."""

    @pytest.mark.asyncio
    async def test_pipeline_run_returns_context(self):
        """run(query) retourne un PipelineContext."""
        engine = PipelineEngine()
        ctx = await engine.run("hello")
        assert isinstance(ctx, PipelineContext)
        assert ctx.query == "hello"

    @pytest.mark.asyncio
    async def test_empty_pipeline_steps(self):
        """PipelineEngine sans steps ne plante pas."""
        engine = PipelineEngine()
        ctx = await engine.run("test")
        assert ctx.response == ""


# ═══════════════════════════════════════════════════════════════════
# 4. Pipeline Steps — Noms des classes
# ═══════════════════════════════════════════════════════════════════


class TestPipelineStepNames:
    """Chaque step a le bon nom de classe."""

    def test_route_name(self):
        step = Route()
        assert step.name == "Route"

    def test_generate_name(self):
        step = Generate()
        assert step.name == "Generate"

    def test_retrieve_name(self):
        step = Retrieve()
        assert step.name == "Retrieve"

    def test_respond_name(self):
        step = Respond()
        assert step.name == "Respond"

    def test_validate_name(self):
        step = Validate()
        assert step.name == "Validate"

    def test_receive_question_name(self):
        step = ReceiveQuestion()
        assert step.name == "ReceiveQuestion"

    def test_build_context_name(self):
        step = BuildContext()
        assert step.name == "BuildContext"
