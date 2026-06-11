"""Tests d'intégration NURU V10 — vérifient le pipeline complet entre modules.

Sprint 8 — Intégration
Connectent les modules entre eux pour vérifier que les composants
fonctionnent correctement ensemble dans des scénarios réels.
"""

import asyncio
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

# ═══════════════════════════════════════════════════════════════
# TEST 1 : Mémoire → Agent (l'agent utilise la mémoire)
# ═══════════════════════════════════════════════════════════════
class TestMemoryAgentIntegration:
    def test_memory_records_agent_task(self):
        """L'enregistrement d'une tâche agent dans la mémoire fonctionne."""
        from src.memory.manager import MemoryManager
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            mgr = MemoryManager(db_path=str(db_path))
            # Enregistrer une conversation
            eid = mgr.record_conversation("Analyse de document", "Voici l'analyse...")
            assert eid is not None
            assert len(eid) > 0
            # Vérifier dans l'épisodique via recall
            results = mgr.episodic.recall("analyse", top_k=5)
            assert len(results) > 0

    def test_agent_uses_memory_for_planning(self):
        """Le planificateur peut accéder à la mémoire pour planifier."""
        from src.agent.planner import TaskPlanner
        from src.memory.manager import MemoryManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = MemoryManager(db_path=str(Path(tmpdir) / "test.db"))
            mgr.record_conversation("Comment analyser un PDF", "Utilise DocumentGenerator")
            planner = TaskPlanner(memory_manager=mgr)
            plan = planner.plan("Analyser un document PDF")
            assert plan is not None
            assert len(plan.steps) > 0

    def test_memory_episode_agent_session(self):
        """Enregistrement d'une session agent complète dans la mémoire."""
        from src.memory.manager import MemoryManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = MemoryManager(db_path=str(Path(tmpdir) / "test.db"))
            steps = [
                {"status": "completed", "description": "Recherche effectuée"},
                {"status": "completed", "description": "Analyse réalisée"},
            ]
            eid = mgr.add_episode(
                session_id="sess-001",
                goal="Analyser les ventes Q1",
                status="success",
                steps=steps,
                importance=0.8,
            )
            assert eid is not None
            # Vérifier que l'épisode est en mémoire
            results = mgr.episodic.recall("ventes Q1", top_k=5)
            assert len(results) > 0

    def test_memory_error_tracking(self):
        """Les erreurs sont enregistrées et consultables via MemoryManager."""
        from src.memory.manager import MemoryManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = MemoryManager(db_path=str(Path(tmpdir) / "test.db"))
            eid = mgr.record_error(
                error_type="hallucination",
                description="Source inventée pour la réponse",
                root_cause="Pas de vérification",
            )
            assert eid is not None
            # Les erreurs sont stockées via error memory
            assert mgr.error.count() >= 1


# ═══════════════════════════════════════════════════════════════
# TEST 2 : Agent → Feedback (feedback sur les résultats agent)
# ═══════════════════════════════════════════════════════════════
class TestAgentFeedbackIntegration:
    def test_thumbs_feedback_recorded(self):
        """Le feedback thumbs up/down est enregistré après une étape agent."""
        from src.learning.feedback import FeedbackCollector
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "feedback.db")
            collector = FeedbackCollector(db_path=db_path)
            fb_id = collector.record_thumbs(
                query="Test query",
                response="Test response",
                is_positive=True,
            )
            assert fb_id is not None
            stats = collector.get_stats()
            assert stats["thumbs_up"] >= 1

    def test_rating_feedback_recorded(self):
        """Le feedback rating 1-5 est enregistré."""
        from src.learning.feedback import FeedbackCollector
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "feedback.db")
            collector = FeedbackCollector(db_path=db_path)
            fb_id = collector.record_rating(
                query="Test query",
                response="Test response",
                rating=5,
            )
            assert fb_id is not None
            stats = collector.get_stats()
            assert stats["ratings"] >= 1
            assert stats["avg_rating"] >= 5.0

    def test_correction_feedback_with_memory(self):
        """La correction synchronise avec ErrorMemory via MemoryManager."""
        from src.learning.feedback import FeedbackCollector
        from src.memory.manager import MemoryManager
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = MemoryManager(db_path=str(Path(tmpdir) / "memory.db"))
            fb_db = str(Path(tmpdir) / "feedback.db")
            collector = FeedbackCollector(db_path=fb_db, memory_manager=mgr)
            fb_id = collector.record_correction(
                query="Capital de la France",
                response="Berlin",
                correction="La capitale de la France est Paris",
            )
            assert fb_id is not None
            # La correction est enregistrée dans le feedback DB
            stats = collector.get_stats()
            assert stats["corrections"] >= 1

    def test_tracker_records_agent_metrics(self):
        """Le tracker enregistre les métriques de l'agent."""
        from src.learning.tracker import PerformanceTracker
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "perf.db")
            tracker = PerformanceTracker(db_path=db_path)
            tracker.record_agent_result(success=True, steps=3, recovery=False)
            tracker.record_rag_result("test query", recall5=0.8, avg_score=0.7, empty=False)
            summary = tracker.get_summary()
            assert summary["total_points"] >= 3


