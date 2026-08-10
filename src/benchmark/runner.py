"""V18-15 — Runner du benchmark A/B.

Orchestration par-dessus les briques existantes (AGENTS.md §7.2 — aucune
duplication) :
  - from src.routing.v16.benchmark import LABELED_SET, run_precision
  - from src.learning.self_eval import SelfEvaluator

Scopes :
  - "routing" (flag `--routing`, défaut CI) : 40 cas déterministes, zéro modèle.
  - "rag"     (`--benchmark`) : routage + RAG (10 questions de référence) +
    juge N1 (CitationJudge, couverture) + juge N2 (SelfEvaluator ≥ 5 %).
Le benchmark RAG est un gate local/dev (M1) — la CI ne couvre que le routage.

Le flag `--minimal` active config.minimal_pipeline (Mode Minimal Pipeline) :
court-circuite QueryRewrite / HYDE / Spotlight / Speculative / Décomposition.
Les gardes V18-31/02/14 ne sont JAMAIS désactivées par ce flag.
"""

from __future__ import annotations

import asyncio
import logging
import random
import sys
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Import de l'existant (AGENTS.md §7.2) ────────────────────────
from src.benchmark.judge import CitationJudge, HallucinationTaxonomy
from src.benchmark.report import BenchmarkReport
from src.learning.self_eval import SelfEvaluator
from src.routing.v16.benchmark import LABELED_SET, run_precision
from src.routing.v16.router_v16 import RouterV16

# Plancher CI (V18-15 spec §3.6). À recalibrer sur la 1ère mesure réelle.
ACCURACY_FLOOR = 0.85

# Questions RAG de référence (10) — typées RAG, s'appuient sur l'index local.
# Ce sont des questions « documentaires » alignées avec le catalogue de docs
# indexées (Bénin, IITA, YARID, CV, projets, rapports, diplômes, FAO).
RAG_REFERENCE_QUESTIONS: list[str] = [
    "Résume mon CV",
    "Qui est Leblanc ?",
    "Parle-moi de mon expérience à la FAO",
    "Explique la photosynthèse dans mon rapport",
    "Ouvre le document du projet Walikale",
    "Cherche dans mes fichiers le rapport IITA",
    "Ma lettre de motivation pour YARID",
    "Ouvre mon rapport annuel",
    "Quel est le compte-rendu de la dernière réunion YARID ?",
    "Mon diplôme est-il dans le dossier ?",
]

# Seuil : extraire les ids cités pour le rappel via recouvrement lexical.
import re as _re
_STOP_TERMS = {
    "le ", "la ", "les ", "un ", "une ", "des ", "du ", "de ", "et ", "est ",
    "a ", "à ", "dans ", "pour ", "sur ", "avec ", "pas ", "que ", "qui ", "par",
    "ou ", "où ", "si ", "ce ", "je ", "mon ", "ma ", "mes ", "dans ",
}


def _signif_keywords(query: str) -> set[str]:
    """Mots-clés significatifs d'une requête (proxy lexical)."""
    q = query.lower()
    words = _re.findall(r"[a-zéèêëàâùûîôç]{4,}", q)
    return {w for w in words if f"{w} " not in _STOP_TERMS and w not in (
        "quand", "quoi", "quel", "quelle", "quels", "quelles", "comment",
        "pourquoi", "combien", "est-ce", "avec", "dans", "pour", "ouvert",
    )}


def _recall_at_5_proxy(query: str, rag_context: str) -> float:
    """Recall@5 lexical (proxy) : 1.0 si un mot-clé de la requête apparaît
    dans le contexte récupéré (top-5), sinon 0.0. Documenté comme heuristique
    faute de ground-truth source étiqueté."""
    kws = _signif_keywords(query)
    if not kws:
        return 1.0 if rag_context.strip() else 0.0
    ctx = (rag_context or "").lower()
    return 1.0 if any(kw in ctx for kw in kws) else 0.0


class BenchResultError(RuntimeError):
    """Échec d'une phase du benchmark (environnement / construction)."""

    pass


# ── Phase routage (déterministe, CI) ─────────────────────────────

def run_benchmark_routing(router=None) -> dict:
    """Rejoue les 40 cas LABELED_SET → {n_cases, accuracy, errors}."""
    router = router or RouterV16()
    accuracy, errors = run_precision(router)
    return {
        "n_cases": len(LABELED_SET),
        "accuracy": round(accuracy, 4),
        "errors": errors,
        "floor": ACCURACY_FLOOR,
        "floor_ok": accuracy >= ACCURACY_FLOOR,
    }


# ── Phase RAG (local/dev, M1) ────────────────────────────────────

