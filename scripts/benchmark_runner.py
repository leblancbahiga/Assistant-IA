#!/usr/bin/env python3
"""
NURU V15 Phase 4 — Benchmark Runner (Item 36, P1 #36)
Lance l'évaluation RAG sur le dataset et produit un rapport JSON/Markdown.

Ajouts V15 :
- Recall@K, MRR, MAP
- Percentiles de latence (p50, p95, p99)
- Tracking historique (comparaison avec runs précédents)
- Validation du dataset (sources existent-elles dans l'index ?)
- CLI --dry-run, --format json|md, --history
"""

import argparse
import asyncio
import csv
import json
import logging
import os
import sqlite3
import statistics
import sys
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.rag_engine import RAGEngine
from src.learning.self_eval import SelfEvaluator, EvalResult
import yaml

logger = logging.getLogger(__name__)

HISTORY_DB = str(Path.home() / ".nuru" / "benchmark_history.db")


@dataclass
class BenchmarkCase:
    question: str
    expected_source: str
    expected_keywords: list[str]
    doc_type: str
    expected_source_id: Optional[str] = None  # V15 : ID source pour validation plus précise


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
    # V15 : métriques étendues
    recall_at_k: float = 0.0      # Recall@K (la source attendue est-elle dans les K résultats ?)
    mrr: float = 0.0              # Mean Reciprocal Rank
    retrieval_order: int = -1     # Rang de la source attendue (-1 = pas trouvée)
    num_chunks: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class DatasetStats:
    total: int = 0
    types: dict[str, int] = field(default_factory=dict)
    missing_sources: list[str] = field(default_factory=list)
    avg_keywords: float = 0.0
    valid: bool = True


