"""Tests V18-15 — branchement SelfEvaluator (juge niveau 2, échantillon 5-10 %).

Cible : `src/learning/self_eval.py` (SelfEvaluator, EvalResult) + son
branchement dans `src/benchmark/runner.py`.

Vérifie (spec V18-15 §2.2 / §3.4 / §6, Round 6 doctrine M1 8 Go) :
- SelfEvaluator est IMPORTÉ depuis `src.learning.self_eval` par le runner
  (AGENTS.md §7.2 — AUCUNE duplication, pas de réimplémentation) ;
- `evaluate(query, response, sources, context)` retourne un `EvalResult` avec
  les 5 dimensions RAGAS-like + `overall`, toutes bornées [0.0, 1.0] ;
- la fidélité reflète le support par les sources (heuristique lexicale,
  PAS juge LLM — doctrine Round 6) ;
- l'échantillonnage niveau 2 (`_n2_sample`) est seed-fixé, fraction 5-10 %
  (défaut 0.1), déterministe ;
- le runner expose la fraction d'échantillon dans le rapport RAG.
"""

import inspect

from src.benchmark.runner import _n2_sample, run_benchmark_rag
from src.learning.self_eval import EvalResult, SelfEvaluator


class TestSelfEvaluatorBranche:
    """Le runner importe SelfEvaluator — zéro duplication (AGENTS.md §7.2)."""

    def test_runner_imports_self_evaluator(self):
        import src.benchmark.runner as runner

        assert runner.SelfEvaluator is SelfEvaluator

    def test_sample_fraction_default_is_10_percent(self):
        """Spec : échantillon niveau 2 = 5-10 % (défaut 10 %)."""
        sig = inspect.signature(run_benchmark_rag)
        assert sig.parameters["sample_level2"].default == 0.1

    def test_report_exposes_sample_fraction(self):
        """Le bloc RAG du rapport trace la fraction d'échantillon (spec §3.4)."""
        import inspect as _inspect
        import src.benchmark.runner as runner

        src = _inspect.getsource(runner.run_benchmark_rag)
        assert '"sample_fraction"' in src
        assert '"level2_sample"' in src


class TestEvalResult:
    """Le résultat d'évaluation expose les 5 dimensions + overall."""

    def test_fields_exist(self):
        er = EvalResult()
        for field in (
            "faithfulness", "answer_relevance", "context_precision",
            "context_recall", "hallucination_score", "overall",
        ):
            assert hasattr(er, field), field

    def test_defaults_zero(self):
        er = EvalResult()
        assert er.faithfulness == 0.0
        assert er.overall == 0.0

    def test_weights_sum_to_one(self):
        assert abs(sum(SelfEvaluator.OVERALL_WEIGHTS.values()) - 1.0) < 1e-9


class TestSelfEvaluatorEvaluate:
    """evaluate() produit des scores bornés et cohérents."""

    def setup_method(self):
        self.evaluator = SelfEvaluator()

    def test_scores_bounded(self):
        er = self.evaluator.evaluate(
            "Résume mon CV",
            "Leblanc a travaillé à la FAO [SOURCE 1].",
            sources=["Leblanc Bahiga a travaillé à la FAO."],
            context="[SOURCE 1] Leblanc Bahiga a travaillé à la FAO.",
        )
        for value in (
            er.faithfulness, er.answer_relevance, er.context_precision,
            er.context_recall, er.hallucination_score, er.overall,
        ):
            assert 0.0 <= value <= 1.0

    def test_faithfulness_supported_by_sources(self):
        er = self.evaluator.evaluate(
            "Question",
            "Leblanc a travaillé à la FAO.",
            sources=["Leblanc Bahiga a travaillé à la FAO en 2020."],
            context="",
        )
        assert er.faithfulness == 1.0

    def test_faithfulness_low_without_support(self):
        er = self.evaluator.evaluate(
            "Question",
            "NURU a conquis Mars en 2042.",
            sources=["Leblanc Bahiga a travaillé à la FAO."],
            context="",
        )
        assert er.faithfulness < 0.5

    def test_empty_response_zero(self):
        er = self.evaluator.evaluate("Question", "", sources=["source"], context="ctx")
        assert er.faithfulness == 0.0

    def test_no_sources_returns_neutral(self):
        er = self.evaluator.evaluate(
            "Question", "Réponse sans sources.", sources=[], context="ctx"
        )
        assert er.faithfulness == 0.5


class TestN2Sample:
    """Échantillonnage du juge niveau 2 : seed fixe, fraction 5-10 %."""

    def _cases(self, n: int = 10):
        return [{"query": f"q{i}"} for i in range(n)]

    def test_fraction_ten_percent_of_ten(self):
        sample = _n2_sample(self._cases(10), 0.1, seed=42)
        assert len(sample) == 1

    def test_fraction_five_percent_of_twenty(self):
        sample = _n2_sample(self._cases(20), 0.05, seed=42)
        assert len(sample) == 1

    def test_deterministic_with_seed(self):
        cases = self._cases(10)
        s1 = _n2_sample(cases, 0.5, seed=7)
        s2 = _n2_sample(cases, 0.5, seed=7)
        assert [c["query"] for c in s1] == [c["query"] for c in s2]

    def test_zero_fraction_returns_empty(self):
        assert _n2_sample(self._cases(10), 0.0, seed=42) == []

    def test_negative_fraction_returns_empty(self):
        assert _n2_sample(self._cases(10), -0.1, seed=42) == []

    def test_full_fraction_returns_all(self):
        sample = _n2_sample(self._cases(10), 1.0, seed=42)
        assert len(sample) == 10

    def test_empty_items_returns_empty(self):
        assert _n2_sample([], 0.5, seed=42) == []

    def test_sample_does_not_mutate_items(self):
        cases = self._cases(10)
        _n2_sample(cases, 0.5, seed=42)
        assert len(cases) == 10