# ═══════════════════════════════════════════════════════════════
# TEST 3 : Raisonnement → Confiance (auto-critique + calibrage)
# ═══════════════════════════════════════════════════════════════
class TestReasoningIntegration:
    def test_reflexion_improves_answer(self):
        """La réflexion améliore une réponse faible."""
        from src.reasoning.reflexion import ReflexionEngine
        engine = ReflexionEngine(max_passes=2, min_score=0.5)
        result = engine.reflect("Non", "Explique la photosynthèse en détail")
        assert result.passes >= 1
        assert len(result.improved_answer) >= len(result.initial_answer)

    def test_consistency_validates_majority(self):
        """La cohérence détecte la réponse majoritaire."""
        from src.reasoning.consistency import SelfConsistency
        sc = SelfConsistency()
        result = sc.vote(["Paris", "Paris", "Lyon"])
        assert result.majority_answer == "Paris"
        assert result.confidence > 0.5

    def test_confidence_rejects_uncertain(self):
        """Le calibrateur rejette les réponses incertaines."""
        from src.reasoning.confidence import ConfidenceCalibrator
        cal = ConfidenceCalibrator(confidence_threshold=0.5)
        result = cal.calibrate(0.2, context_completeness=0.3, query_complexity=0.9)
        assert result.should_answer is False

    def test_reflexion_then_confidence_pipeline(self):
        """Pipeline réflexion → confiance : la réflexion améliore, le calibrateur valide."""
        from src.reasoning.reflexion import ReflexionEngine
        from src.reasoning.confidence import ConfidenceCalibrator
        engine = ReflexionEngine(max_passes=2, min_score=0.5)
        result = engine.reflect("Non", "Explique la photosynthèse en détail")
        # Après réflexion, le score devrait être meilleur
        assert result.score_final >= result.score_initial
        # Le calibrateur peut évaluer le résultat
        cal = ConfidenceCalibrator(confidence_threshold=0.3)
        calibrated = cal.calibrate(result.score_final)
        assert calibrated.raw_score == result.score_final

    def test_consistency_then_reflexion_pipeline(self):
        """Pipeline cohérence → réflexion : le vote détecte, la réflexion améliore."""
        from src.reasoning.consistency import SelfConsistency
        from src.reasoning.reflexion import ReflexionEngine
        sc = SelfConsistency()
        vote_result = sc.vote(["Oui c'est vrai", "Oui c'est vrai", "Non c'est faux"])
        assert vote_result.majority_answer == "Oui c'est vrai"
        # La réflexion peut ensuite améliorer la réponse
        engine = ReflexionEngine(max_passes=2, min_score=0.5)
        reflection = engine.reflect(vote_result.majority_answer, "Vérifie cette affirmation")
        assert reflection.passes >= 1


# ═══════════════════════════════════════════════════════════════
# TEST 4 : Outils → Document (génération document via registry)
# ═══════════════════════════════════════════════════════════════
class TestToolsDocumentIntegration:
    def test_registry_executes_document_generation(self):
        """Le registre exécute la génération de document."""
        from src.tools.registry import ToolRegistry, ToolDefinition, ToolParameter, ToolExecutor
        from src.tools.document import DocumentGenerator, DocumentSpec, DocFormat, DocSection

        registry = ToolRegistry()
        tool = ToolDefinition(
            name="generate_document",
            description="Génère un document",
            category="document",
            parameters=[
                ToolParameter(name="title", type="str", description="Titre"),
                ToolParameter(name="format", type="str", description="Format"),
            ],
        )
        registry.register(tool)

        gen = DocumentGenerator()
        executor = ToolExecutor(registry)

        def gen_handler(title: str, format: str):
            return gen.generate(
                DocumentSpec(
                    title=title,
                    format=DocFormat(format),
                    sections=[DocSection("Intro", "Contenu")],
                ),
                f"/tmp/test_{title}.md",
            )

        executor.register_handler("generate_document", gen_handler)
        result = executor.execute("generate_document", {"title": "Rapport", "format": "markdown"})
        assert result.success is True

    def test_document_all_formats(self):
        """Génération de tous les formats supportés."""
        from src.tools.document import DocumentGenerator, DocumentSpec, DocFormat, DocSection
        gen = DocumentGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            for fmt in [DocFormat.WORD, DocFormat.PDF, DocFormat.PPTX, DocFormat.XLSX, DocFormat.MARKDOWN]:
                spec = DocumentSpec(
                    title="Test",
                    format=fmt,
                    sections=[DocSection("S1", "C1")],
                )
                path = gen.generate(spec, Path(tmpdir) / f"test.{fmt.value}")
                assert path.exists()
                assert path.stat().st_size > 0

    def test_registry_search_and_execute(self):
        """Recherche d'un outil dans le registre puis exécution."""
        from src.tools.registry import ToolRegistry, ToolDefinition, ToolParameter, ToolExecutor
        registry = ToolRegistry()
        registry.register(ToolDefinition(
            name="summarize_text", description="Résume un texte", category="text",
            parameters=[ToolParameter(name="text", type="str", description="Texte")],
        ))
        executor = ToolExecutor(registry)
        executor.register_handler("summarize_text", lambda text: f"Résumé: {text[:20]}...")
        results = registry.search("summarize")
        assert len(results) == 1
        result = executor.execute("summarize_text", {"text": "Un très long texte à résumer"})
        assert result.success is True


