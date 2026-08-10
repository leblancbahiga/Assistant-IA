# Architecture NURU — Matrice des dépendances

**Chantier** : V18-15 apport ④ (documents d'architecture vivants)
**Contrat** : V18.md — V18-15, §1 Dépendances (l.119)
**Nature** : documentation vivante — ZÉRO code

---

## 1. Dépendances logicielles du benchmark V18-15

| Composant V18-15 | Dépend de | Raison |
|---|---|---|
| `src/benchmark/runner.py` | `src.routing.v16.benchmark` (LABELED_SET, run_precision) | rejouer les 40 cas de routage |
| `src/benchmark/runner.py` | `src.routing.v16.router_v16` (RouterV16) | routeur déterministe du routage |
| `src/benchmark/runner.py` | `src.learning.self_eval` (SelfEvaluator) | juge niveau 2 (échantillon 5-10 %) |
| `src/benchmark/runner.py` | `src.benchmark.judge` (CitationJudge, HallucinationTaxonomy) | juge niveau 1 + taxonomie A/B/C/D |
| `src/benchmark/runner.py` | `src.benchmark.report` (BenchmarkReport) | rapport JSON `benchmark_*.json` |
| `src/benchmark/runner.py` | `src.config` (config.minimal_pipeline) | Mode Minimal Pipeline (`--minimal`) |
| `src/benchmark/runner.py` | `src.nuru_core` (NuruCore) | phase RAG locale (gate M1) |
| `run.py` | `src.benchmark.runner` (run_benchmark_cli) | branche headless `--benchmark` |
| `src/routing/v16/benchmark.py` | `src.routing.v16.router_v16` | module benchmark pré-existant |

## 2. Dépendances inter-chantiers (V18.md §1)

| V18-15 nécessite | Raison | Statut |
|---|---|---|
| **V18-24** + **V18-34b** (contrainte d'activation coverage) | la Citation Coverage exige un prompt qui demande le format `[SOURCE i]` | NON implantés → coverage rejetée, jamais comptée comme échec |
| **V18-13** (template nettoyé) | préalable de V18-24 | NON implanté |
| Gardes V18-31 / V18-02 / V18-14 | restent ACTIVES en mode minimal | jamais désactivées par `minimal_pipeline` |

**V18-15 bloque** : V18-41 (critères de sortie — recall@5, coverage),
V18-33 (réactivation des tests).

**V18-15 sert de détecteur** pour V18-01/23/24/34 : A/B avant/après chaque
changement RAG.

## 3. Dépendances d'environnement

| Contrainte | Impact |
|---|---|
| MLX Apple Silicon (M1 8 Go) | la phase RAG du benchmark est un gate LOCAL/DEV uniquement |
| CI ubuntu-latest (Linux x86) | ne couvre QUE le routage déterministe (40 cas) — jamais les modèles MLX |
| `HF_HUB_OFFLINE=1` | aucun téléchargement HF pendant les tests / le benchmark |
| `.venv` Python 3.13 natif | `unset PYTHONPATH` avant activation (contamination Hermes 3.11) |

## 4. Contrainte d'activation de la coverage

La métrique `citation_coverage` dépend de la production réelle de
références `[SOURCE i]` par le LLM (V18-24 prompt + V18-34b format).
`BenchmarkReport._coverage_activation_status` vérifie le format dans le
contexte : s'il est absent, la coverage est REJETÉE comme « contrainte
d'activation non satisfaite » — jamais un échec du benchmark.

## 5. Dernière vérification

- Date : 2026-08-10
- Vérifié : imports réels de `runner.py` (v16.benchmark, self_eval, judge,
  report, config, nuru_core lazy), branche `--benchmark` dans `run.py`
  AVANT toute instanciation Qt, gate M1 documenté (benchmark RAG local/dev),
  gardes `check_strict_blocks` / `Validate.run` sans référence à
  `minimal_pipeline` (tests `test_minimal_pipeline.py`).
