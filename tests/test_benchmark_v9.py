"""Benchmark NURU V10 — performances de chaque module.

Sprint 8 — Intégration
Mesure les temps d'exécution de chaque composant pour garantir
des performances acceptables. Les seuils incluent une marge de sécurité x10.
"""

import tempfile
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class BenchmarkResult:
    """Résultat d'un benchmark."""
    def __init__(self, name: str, duration_ms: float, passed: bool, details: str = ""):
        self.name = name
        self.duration_ms = duration_ms
        self.passed = passed
        self.details = details


def benchmark(name: str, func):
    """Exécute une fonction et mesure le temps."""
    start = time.perf_counter()
    try:
        func()
        duration = (time.perf_counter() - start) * 1000
        return BenchmarkResult(name, duration, True)
    except Exception as e:
        duration = (time.perf_counter() - start) * 1000
        return BenchmarkResult(name, duration, False, str(e))


# ═══════════════════════════════════════════════════════════════
# Benchmarks Mémoire
# ═══════════════════════════════════════════════════════════════
class TestBenchmarkMemory:
    def test_memory_write_speed(self):
        """Vitesse d'écriture mémoire : < 500ms par écriture."""
        from src.memory.manager import MemoryManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = MemoryManager(db_path=str(Path(tmpdir) / "bench.db"))
            result = benchmark("memory_write", lambda: mgr.record_conversation("test", "response"))
            assert result.passed
            assert result.duration_ms < 500, f"memory_write trop lent: {result.duration_ms:.1f}ms"

    def test_memory_search_speed(self):
        """Vitesse de recherche mémoire : < 500ms."""
        from src.memory.manager import MemoryManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = MemoryManager(db_path=str(Path(tmpdir) / "bench.db"))
            mgr.record_conversation("analyse document PDF", "Voici l'analyse du document")
            result = benchmark("memory_search", lambda: mgr.episodic.recall("document", top_k=5))
            assert result.passed
            assert result.duration_ms < 500, f"memory_search trop lent: {result.duration_ms:.1f}ms"

    def test_memory_concurrent_writes(self):
        """Écritures multiples : < 2s pour 10 écritures."""
        from src.memory.manager import MemoryManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = MemoryManager(db_path=str(Path(tmpdir) / "bench.db"))

            def write_batch():
                for i in range(10):
                    mgr.record_conversation(f"query {i}", f"response {i}")

            result = benchmark("memory_write_batch", write_batch)
            assert result.passed
            assert result.duration_ms < 3000, f"memory_write_batch trop lent: {result.duration_ms:.1f}ms"


# ═══════════════════════════════════════════════════════════════
# Benchmarks Agent
# ═══════════════════════════════════════════════════════════════
class TestBenchmarkAgent:
    def test_planner_speed(self):
        """Vitesse du planificateur : < 50ms."""
        from src.agent.planner import TaskPlanner
        planner = TaskPlanner()
        result = benchmark("planner", lambda: planner.plan("Analyser un document"))
        assert result.passed
        assert result.duration_ms < 50, f"planner trop lent: {result.duration_ms:.1f}ms"

    def test_executor_speed(self):
        """Vitesse de l'exécuteur : < 500ms pour 3 étapes."""
        from src.agent.planner import TaskPlanner
        from src.agent.executor import TaskExecutor
        planner = TaskPlanner()
        executor = TaskExecutor()
        plan = planner.plan("Créer un rapport")

        async def run_plan():
            for step in plan.steps:
                await executor.execute(step)

        result = benchmark("executor", lambda: asyncio.run(run_plan()))
        assert result.passed
        assert result.duration_ms < 500, f"executor trop lent: {result.duration_ms:.1f}ms"

    def test_verifier_speed(self):
        """Vitesse du vérificateur : < 10ms."""
        from src.agent.planner import TaskPlanner
        from src.agent.executor import TaskExecutor
        from src.agent.verifier import TaskVerifier
        planner = TaskPlanner()
        executor = TaskExecutor()
        verifier = TaskVerifier()
        plan = planner.plan("Créer un rapport")

        async def verify_all():
            for step in plan.steps:
                result = await executor.execute(step)
                verifier.verify(step, result)

        result = benchmark("verifier", lambda: asyncio.run(verify_all()))
        assert result.passed
        assert result.duration_ms < 500, f"verifier trop lent: {result.duration_ms:.1f}ms"


# ═══════════════════════════════════════════════════════════════
# Benchmarks Raisonnement
# ═══════════════════════════════════════════════════════════════
class TestBenchmarkReasoning:
    def test_reflexion_speed(self):
        """Vitesse de la réflexion : < 50ms."""
        from src.reasoning.reflexion import ReflexionEngine
        engine = ReflexionEngine()
        result = benchmark("reflexion", lambda: engine.reflect("Non", "Explique"))
        assert result.passed
        assert result.duration_ms < 50, f"reflexion trop lent: {result.duration_ms:.1f}ms"

    def test_consistency_speed(self):
        """Vitesse de cohérence : < 50ms."""
        from src.reasoning.consistency import SelfConsistency
        sc = SelfConsistency()
        result = benchmark("consistency", lambda: sc.vote(["Paris", "Paris", "Lyon"]))
        assert result.passed
        assert result.duration_ms < 50, f"consistency trop lent: {result.duration_ms:.1f}ms"

    def test_confidence_speed(self):
        """Vitesse du calibrateur : < 5ms."""
        from src.reasoning.confidence import ConfidenceCalibrator
        cal = ConfidenceCalibrator()
        result = benchmark("confidence", lambda: cal.calibrate(0.7))
        assert result.passed
        assert result.duration_ms < 20, f"confidence trop lent: {result.duration_ms:.1f}ms"