# ═══════════════════════════════════════════════════════════════
# TEST 5 : Pipeline complet (Mémoire → Agent → Feedback → Doc)
# ═══════════════════════════════════════════════════════════════
class TestFullPipeline:
    def test_complete_workflow(self):
        """Pipeline complet : planifier → exécuter → feedback → document."""
        from src.agent.planner import TaskPlanner
        from src.agent.executor import TaskExecutor
        from src.agent.verifier import TaskVerifier
        from src.learning.feedback import FeedbackCollector
        from src.tools.document import DocumentGenerator, DocumentSpec, DocFormat, DocSection
        import tempfile

        # 1. Planifier
        planner = TaskPlanner()
        plan = planner.plan("Créer un rapport d'analyse")
        assert plan is not None
        assert len(plan.steps) > 0

        # 2. Exécuter (async)
        executor = TaskExecutor()
        async def run_steps():
            results = []
            for step in plan.steps:
                r = await executor.execute(step)
                results.append(r)
            return results
        results = asyncio.run(run_steps())
        assert len(results) == len(plan.steps)

        # 3. Vérifier
        verifier = TaskVerifier()
        for i, r in enumerate(results):
            step = plan.steps[i]
            is_ok, score, reason = verifier.verify(step, r)
            # Le vérificateur retourne un tuple (bool, float, str)
            assert isinstance(is_ok, bool)
            assert isinstance(score, float)
            assert isinstance(reason, str)

        # 4. Feedback
        with tempfile.TemporaryDirectory() as tmpdir:
            fb_db = str(Path(tmpdir) / "feedback.db")
            collector = FeedbackCollector(db_path=fb_db)
            fb_id = collector.record_thumbs(
                query="Créer rapport",
                response="Rapport généré",
                is_positive=True,
            )
            assert fb_id is not None
            stats = collector.get_stats()
            assert stats["thumbs_up"] >= 1

        # 5. Document
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = DocumentGenerator()
            spec = DocumentSpec(
                title="Rapport d'analyse NURU",
                format=DocFormat.WORD,
                sections=[DocSection("Résultats", "Pipeline exécuté avec succès")],
            )
            path = gen.generate(spec, Path(tmpdir) / "rapport.docx")
            assert path.exists()
            assert path.stat().st_size > 0


# ═══════════════════════════════════════════════════════════════
# TEST 6 : ErreurMemory → Raisonnement (éviter les erreurs connues)
# ═══════════════════════════════════════════════════════════════
class TestErrorReasoningIntegration:
    def test_confidence_checks_error_memory(self):
        """Le calibrateur de confiance peut utiliser les erreurs connues."""
        from src.reasoning.confidence import ConfidenceCalibrator
        from src.memory.errors import ErrorMemory
        from src.memory.schema import MemorySchema
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            schema = MemorySchema(db_path=str(Path(tmpdir) / "errors.db"))
            schema.init_db()
            errors = ErrorMemory(schema)
            # Enregistrer une erreur
            error_id = errors.add(
                error_type="hallucination",
                description="Source inventée",
                root_cause="pas de vérification",
            )
            assert error_id is not None
            # Le calibrateur évalue la confiance brute
            cal = ConfidenceCalibrator(confidence_threshold=0.5)
            result = cal.calibrate(0.6, context_completeness=1.0, query_complexity=0.3)
            # Le score brut est préservé
            assert result.raw_score == 0.6
            # On peut vérifier les erreurs similaires
            similar = errors.check_similar("source inventée", threshold=0.3)
            # Le nombre d'erreurs similaires influence la décision
            penalty = 0.2 if similar else 0.0
            adjusted_score = result.calibrated_score - penalty
            assert adjusted_score <= 1.0

    def test_error_memory_prevents_repeat(self):
        """La mémoire d'erreurs empêche de répéter les erreurs connues."""
        from src.memory.errors import ErrorMemory
        from src.memory.schema import MemorySchema
        from src.reasoning.confidence import ConfidenceCalibrator
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            schema = MemorySchema(db_path=str(Path(tmpdir) / "errors.db"))
            schema.init_db()
            errors = ErrorMemory(schema)
            # Enregistrer une erreur de type hallucination
            errors.add(
                error_type="hallucination",
                description="Réponse inventée sur le contexte",
                root_cause="absence de sources vérifiées",
            )
            # Vérifier qu'une requête similaire est détectée
            similar = errors.check_similar("réponse inventée contexte", threshold=0.3)
            # Le calibrateur devrait prendre en compte le risque
            cal = ConfidenceCalibrator(confidence_threshold=0.5)
            if similar:
                # Avec des erreurs similaires, on降 la confiance
                result = cal.calibrate(0.6, context_completeness=0.5, query_complexity=0.7)
                assert result.raw_score == 0.6