def _build_pipeline():
    """Construit NuruCore + pipeline (chemin live, zéro Qt)."""
    from src.nuru_core import NuruCore
    core = NuruCore()
    return core


async def _run_rag_case(core, query: str) -> dict:
    """Exécute une question RAG dans le pipeline Kernel.

    Retourne {query, response, rag_context, rag_result, error}.
    """
    try:
        ctx = await core.pipeline.run(query, session_id="benchmark")
    except Exception as e:  # noqa: BLE001
        return {"query": query, "response": "", "rag_context": "",
                "rag_result": None, "error": f"{type(e).__name__}: {e}"}
    return {
        "query": query,
        "response": ctx.response or "",
        "rag_context": ctx.rag_context or "",
        "rag_result": ctx.rag_result,
        "error": ctx.error,
    }


def _n2_sample(items: list[dict], fraction: float, seed: int) -> list[dict]:
    """Échantillonne (seed fixe) la fraction demandée pour le juge niveau 2."""
    if fraction <= 0.0 or not items:
        return []
    n = max(1, round(len(items) * fraction))
    rng = random.Random(seed)
    return rng.sample(items, min(n, len(items)))


def run_benchmark_rag(
    *,
    questions: Optional[list[str]] = None,
    sample_level2: float = 0.1,
    seed: int = 42,
) -> dict:
    """Routage + RAG + juge N1 + SelfEvaluator N2.

    Retourne le dict `rag` du rapport JSON. Levient BenchResultError si le
    pipeline ne peut pas être construit (environnement).
    """
    questions = questions or RAG_REFERENCE_QUESTIONS
    routing = run_benchmark_routing()

    try:
        core = _build_pipeline()
    except Exception as e:  # noqa: BLE001
        raise BenchResultError(f"Impossible de construire NuruCore : {e!r}") from e

    judge = CitationJudge()
    taxonomy = HallucinationTaxonomy()
    evaluator = SelfEvaluator()

    # 1. Exécuter les questions RAG (séquentiel pour borner la RAM M1)
    try:
        cases = asyncio.run(_execute_cases(core, questions))
    finally:
        _teardown(core)

    # 2. Juge N1 (coverage) sur TOUS les cas
    for c in cases:
        c["citation_coverage"] = judge.coverage(c["response"], c["rag_context"])
        c["annotated"] = judge.annotated_affirmations(c["response"], c["rag_context"])

    # 3. Juge N2 (SelfEvaluator) sur l'échantillon (seed fixe)
    sample = _n2_sample(cases, sample_level2, seed)
    n2 = {"n": 0, "faithfulness": 0.0, "precision": 0.0, "overall": 0.0,
          "hallucination_score": 0.0}
    if sample:
        dims = []
        for c in sample:
            try:
                er = evaluator.evaluate(
                    c["query"], c["response"],
                    sources=c.get("_source_texts", []),
                    context=c["rag_context"],
                )
                dims.append(er)
            except Exception as e:  # noqa: BLE001
                logger.warning("SelfEvaluator échec pour %r : %s", c["query"], e)
        if dims:
            n2 = {
                "n": len(dims),
                "faithfulness": round(sum(d.faithfulness for d in dims) / len(dims), 4),
                "precision": round(sum(d.context_precision for d in dims) / len(dims), 4),
                "overall": round(sum(d.overall for d in dims) / len(dims), 4),
                "hallucination_score": round(
                    sum(d.hallucination_score for d in dims) / len(dims), 4),
            }

    # 4. Taxonomie A/B/C/D
    labels = []
    for c in cases:
        lvl2 = None
        if c in sample and n2["n"]:
            lvl2 = {"faithfulness": n2["faithfulness"]}
        labels.append(taxonomy.classify(c["rag_context"], c["citation_coverage"], lvl2))
    taxa = taxonomy.distribution(labels)

    # 5. Recall@5 (proxy lexical documenté)
    recalls = [_recall_at_5_proxy(c["query"], c["rag_context"]) for c in cases]
    recall5 = round(sum(recalls) / len(recalls), 4) if recalls else 0.0

    # 6. Citation coverage moyenne (niveau 1) sur TOUS les cas RAG.
    # La rejet éventuelle (contrainte d'activation, V18-24/34b) est gérée au
    # niveau du rapport via _coverage_activation_status.
    covs = [c["citation_coverage"] for c in cases]
    avg_coverage = round(sum(covs) / len(covs), 4) if covs else 0.0

    rag_block = {
        "n_cases": len(cases),
        "recall@5": recall5,
        "citation_coverage": avg_coverage,
        "hallucination_taxonomy": taxa,
        "level2_sample": n2,
        "sample_fraction": sample_level2,
        "cases": [
            {
                "query": c["query"],
                "citation_coverage": c["citation_coverage"],
                "has_citation": _has_citation(c),
            }
            for c in cases
        ],
        "sample_context": cases[0]["rag_context"][:2000] if cases else "",
        "note": (
            "Contrainte d'activation coverage : dépend de V18-24 + V18-34b "
            "(prompt + format [SOURCE i]). Rejetée jusqu'à activation. "
            "Recall@5 = proxy lexical (pas de ground-truth source étiqueté)."
        ),
    }
    rag_block["routing_accuracy"] = routing["accuracy"]
    return rag_block


