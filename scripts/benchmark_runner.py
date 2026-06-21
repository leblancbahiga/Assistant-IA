#!/usr/bin/env python3
"""
NURU V12+ — Benchmark Runner
Lance l'évaluation RAG sur le dataset étendu et produit un rapport JSON/Markdown.
"""

import asyncio
import json
import sys
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.rag_engine import RAGEngine
from src.learning.self_eval import SelfEvaluator, EvalResult
import yaml


@dataclass
class BenchmarkCase:
    question: str
    expected_source: str
    expected_keywords: list[str]
    doc_type: str


@dataclass
class BenchmarkResult:
    question: str
    doc_type: str
    expected_source: str
    retrieved_sources: list[str]
    response: str
    eval_result: EvalResult
    retrieval_time_ms: float
    confidence_label: str
    top_score: float
    passed: bool


class BenchmarkRunner:
    def __init__(self, dataset_path: str):
        self.dataset_path = dataset_path
        self.engine = RAGEngine()
        self.evaluator = SelfEvaluator()
        self.cases: list[BenchmarkCase] = []

    def load_dataset(self) -> list[BenchmarkCase]:
        with open(self.dataset_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.cases = [
            BenchmarkCase(
                question=item["question"],
                expected_source=item["expected_source"],
                expected_keywords=item["expected_keywords"],
                doc_type=item.get("doc_type", "unknown"),
            )
            for item in data
        ]
        return self.cases

    async def run_single(self, case: BenchmarkCase) -> BenchmarkResult:
        start = time.time()
        ctx, res = await self.engine.retrieve(case.question)
        retrieval_time_ms = (time.time() - start) * 1000

        # Extraire les sources du contexte
        retrieved_sources = []
        for line in ctx.split("\n"):
            if line.startswith("[SOURCE") and "]" in line:
                retrieved_sources.append(line.split("]")[0] + "]")

        # Construire une réponse synthétique depuis le contexte
        response = ctx[:2000] if ctx else "Aucun contexte récupéré"

        # Évaluation
        eval_result = self.evaluator.evaluate(
            query=case.question,
            response=response,
            sources=retrieved_sources,
            context=ctx,
        )

        # Critères de réussite
        source_match = any(case.expected_source.lower() in s.lower() for s in retrieved_sources)
        keyword_match = any(kw.lower() in response.lower() for kw in case.expected_keywords)
        passed = source_match and keyword_match and eval_result.overall >= 0.4

        return BenchmarkResult(
            question=case.question,
            doc_type=case.doc_type,
            expected_source=case.expected_source,
            retrieved_sources=retrieved_sources,
            response=response[:500],
            eval_result=eval_result,
            retrieval_time_ms=retrieval_time_ms,
            confidence_label=res.confidence_label if hasattr(res, "confidence_label") else "N/A",
            top_score=res.top_score if hasattr(res, "top_score") else 0.0,
            passed=passed,
        )

    async def run_all(self) -> dict[str, Any]:
        if not self.cases:
            self.load_dataset()

        print(f"📊 Benchmark sur {len(self.cases)} cas...")
        results: list[BenchmarkResult] = []

        for i, case in enumerate(self.cases, 1):
            print(f"  [{i}/{len(self.cases)}] {case.question[:60]}...")
            result = await self.run_single(case)
            results.append(result)

        # Agrégation par type
        by_type: dict[str, list[BenchmarkResult]] = {}
        for r in results:
            by_type.setdefault(r.doc_type, []).append(r)

        summary = {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "pass_rate": sum(1 for r in results if r.passed) / len(results) if results else 0,
            "avg_retrieval_ms": sum(r.retrieval_time_ms for r in results) / len(results) if results else 0,
            "avg_overall": sum(r.eval_result.overall for r in results) / len(results) if results else 0,
            "avg_faithfulness": sum(r.eval_result.faithfulness for r in results) / len(results) if results else 0,
            "avg_relevance": sum(r.eval_result.answer_relevance for r in results) / len(results) if results else 0,
            "avg_precision": sum(r.eval_result.context_precision for r in results) / len(results) if results else 0,
            "avg_recall": sum(r.eval_result.context_recall for r in results) / len(results) if results else 0,
            "avg_hallucination": sum(r.eval_result.hallucination_score for r in results) / len(results) if results else 0,
            "by_type": {
                dt: {
                    "count": len(rs),
                    "passed": sum(1 for r in rs if r.passed),
                    "pass_rate": sum(1 for r in rs if r.passed) / len(rs),
                    "avg_overall": sum(r.eval_result.overall for r in rs) / len(rs),
                }
                for dt, rs in by_type.items()
            },
            "results": [
                {
                    "question": r.question,
                    "doc_type": r.doc_type,
                    "expected_source": r.expected_source,
                    "retrieved_sources": r.retrieved_sources,
                    "passed": r.passed,
                    "eval": asdict(r.eval_result),
                    "retrieval_time_ms": r.retrieval_time_ms,
                    "confidence_label": r.confidence_label,
                    "top_score": r.top_score,
                }
                for r in results
            ],
        }
        return summary

    def save_report(self, summary: dict, output_path: str):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"💾 Rapport JSON : {output_path}")

    def print_summary(self, summary: dict):
        print("\n" + "=" * 60)
        print("📈 RÉSUMÉ BENCHMARK")
        print("=" * 60)
        print(f"Total cas      : {summary['total']}")
        print(f"✅ Réussis     : {summary['passed']}")
        print(f"❌ Échoués     : {summary['failed']}")
        print(f"📊 Taux succès : {summary['pass_rate']:.1%}")
        print(f"⏱️  Récup. moy. : {summary['avg_retrieval_ms']:.0f} ms")
        print()
        print("Scores moyens :")
        print(f"  Overall       : {summary['avg_overall']:.3f}")
        print(f"  Faithfulness  : {summary['avg_faithfulness']:.3f}")
        print(f"  Relevance     : {summary['avg_relevance']:.3f}")
        print(f"  Precision     : {summary['avg_precision']:.3f}")
        print(f"  Recall        : {summary['avg_recall']:.3f}")
        print(f"  No Halluc.    : {summary['avg_hallucination']:.3f}")
        print()
        print("Par type :")
        for dt, stats in summary["by_type"].items():
            print(f"  {dt:15s} : {stats['count']:3d} cas | {stats['pass_rate']:.1%} | overall={stats['avg_overall']:.3f}")


async def main():
    dataset = "tests/rag_eval_dataset.yaml"
    output = "benchmark_report.json"

    runner = BenchmarkRunner(dataset)
    runner.load_dataset()
    summary = await runner.run_all()
    runner.save_report(summary, output)
    runner.print_summary(summary)

    # Code de sortie pour CI
    sys.exit(0 if summary["pass_rate"] >= 0.5 else 1)


if __name__ == "__main__":
    asyncio.run(main())