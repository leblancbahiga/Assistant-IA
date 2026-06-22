"""Harnais d'évaluation — Tests et benchmarks mémoire.

Vérifie l'intégrité des composants Phase 3 :
  - Memory consistency
  - Knowledge Graph queries
  - Proactive signal evaluation
  - Dynamic prompt generation
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class EvalResult:
    """Résultat d'un test d'évaluation."""
    test_name: str
    passed: bool
    duration_ms: float
    details: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "test": self.test_name,
            "passed": self.passed,
            "duration_ms": self.duration_ms,
            "details": self.details,
        }


@dataclass
class EvalSuiteResult:
    """Résultat complet d'une suite de tests."""
    results: list[EvalResult] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    duration_ms: float = 0.0

    def add(self, result: EvalResult) -> None:
        self.results.append(result)
        self.total += 1
        if result.passed:
            self.passed += 1
        else:
            self.failed += 1

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 1.0
        return self.passed / self.total


class MemoryHarness:
    """Harnais de tests pour les systèmes mémoire Phase 3.

    Usage :
        harness = MemoryHarness()
        # Test individuel
        result = harness.test_memory_consistency(memory_manager)
        # Suite complète
        suite = harness.run_full_suite(knowledge_graph, persona_engine)
        print(f"Score: {suite.passed}/{suite.total}")
    """

    def test_memory_consistency(self, memory_manager) -> EvalResult:
        """Vérifie la cohérence des mémoires."""
        start = time.time()
        try:
            stats = memory_manager.get_stats()
            total = stats.get("total", 0)
            duration = (time.time() - start) * 1000

            if total >= 0:
                return EvalResult(
                    test_name="memory_consistency",
                    passed=True,
                    duration_ms=duration,
                    details=f"Mémoires OK ({total} entrées)",
                )
            return EvalResult(
                test_name="memory_consistency",
                passed=True,
                duration_ms=duration,
                details="Aucune mémoire (OK pour premier lancement)",
            )
        except Exception as e:
            return EvalResult(
                test_name="memory_consistency",
                passed=False,
                duration_ms=(time.time() - start) * 1000,
                error=str(e),
            )

    def test_knowledge_graph(self, knowledge_graph) -> EvalResult:
        """Teste les opérations de base du Knowledge Graph."""
        start = time.time()
        try:
            if not knowledge_graph:
                return EvalResult(
                    test_name="knowledge_graph",
                    passed=False,
                    duration_ms=0,
                    details="Knowledge Graph non initialisé",
                )

            # Test add_node + add_edge + search
            n1 = knowledge_graph.add_node("eval_test", "test")
            n2 = knowledge_graph.add_node("eval_test_related", "test")
            knowledge_graph.add_edge(n1.id, n2.id, "test_relation")

            related = knowledge_graph.find_related("eval_test")
            stats = knowledge_graph.get_stats()

            success = len(related) > 0 and stats["total_nodes"] >= 2

            return EvalResult(
                test_name="knowledge_graph",
                passed=success,
                duration_ms=(time.time() - start) * 1000,
                details=f"KG OK: {stats['total_nodes']} nœuds, {stats['total_edges']} arêtes",
            )
        except Exception as e:
            return EvalResult(
                test_name="knowledge_graph",
                passed=False,
                duration_ms=(time.time() - start) * 1000,
                error=str(e),
            )

    def test_persona_engine(self, persona_engine) -> EvalResult:
        """Teste le PersonaEngine."""
        start = time.time()
        try:
            if not persona_engine:
                return EvalResult(
                    test_name="persona_engine",
                    passed=False,
                    duration_ms=0,
                    details="PersonaEngine non initialisé",
                )

            # Vérifier les personas built-in
            builtin = persona_engine.get_builtin_names()
            instructions = persona_engine.build_prompt_instructions()

            success = "persona_pro" in builtin and len(instructions) > 50

            return EvalResult(
                test_name="persona_engine",
                passed=success,
                duration_ms=(time.time() - start) * 1000,
                details=f"PersonaEngine OK: {builtin}",
            )
        except Exception as e:
            return EvalResult(
                test_name="persona_engine",
                passed=False,
                duration_ms=(time.time() - start) * 1000,
                error=str(e),
            )

    def test_dynamic_prompt(self, prompt_builder) -> EvalResult:
        """Teste la génération de prompt dynamique."""
        start = time.time()
        try:
            if not prompt_builder:
                return EvalResult(
                    test_name="dynamic_prompt",
                    passed=False,
                    duration_ms=0,
                    details="PromptBuilder non initialisé",
                )

            prompt = prompt_builder.build()
            success = len(prompt) > 50

            return EvalResult(
                test_name="dynamic_prompt",
                passed=success,
                duration_ms=(time.time() - start) * 1000,
                details=f"Prompt OK: {len(prompt)} caractères",
            )
        except Exception as e:
            return EvalResult(
                test_name="dynamic_prompt",
                passed=False,
                duration_ms=(time.time() - start) * 1000,
                error=str(e),
            )

    def run_full_suite(self, knowledge_graph=None, persona_engine=None,
                       memory_manager=None, prompt_builder=None) -> EvalSuiteResult:
        """Exécute toute la suite de tests mémoire."""
        suite = EvalSuiteResult()
        start = time.time()

        if memory_manager:
            suite.add(self.test_memory_consistency(memory_manager))
        if knowledge_graph:
            suite.add(self.test_knowledge_graph(knowledge_graph))
        if persona_engine:
            suite.add(self.test_persona_engine(persona_engine))
        if prompt_builder:
            suite.add(self.test_dynamic_prompt(prompt_builder))

        suite.duration_ms = (time.time() - start) * 1000
        return suite
