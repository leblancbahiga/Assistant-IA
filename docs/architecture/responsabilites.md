# Architecture NURU — Carte des responsabilités

**Chantier** : V18-15 apport ④ (documents d'architecture vivants)
**Contrat** : V18.md — V18-15, V18-41
**Nature** : documentation vivante — ZÉRO code

---

## 1. Principe

Chaque composant a une responsabilité unique, un cycle de vie explicite
(init/shutdown via `ServiceRegistry`) et accède aux autres par le Kernel
(`NuruKernel.get(name)` / `get_service`) — pas d'imports croisés de
singletons entre couches.

## 2. Carte

| Composant | Fichier | Responsabilité | Cycle de vie |
|---|---|---|---|
| NuruCore | `src/nuru_core.py` | Assemblage racine : services, registre, pipeline | `NuruCore()` → init ; `close()` |
| NuruKernel | `src/kernel/__init__.py` | Résolution de services (`get`), registre | Singleton, lazy |
| PipelineEngine | `src/kernel/pipeline.py` | Orchestration des steps, `PipelineContext` | `run(query)` par requête |
| Steps (ReceiveQuestion → Respond) | `src/kernel/pipeline_steps.py` | Logique par étape du pipeline | Steps stateless, contexte mutable |
| RAGOrchestrator | `src/orchestration/rag_pipeline.py` | Retrieval, décomposition, web fallback, gardes Strict RAG, vérification citations | Service enregistré |
| RAGEngine | `src/rag_engine.py` | Index/retrieval sqlite-vec + BM25, format `[SOURCE i]` | Service ; chargement lazy des modèles |
| MultiSearchOrchestrator | `src/rag/multi_search.py` | Stratégies de recherche + RRF, HYDE | Orchestrateur interne |
| Router V16 | `src/routing/v16/router_v16.py` | Routage déterministe N1-N6 (zéro modèle) | Léger, CI-viable |
| Router legacy | `src/routing/router.py` | Spotlight (N4), fallback cloud (N5), cache décision | Service |
| Config | `src/config.py` | Singleton `config`, flags (dont `minimal_pipeline`) | Singleton, YAML surchargeable |
| Benchmark V18-15 | `src/benchmark/` (runner, judge, report) | Orchestration A/B : routage CI + RAG local + juges N1/N2 + rapport JSON | CLI headless |
| SelfEvaluator | `src/learning/self_eval.py` | Juge niveau 2 heuristique (5 dims RAGAS-like, zéro LLM) | Brique importée |
| Session/LTM/Mémoire | `session_store`, `long_term_memory` | Historique conversationnel, faits persistants | Services |
| ActStep | `src/kernel/pipeline_steps.py` | Actions/tools — GATÉ `enable_act_step` (OFF), lazy `src.tools` | Step |

## 3. Frontières à ne pas franchir

- Les steps ne construisent pas le RAG eux-mêmes : ils appellent
  `RAGOrchestrator` via le Kernel.
- `src/benchmark/` ne réimplémente AUCUNE brique : il importe
  `LABELED_SET`/`run_precision` (`src/routing/v16/benchmark.py`) et
  `SelfEvaluator` (`src/learning/self_eval.py`) — AGENTS.md §7.2.
- L'UI (PySide6) n'accède pas directement aux modèles MLX : elle consomme
  les services Kernel (signal `metrics_updated`, etc.).
- `minimal_pipeline` n'existe QUE pour `run.py --benchmark --minimal` ;
  il ne change jamais le fonctionnement normal.

## 4. Dernière vérification

- Date : 2026-08-10
- Vérifié : imports `src/benchmark/runner.py` (SelfEvaluator depuis
  `src.learning.self_eval`, LABELED_SET/run_precision depuis
  `src.routing.v16.benchmark`), services résolus via `_get_service` dans
  `pipeline_steps.py`, singleton `config` dans `src/config.py`.
