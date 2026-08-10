"""V18-15 — Benchmark A/B opérationnel.

Orchestration nouvelle par-dessus les briques existantes (AGENTS.md §7.2 —
AUCUNE duplication) :
  - `src.routing.v16.benchmark`  → LABELED_SET, run_precision  (routage, 40 cas)
  - `src.learning.self_eval`     → SelfEvaluator                (juge niveau 2)

Les classes ici (CitationJudge, HallucinationTaxonomy, runner, report)
sont l'orchestration du benchmark, pas des réimplémentations de briques.
"""