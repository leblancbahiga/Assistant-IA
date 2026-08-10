# Architecture NURU — Contrat des points d'entrée

**Chantier** : V18-15 apport ④ (documents d'architecture vivants)
**Contrat** : V18.md — V18-15 (CLI, l.59), spec V18-15 §3.2/§3.5/§3.6
**Nature** : documentation vivante — ZÉRO code

---

## 1. CLI applicative — `python run.py`

| Commande | Comportement | Sortie |
|---|---|---|
| `python run.py` | Lance l'UI (nouvelle UI si `USE_NEW_UI`) | App PySide6 |
| `python run.py --legacy` | Lance l'UI legacy | App |
| `python run.py --benchmark` | Branche HEADLESS benchmark AVANT toute instanciation Qt | JSON + rapport fichier |
| `python run.py --benchmark --routing` | Scope routage uniquement (défaut CI, rapide, zéro modèle) | JSON des 40 cas, exit 0 |
| `python run.py --benchmark --minimal` | Mode Minimal Pipeline (`config.minimal_pipeline=True`) | JSON mode="minimal" |
| `python run.py --benchmark --samples N` | Fraction échantillon juge niveau 2 (défaut 0.10) | JSON |

Sortie : `benchmark_<timestamp>.json` à la racine du projet (gitignoré) ;
le JSON complet est imprimé sur stdout.

## 2. Contrat `run_benchmark_cli(argv)` — `src/benchmark/runner.py`

- **Entrée** : `argv` (défaut `sys.argv`). Flags : `--routing`,
  `--minimal`, `--samples N` ; la présence de `--benchmark` est la branche.
- **Retour** : `int` — `0` si `routing.floor_ok` (accuracy ≥ plancher),
  `1` sinon.
- **Effets** : écrit `benchmark_<ts>.json`, print le rapport JSON sur stdout.
- `run.py` fait `sys.exit(run_benchmark_cli(sys.argv))`.

## 3. Contrat `run_benchmark(...)` — orchestration publique

```python
run_benchmark(*, scope="routing+rag", mode="full", minimal=False,
              sample_level2=0.1, out_path="benchmark_<ts>.json",
              routing_only=False) -> dict
```

Retour :

```json
{
  "routing": {"n_cases": 40, "accuracy": 1.0, "errors": [],
              "floor": 0.85, "floor_ok": true},
  "rag": {"n_cases": 0, "routing_accuracy": 1.0,
          "note": "Rapport de routage uniquement (CI). ..."},
  "mode": "full",
  "report_path": "benchmark_<ts>.json",
  "report_json": "{...}"
}
```

- `scope="routing"` / `routing_only=True` : pas de RAG, pas de NuruCore
  (CI-viable).
- `scope="routing+rag"` : phase RAG locale (gate M1) — si NuruCore
  n'est pas constructible, `BenchResultError` → bloc `rag` avec `error`,
  jamais un crash.

## 4. Contrat du rapport JSON — `src/benchmark/report.py`

Schéma `benchmark_*.json` (spec §3.5) :

```json
{
  "timestamp": "2026-08-10T...",
  "version": "0.1.0",
  "scope": "routing+rag | routing",
  "mode": "full | minimal",
  "routing": {"n_cases": 40, "accuracy": 0.xx,
              "errors": [["query","expected","got","reasoning"]],
              "floor": 0.85, "floor_ok": true},
  "rag": {
    "n_cases": 10,
    "recall@5": 0.xx,
    "citation_coverage": 0.xx,
    "hallucination_taxonomy": {"A": 0, "B": 0, "C": 0, "D": 0},
    "level2_sample": {"n": 1, "faithfulness": 0.xx, "precision": 0.xx,
                      "overall": 0.xx, "hallucination_score": 0.xx},
    "sample_fraction": 0.1,
    "cases": [{"query": "...", "citation_coverage": 0.xx, "has_citation": false}],
    "sample_context": "...",
    "note": "..."
  },
  "cibles_v18_41": {"recall5_ok": false, "coverage_activable": false,
                    "coverage_ok": false, "coverage_reason": "..."}
}
```

**Contrainte d'activation** : si le format `[SOURCE i]` est absent du
contexte (V18-24/34b non implantés), `coverage_activable=false` et
`coverage_ok=false` avec raison — la coverage n'est JAMAIS comptée comme
échec.

## 5. Briques pré-existantes importées (AGENTS.md §7.2 — zéro doublon)

| Point d'entrée | Signature | Retour |
|---|---|---|
| `src.routing.v16.benchmark.run_precision` | `(router) -> tuple[float, list]` | accuracy + erreurs (query, expected, got, reasoning) |
| `src.routing.v16.benchmark.run_latency` | `(router, n=2000) -> dict` | `{p50_ms, p95_ms, p99_ms, max_ms}` |
| `python -m src.routing.v16.benchmark` | — | texte brut (précision + latence) |
| `src.learning.self_eval.SelfEvaluator.evaluate` | `(query, response, sources=None, context=None) -> EvalResult` | 5 dims + overall, bornées [0,1] |
| `src.benchmark.judge.CitationJudge.coverage` | `(response, rag_context) -> float` | proportion citations valides |
| `src.benchmark.judge.HallucinationTaxonomy.classify` | `(rag_context, coverage, level2=None) -> str` | `"A" | "B" | "C" | "D"` |

## 6. Contrat du pipeline — `PipelineEngine.run`

```python
await pipeline.run(query: str, session_id: str = "default") -> PipelineContext
```

- Retourne le `PipelineContext` (response, rag_context, rag_result, intent,
  error, strict_refused, ...).
- Utilisé par le benchmark RAG (`runner._run_rag_case`) et par l'UI.

## 7. Dernière vérification

- Date : 2026-08-10
- Vérifié : `python run.py --benchmark --routing` → JSON 40 cas, exit 0,
  zéro Qt (exécuté) ; `run_benchmark(minimal=True)` → mode="minimal" ;
  `run_precision(RouterV16())` → accuracy 1.0 (40/40).