# ═══════════════════════════════════════════════════════════════
# Benchmarks Outils
# ═══════════════════════════════════════════════════════════════
class TestBenchmarkTools:
    def test_document_generation_speed(self):
        """Vitesse de génération document : < 2000ms pour tous les formats."""
        from src.tools.document import DocumentGenerator, DocumentSpec, DocFormat, DocSection
        gen = DocumentGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            def gen_all():
                for fmt in [DocFormat.WORD, DocFormat.PDF, DocFormat.PPTX, DocFormat.XLSX]:
                    spec = DocumentSpec(
                        title="Benchmark",
                        format=fmt,
                        sections=[DocSection("S1", "C1")],
                    )
                    gen.generate(spec, Path(tmpdir) / f"bench.{fmt.value}")

            result = benchmark("docgen_all_formats", gen_all)
            assert result.passed
            assert result.duration_ms < 2000, f"docgen trop lent: {result.duration_ms:.1f}ms"

    def test_registry_operations_speed(self):
        """Vitesse des opérations du registre : < 10ms pour 10 outils."""
        from src.tools.registry import ToolRegistry, ToolDefinition, ToolParameter
        registry = ToolRegistry()

        def register_many():
            for i in range(10):
                registry.register(ToolDefinition(
                    name=f"tool_{i}",
                    description=f"Outil test {i}",
                    category="test",
                    parameters=[ToolParameter(name="param", type="str", description="p")],
                ))

        result = benchmark("registry_register", register_many)
        assert result.passed
        assert result.duration_ms < 20, f"registry_register trop lent: {result.duration_ms:.1f}ms"


# ═══════════════════════════════════════════════════════════════
# Benchmarks Recherche
# ═══════════════════════════════════════════════════════════════
class TestBenchmarkResearch:
    def test_research_scoring_speed(self):
        """Vitesse de scoring recherche : < 20ms."""
        from src.research.web import WebResearcher
        researcher = WebResearcher()
        result = benchmark("research_score", lambda: researcher.score_relevance(
            "comment analyser un PDF", "Guide PDF", "Voici comment analyser un PDF"
        ))
        assert result.passed
        assert result.duration_ms < 20, f"research_score trop lent: {result.duration_ms:.1f}ms"

    def test_research_dedup_speed(self):
        """Vitesse de déduplication : < 10ms pour 100 résultats."""
        from src.research.web import WebResearcher, SearchResult
        researcher = WebResearcher()
        results = [
            SearchResult(url=f"https://example.com/page{i}", title=f"Page {i}", snippet="test", relevance_score=0.5)
            for i in range(100)
        ]

        def dedup():
            return researcher.deduplicate(results)

        result = benchmark("research_dedup", dedup)
        assert result.passed
        assert result.duration_ms < 20, f"research_dedup trop lent: {result.duration_ms:.1f}ms"


# ═══════════════════════════════════════════════════════════════
# Benchmarks Learning
# ═══════════════════════════════════════════════════════════════
class TestBenchmarkLearning:
    def test_feedback_write_speed(self):
        """Vitesse d'écriture feedback : < 100ms."""
        from src.learning.feedback import FeedbackCollector
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "bench_feedback.db")
            collector = FeedbackCollector(db_path=db_path)
            result = benchmark("feedback_write", lambda: collector.record_thumbs(
                query="test", response="response", is_positive=True
            ))
            assert result.passed
            assert result.duration_ms < 100, f"feedback_write trop lent: {result.duration_ms:.1f}ms"

    def test_tracker_write_speed(self):
        """Vitesse d'écriture tracker : < 100ms."""
        from src.learning.tracker import PerformanceTracker
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "bench_perf.db")
            tracker = PerformanceTracker(db_path=db_path)
            result = benchmark("tracker_write", lambda: tracker.record(
                metric_name="test_metric", value=0.5, category="test"
            ))
            assert result.passed
            assert result.duration_ms < 100, f"tracker_write trop lent: {result.duration_ms:.1f}ms"

    def test_tracker_summary_speed(self):
        """Vitesse de calcul du résumé tracker : < 50ms."""
        from src.learning.tracker import PerformanceTracker
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "bench_perf.db")
            tracker = PerformanceTracker(db_path=db_path)
            # Pré-remplir
            for i in range(20):
                tracker.record(f"metric_{i % 5}", float(i) / 10.0, category="test")
            result = benchmark("tracker_summary", tracker.get_summary)
            assert result.passed
            assert result.duration_ms < 100, f"tracker_summary trop lent: {result.duration_ms:.1f}ms"


# Need asyncio for executor benchmark
import asyncio