class BenchmarkRunner:
    def __init__(self, dataset_path: str):
        self.dataset_path = dataset_path
        self.engine = RAGEngine()
        self.evaluator = SelfEvaluator()
        self.cases: list[BenchmarkCase] = []
        self._index_path: Optional[str] = None

    def load_dataset(self) -> list[BenchmarkCase]:
        with open(self.dataset_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.cases = [
            BenchmarkCase(
                question=item["question"],
                expected_source=item["expected_source"],
                expected_keywords=item["expected_keywords"],
                doc_type=item.get("doc_type", "unknown"),
                expected_source_id=item.get("expected_source_id"),
            )
            for item in data
        ]
        return self.cases

    def validate_dataset(self) -> DatasetStats:
        """Valide le dataset : check que les sources attendues existent."""
        stats = DatasetStats(total=len(self.cases))

        type_counts: dict[str, int] = {}
        for case in self.cases:
            type_counts[case.doc_type] = type_counts.get(case.doc_type, 0) + 1
        stats.types = type_counts

        # Mots-clés moyens
        kw_counts = [len(c.expected_keywords) for c in self.cases]
        stats.avg_keywords = statistics.mean(kw_counts) if kw_counts else 0.0

        # Vérifier l'existence des sources attendues dans l'index
        # On extrait juste le chemin du fichier, on vérifie son existence
        for case in self.cases:
            if not self._path_exists(case.expected_source):
                stats.missing_sources.append(case.expected_source)

        if stats.missing_sources:
            stats.valid = False

        return stats

    def _path_exists(self, source: str) -> bool:
        """Vérifie si une source RAG existe dans l'index."""
        # Essayer d'abord comme chemin de fichier absolu
        p = Path(source)
        if p.exists():
            return True
        # Puis relatif à documents/
        doc_dir = Path.home() / ".nuru" / "documents"
        if (doc_dir / source).exists():
            return True
        # Vérifier dans l'index SQLite
        try:
            conn = sqlite3.connect(str(self.engine.db_path), timeout=5)
            row = conn.execute(
                "SELECT 1 FROM documents WHERE source LIKE ? OR source = ?",
                (f"%{source}%", source),
            ).fetchone()
            conn.close()
            return row is not None
        except Exception:
            return False

    async def run_single(self, case: BenchmarkCase) -> BenchmarkResult:
        start = time.time()
        ctx, res = await self.engine.retrieve(case.question)
        retrieval_time_ms = (time.time() - start) * 1000

        # Extraire les sources du contexte
        retrieved_sources = []
        for line in ctx.split("\n"):
            if line.startswith("[SOURCE") and "]" in line:
                retrieved_sources.append(line.split("]")[0] + "]")

        # V15 : Recall@K & MRR
        recall_at_k = 0.0
        mrr = 0.0
        retrieval_order = -1
        for idx, src in enumerate(retrieved_sources):
            if case.expected_source.lower() in src.lower():
                retrieval_order = idx + 1  # 1-indexed
                recall_at_k = 1.0
                mrr = 1.0 / (idx + 1)
                break

        # Réponse synthétique depuis le contexte
        response = ctx[:2000] if ctx else "Aucun contexte récupéré"

        # Évaluation
        eval_result = self.evaluator.evaluate(
            query=case.question,
            response=response,
            sources=retrieved_sources,
            context=ctx,
        )

        # Critères de réussite
        source_match = any(
            case.expected_source.lower() in s.lower() for s in retrieved_sources
        )
        keyword_match = any(
            kw.lower() in response.lower() for kw in case.expected_keywords
        )
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
            recall_at_k=recall_at_k,
            mrr=mrr,
            retrieval_order=retrieval_order,
            num_chunks=len(retrieved_sources),
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

        # Agrégation
        latencies = [r.retrieval_time_ms for r in results]
        scores = [r.eval_result.overall for r in results]

        by_type: dict[str, list[BenchmarkResult]] = {}
        for r in results:
            by_type.setdefault(r.doc_type, []).append(r)

        summary = {
            "run_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "timestamp": time.time(),
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "pass_rate": (
                sum(1 for r in results if r.passed) / len(results) if results else 0
            ),
            # V15 : métriques avancées
            "avg_recall_at_k": statistics.mean([r.recall_at_k for r in results]) if results else 0,
            "avg_mrr": statistics.mean([r.mrr for r in results]) if results else 0,
            "median_retrieval_ms": statistics.median(latencies) if latencies else 0,
            "p95_retrieval_ms": sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0,
            "p99_retrieval_ms": sorted(latencies)[int(len(latencies) * 0.99)] if latencies else 0,
            "avg_retrieval_ms": sum(latencies) / len(latencies) if latencies else 0,
            "avg_overall": statistics.mean(scores) if scores else 0,
            "median_overall": statistics.median(scores) if scores else 0,
            "avg_faithfulness": statistics.mean(
                [r.eval_result.faithfulness for r in results]
            ) if results else 0,
            "avg_relevance": statistics.mean(
                [r.eval_result.answer_relevance for r in results]
            ) if results else 0,
            "avg_precision": statistics.mean(
                [r.eval_result.context_precision for r in results]
            ) if results else 0,
            "avg_recall": statistics.mean(
                [r.eval_result.context_recall for r in results]
            ) if results else 0,
            "avg_hallucination": statistics.mean(
                [r.eval_result.hallucination_score for r in results]
            ) if results else 0,
            "by_type": {
                dt: {
                    "count": len(rs),
                    "passed": sum(1 for r in rs if r.passed),
                    "pass_rate": (
                        sum(1 for r in rs if r.passed) / len(rs) if rs else 0
                    ),
                    "avg_overall": statistics.mean(
                        [r.eval_result.overall for r in rs]
                    ) if rs else 0,
                    "avg_recall_at_k": statistics.mean(
                        [r.recall_at_k for r in rs]
                    ) if rs else 0,
                    "avg_mrr": statistics.mean(
                        [r.mrr for r in rs]
                    ) if rs else 0,
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
                    "recall_at_k": r.recall_at_k,
                    "mrr": r.mrr,
                    "retrieval_order": r.retrieval_order,
                }
                for r in results
            ],
        }
        return summary

    def save_history(self, summary: dict[str, Any]):
        """Sauvegarde le résumé dans l'historique SQLite."""
        conn = sqlite3.connect(HISTORY_DB, timeout=10)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS benchmark_history (
                    run_id TEXT PRIMARY KEY,
                    timestamp REAL,
                    total INTEGER,
                    passed INTEGER,
                    failed INTEGER,
                    pass_rate REAL,
                    avg_recall_at_k REAL,
                    avg_mrr REAL,
                    avg_retrieval_ms REAL,
                    median_retrieval_ms REAL,
                    p95_retrieval_ms REAL,
                    avg_overall REAL,
                    by_type TEXT
                )
            """)
            conn.execute(
                """INSERT OR REPLACE INTO benchmark_history VALUES
                   (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    summary["run_id"],
                    summary["timestamp"],
                    summary["total"],
                    summary["passed"],
                    summary["failed"],
                    summary["pass_rate"],
                    summary["avg_recall_at_k"],
                    summary["avg_mrr"],
                    summary["avg_retrieval_ms"],
                    summary["median_retrieval_ms"],
                    summary["p95_retrieval_ms"],
                    summary["avg_overall"],
                    json.dumps(summary.get("by_type", {})),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_history(self, limit: int = 10) -> list[dict]:
        """Récupère les N derniers runs."""
        conn = sqlite3.connect(HISTORY_DB, timeout=10)
        try:
            rows = conn.execute(
                "SELECT * FROM benchmark_history ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            columns = [d[0] for d in conn.execute(
                "PRAGMA table_info(benchmark_history)"
            ).fetchall()]
            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()

    def format_report_markdown(self, summary: dict) -> str:
        """Produit un rapport Markdown lisible."""
        lines = [
            f"# 📊 Benchmark RAG — {summary['run_id']}",
            "",
            f"**{summary['passed']}/{summary['total']}** réussis "
            f"({summary['pass_rate']*100:.1f}%)",
            "",
            "## Métriques globales",
            "| Métrique | Valeur |",
            "|----------|--------|",
            f"| Pass rate | {summary['pass_rate']*100:.1f}% |",
            f"| Recall@K | {summary['avg_recall_at_k']*100:.1f}% |",
            f"| MRR | {summary['avg_mrr']:.3f} |",
            f"| Score overall | {summary['avg_overall']:.3f} |",
            f"| Latence moyenne | {summary['avg_retrieval_ms']:.0f} ms |",
            f"| Latence médiane | {summary['median_retrieval_ms']:.0f} ms |",
            f"| P95 latence | {summary['p95_retrieval_ms']:.0f} ms |",
            "",
            "## Par type de document",
            "| Type | Count | Pass rate | Recall@K | MRR | Overall |",
            "|------|-------|-----------|----------|-----|---------|",
        ]
        for dt, info in summary.get("by_type", {}).items():
            lines.append(
                f"| {dt} | {info['count']} | "
                f"{info['pass_rate']*100:.1f}% | "
                f"{info['avg_recall_at_k']*100:.1f}% | "
                f"{info['avg_mrr']:.3f} | "
                f"{info['avg_overall']:.3f} |"
            )

        lines.append("")
        lines.append("## Résultats détaillés")
        for r in summary.get("results", []):
            mark = "✅" if r["passed"] else "❌"
            lines.append(
                f"- {mark} **{r['question'][:60]}** — "
                f"overall={r['eval']['overall']:.2f}, "
                f"recall@{r['recall_at_k']:.0f}, "
                f"mrr={r['mrr']:.2f}, "
                f"latence={r['retrieval_time_ms']:.0f}ms"
            )

        return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser(
        description="NURU RAG Benchmark Runner (V15 Phase 4)"
    )
    parser.add_argument("dataset", nargs="?", default="benchmark_dataset.yaml",
                        help="Dataset YAML path")
    parser.add_argument("--dry-run", action="store_true",
                        help="Valide le dataset sans lancer les tests")
    parser.add_argument("--format", choices=["json", "md"], default="md",
                        help="Format du rapport (défaut: md)")
    parser.add_argument("--history", action="store_true",
                        help="Affiche l'historique des runs")
    parser.add_argument("--history-limit", type=int, default=5,
                        help="Nombre de runs historiques à afficher")
    parser.add_argument("--output", type=str,
                        help="Chemin du fichier de sortie")
    args = parser.parse_args()

    runner = BenchmarkRunner(args.dataset)
    runner.load_dataset()
    ds = runner.validate_dataset()

    if args.history:
        print("## Historique des runs\n")
        rows = runner.get_history(args.history_limit)
        for r in rows:
            print(
                f"  {r['run_id']}: {r['passed']}/{r['total']} "
                f"({r['pass_rate']*100:.1f}%) — "
                f"Recall@{r['avg_recall_at_k']*100:.1f}%, "
                f"MRR={r['avg_mrr']:.3f}, "
                f"{r['avg_retrieval_ms']:.0f}ms"
            )
        return

    print(f"\nDataset : {args.dataset}")
    print(f"  Cas      : {ds.total}")
    print(f"  Types    : {ds.types}")
    print(f"  Sources manquantes : {len(ds.missing_sources) if ds.missing_sources else 0}")

    if ds.missing_sources:
        for s in ds.missing_sources[:5]:
            print(f"    ⚠️  {s}")
        print("  → Corrige les sources manquantes avant de lancer le benchmark.")
        if args.dry_run:
            return

    if args.dry_run:
        print("\n✅ Dataset valide. Dry-run terminé — aucun test lancé.")
        return

    summary = await runner.run_all()
    runner.save_history(summary)

    if args.format == "json":
        report = json.dumps(summary, indent=2, ensure_ascii=False)
    else:
        report = runner.format_report_markdown(summary)

    print(f"\n{'─' * 60}\n")
    print(report)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"\nRapport sauvegardé : {args.output}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