def _has_citation(c: dict) -> bool:
    import re
    return bool(re.search(r"\[SOURCE\s+\d+\]", c.get("response") or ""))


async def _execute_cases(core, questions: list[str]):
    cases = []
    for q in questions:
        c = await _run_rag_case(core, q)
        cases.append(c)
        logger.info("🧪 RAG benchmark: %r → err=%s", q[:40], c["error"] or "none")
    return cases


def _teardown(core) -> None:
    """Mesure de ménage best-effort pour libérer les modèles M1."""
    try:
        import mlx.core as _mx  # noqa: F401  (ne force rien si absent)
    except Exception:
        pass
    try:
        if hasattr(core, "rag") and hasattr(core.rag, "clear_reranker"):
            core.rag.clear_reranker()
    except Exception:
        pass


# ── Orchestration publique + CLI ─────────────────────────────────

def run_benchmark(
    *,
    scope: str = "routing+rag",
    mode: str = "full",
    minimal: bool = False,
    sample_level2: float = 0.1,
    out_path: str = "benchmark_<ts>.json",
    routing_only: bool = False,
) -> dict:
    """Point d'entrée principal du benchmark (appelé par run.py --benchmark).

    scope : "routing" ou "routing+rag".
    mode : "full" (par défaut) ou "minimal" (Mode Minimal Pipeline).
    minimal : active config.minimal_pipeline si True.
    sample_level2 : fraction échantillonnée pour le juge niveau 2 (5-10 %).
    """
    if minimal:
        from src.config import config as _cfg
        _cfg.minimal_pipeline = True
        mode = "minimal"
        logger.info("🧪 Mode Minimal Pipeline ACTIF (V18-15) — 5 optimisations désactivées")

    routing = run_benchmark_routing()

    report = BenchmarkReport(scope=scope, mode=mode)
    if routing_only or scope == "routing":
        # Scope routage uniquement (défaut CI, zéro modèle, zéro NuruCore)
        rag_block = {
            "n_cases": 0,
            "routing_accuracy": routing["accuracy"],
            "note": "Rapport de routage uniquement (CI). Le benchmark RAG reste local/dev (M1).",
        }
    else:
        try:
            rag_block = run_benchmark_rag(sample_level2=sample_level2)
        except BenchResultError as e:
            logger.error("❌ Benchmark RAG indisponible : %s", e)
            rag_block = {
                "n_cases": 0,
                "error": str(e),
                "note": "Benchmark RAG non exécutable dans cet environnement (local/dev M1 requis).",
            }

    report.rag = rag_block
    report.routing = routing
    path = report.write(out_path)
    report.rag["report_path"] = path
    report.rag["report_json"] = report.dumps()

    # Retour HUMAN-readable + machine (rapport complet)
    return {
        "routing": routing,
        "rag": rag_block,
        "mode": mode,
        "report_path": path,
        "report_json": report.dumps(),
    }


def run_benchmark_cli(argv: Optional[list[str]] = None) -> int:
    """CLI headless du benchmark — retourne le code de sortie.

    Flags :
      --routing          scope routage uniquement (défaut CI, rapide)
      --minimal          Mode Minimal Pipeline (5 optimisations désactivées)
      --samples N        fraction niveau 2 (défaut 0.10)
      --benchmark        explicit (non requis, sert de branche)
    """
    argv = argv if argv is not None else sys.argv
    routing_only = "--routing" in argv
    minimal = "--minimal" in argv

    sample = 0.1
    try:
        idx = argv.index("--samples")
        sample = float(argv[idx + 1])
    except (ValueError, IndexError):
        pass

    import time

    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    scope = "routing" if routing_only else "routing+rag"
    logger.info("🧪 Benchmark V18-15 démarrage (scope=%s, minimal=%s, samples=%s)",
                scope, minimal, sample)

    result = run_benchmark(
        scope=scope,
        minimal=minimal,
        sample_level2=sample,
        routing_only=routing_only,
        out_path=f"benchmark_{ts}.json",
    )
    print(result["report_json"])
    return 0 if result["routing"].get("floor_ok") else 1