# CHECKLIST V18 — SOURCE DE VÉRITÉ DU DÉVELOPPEMENT

> Créée le 8 août 2026 · Conforme au prompt officiel d'implémentation V18.
> Statuts : ⏸️ = à faire · 🔄 = en cours · ✅ = implémenté + tests OK · 🚫 = bloqué (rapport)
> Légende snippets : R4 = SNIPPETS_V18_ROUND4.md · R5 = SNIPPETS_V18_ROUND5.md

## PLAN D'IMPLÉMENTATION (5 phases — respect des dépendances)

| Phase | Contenu | Décisions |
|---|---|---|
| 1 — P0 | Freeze UI + surveillance RAM | V18-40, V18-37 |
| 2 — Quick Wins | Fix prompts + blocages visibles | V18-13, V18-24, V18-31, V18-35 |
| 3 — Cœur | RAM + RAG + pipeline (blocs A-F) | V18-36, V18-27, V18-04, V18-03, V18-08, V18-01, V18-23, V18-02, V18-14, V18-05, V18-16, V18-17, V18-06, V18-25, V18-20, V18-07, V18-12, V18-15, V18-18, V18-19, V18-22, V18-26, V18-28, V18-38, V18-39, V18-33, V18-34a, V18-34b, V18-41 |
| 4 — V18.1 | Gel + reports | V18-09, V18-10, V18-11, V18-21, V18-29, V18-30, V18-32 |
| 5 — V19 | Nettoyage code mort (~40 k lignes) | — (hors V18) |

## J1 du sprint corrigé (référence contrat) : V18-13 → V18-24 (a)(b)
## Juge de paix final : V18-41 (4 cibles benchmark)

---

## DÉCISIONS

| # | Décision | Statut | Dépend de | Fichiers | Tests | Snippet |
|---|---|---|---|---|---|---|
| V18-01 | Reranker MLX natif direct (étape (a) supprimée) | ⏸️ | 03, 36 | src/reranker.py, src/rag_engine.py:999 (blend), src/config.py | benchmark RAG | — |
| V18-02 | État RAG typé `has_valid_evidence` | ⏸️ | — (bloque 31) | src/kernel/pipeline_steps.py, src/rag_engine.py, context_manager.py (7 fichiers/17 sites) | tests migration couche | — |
| V18-03 | Registre RAM unifié (3 sites → 1) | ⏸️ | — | src/nuru_core.py:207-209, src/rag_engine.py:36-39, src/routing/router.py | pytest RAM | — |
| V18-04 | should_force_cloud (3 conditions) | ⏸️ | 03, 36 | src/core/ram_budget.py:372-385 | pytest RAM | — |
| V18-05 | Supprimer `_maybe_unload_embedder` callback | ⏸️ | **16** (bloquant) | src/nuru_core.py:414 | pytest RAM | — |
| V18-06 | Gate CloudQueryRewriter (enum résolu) | ⏸️ | 25 | src/rag/query_rewriter.py:114-177 | test_router | — |
| V18-07 | Visibilité : logger ctx.step_timings + model= | ⏸️ | — | src/kernel/pipeline.py:235-280 | — | — |
| V18-08 | peak_mb mesuré (warm-up, Metal, ctx 2048) | ⏸️ | 03, 36 | src/core/ram_budget.py:59 | pytest RAM | — |
| V18-09 | Step Act optionnel gaté | ⏸️ V18.1 | — | src/kernel/pipeline_steps.py, src/tools/ | — | R4 Q6 |
| V18-10 | Unification MCP ↔ ToolRegistry | ⏸️ V18.1 | 09 | src/kernel/mcp_server.py | — | — |
| V18-11 | Toggle UI AgentOrchestrator | ⏸️ V18.1 | — | src/ui/, src/core/orchestrator.py:240-243 | — | — |
| V18-12 | Réévaluer Phi-4 vs Qwen3 (après 01+02) | ⏸️ | 01, 02 | src/config.py | benchmark | — |
| V18-13 | Nettoyer template (règle 4 l.74-75 + l.85/90) | ✅ `295c064` | — (**bloque 24**) | src/nuru_core.py:56-92 (SYSTEM_PROMPT_TEMPLATE) | — | R4 Q1 préreq |
| V18-14 | FSM pilotée par état typé | ⏸️ | 02 | src/kernel/pipeline_steps.py | test_pipeline | — |
| V18-15 | Benchmark 40 cas + SelfEvaluator + CI | ⏸️ | — | benchmark/ (nouveau), pyproject.toml | benchmark | — |
| V18-16 | locked_by_pipeline (protection) | ⏸️ | — | src/core/ram_budget.py | pytest RAM | — |
| V18-17 | Éviction différée 60 s si _generating | ⏸️ | 16 | src/core/ram_budget.py | pytest RAM | — |
| V18-18 | SQLite WAL + timeouts + lock | ⏸️ | — | src/rag_engine.py, trace/session stores | pytest | — |
| V18-19 | Alerte UI mode dégradé vec0 (numpy) | ⏸️ | — | src/ (find `_has_vec0`), src/ui/ | — | — |
| V18-20 | Gate N3 enum (raffiné) | ⏸️ | 25 | src/kernel/pipeline.py:51 | test_router | — |
| V18-21 | Geler modules morts (KG/Proactive/MCP) + session_memory + PolicyEngine | ⏸️ V18.1 | — | src/nuru_core.py:30-41,273-284,331-332,220 | pytest boot | R4 Q6, R5 Q4/Q5 |
| V18-22 | Alias LocalLLM.stop → close | ⏸️ | — | src/core/llm_local.py:530 | pytest | — |
| V18-23 | Seuils unifiés (0.0 → 0.30) | ⏸️ | **01** (ordre) | src/reranker.py:28, src/config.py:64 | benchmark | — |
| V18-24 | Rebrancher system_prompt_builder | ✅ `9eab913` | **13** (bloquant) | src/kernel/pipeline_steps.py:375 | A/B id=941 (après 02+04/27) | **R4 Q1 ✅** |
| V18-25 | Enum HybridStrategy (3 modes) | ⏸️ | — | src/core/router.py:112, 5 points chaîne | test_router | R4 Q3 |
| V18-26 | Lifecycle adaptatif stop/close/cleanup/unload | ⏸️ | — | src/core/registry.py:145-157 | pytest | — |
| V18-27 | Budget MLX dynamique + OOM→cloud | ⏸️ | 03, 36 | src/core/ram_budget.py:203,372-385, src/core/llm_local.py:437-439 | pytest RAM | **R4 Q2 ✅** |
| V18-28 | Retirer UI « TokenJuice ACTIF » (menteur) | ⏸️ | — | src/ui/overlay.py:129,181 | — | — |
| V18-29 | Supprimer RAMMonitor (déjà mort) | ⏸️ V18.1 | — | src/ram_monitor.py, src/nuru_core.py:198,450-451 | pytest boot | R4 Q4 |
| V18-30 | Pool connexions SQLite (P1) | ⏸️ P1 | — | src/rag_engine.py:385 | — | — |
| V18-31 | Fast-Fail RAG vide (étendre check_strict_blocks) | ⏸️ | **02** | src/rag/rag_pipeline.py:266, context_manager.py:50-52 | test_pipeline | **R4 Q5 ✅ + R5 Q3 ✅** |
| V18-32 | keep_alive conditionnel (30 s si thrash fixé, sinon 120 s) | ⏸️ Phase 4 | 01 | src/core/llm_local.py (keep_alive), src/config.py | — | — |
| V18-33 | Réactiver tests désélectionnés (méthode) | ⏸️ P1 | 15 | pyproject.toml:89, tests/ | pytest | R4 Q7 |
| V18-34a | Truncation chunk par chunk `[SOURCE ` | ⏸️ P1 | — | src/context_manager.py:24-32 (→ _truncate_by_chunks) | pytest | **R5 Q1 ✅** |
| V18-34b | Format citation `[SOURCE i]` aligné | ⏸️ P1 (après a) | 34a | src/prompt_builder.py:160 | pytest | **R5 Q1 ✅** |
| V18-35 | Ne PAS démarrer KernelScheduler (doc seule) | ⏸️ | — | src/nuru_core.py:156-157 (commentaire) | — | **R5 Q2 (révisé)** |
| V18-36 | Plafond RAM dynamique (le plus restrictif) | ⏸️ | — | src/core/ram_budget.py (hard_limit_gb, 8 occ.) | pytest RAM | — |
| V18-37 | start_monitoring : erreur + relance | ⏸️ | — | src/core/ram_budget.py:137-146 | pytest RAM | — |
| V18-38 | deepcopy métadonnées avant émission Qt | ⏸️ | — | src/core/conversation_engine.py:340,365 | pytest | — |
| V18-39 | session_memory gelé (source = session_store) | ⏸️ | 21 | src/core/orchestrator.py:183-184,804 | — | R5 Q4 |
| V18-40 | SQLite sync → asyncio.to_thread (P0) | ⏸️ **P0** | 18 | src/rag_engine.py:781 (retrieve), rag_pipeline.py:67,140 | test freeze UI | — |
| V18-41 | Contrat de performance (4 cibles) | ⏸️ juge paix | 15, 02, 27 | benchmark/ | benchmark final | — |

---

## ORDRE DE TRAITEMENT PROPOSÉ (respectant dépendances + sprint corrigé)

1. **V18-13** (nettoyage template) — prérequis bloquant de V18-24 → J1
2. **V18-24** (rebranchement prompt) — snippet R4 Q1 ✅ → J1
3. **V18-40** (to_thread, P0 freeze UI)
4. **V18-37** (start_monitoring non silencieux)
5. **V18-35** (doc scheduler — quick win)
6. **V18-36** (plafond dynamique) → 7. **V18-27** (budget MLX, snippet R4 Q2 ✅) → 8. **V18-04** (should_force_cloud 3 cond.)
9. **V18-03** (registre unifié) → 10. **V18-08** (peak_mb mesuré)
11. **V18-16** (locked_by_pipeline) → 12. **V18-17** (éviction 60 s) → 13. **V18-05** (suppression callback)
14. **V18-25** (enum, snippet R4 Q3) → 15. **V18-06** (gate rewriter) → 16. **V18-20** (gate N3)
17. **V18-02** (état typé) → 18. **V18-31** (Fast-Fail, snippets R4 Q5 + R5 Q3 ✅) → 19. **V18-14** (FSM)
20. **V18-01** (reranker MLX) → 21. **V18-23** (seuils 0.30)
22. **V18-18** (WAL/timeouts) → 23. **V18-22** (stop→close) → 24. **V18-26** (lifecycle)
25. **V18-38** (deepcopy) → 26. **V18-39** (session_memory gelé)
27. **V18-28** (UI TokenJuice) → 28. **V18-07** (logs)
29. **V18-15** (benchmark) → 30. **V18-33** (tests) → 31. **V18-34a** → 32. **V18-34b** (snippets R5 ✅)
33. **V18-12** (réévaluer modèle) → 34. **V18-41** (benchmark final = juge de paix)
35. V18.1 : **V18-21** (gel), **V18-29** (RAMMonitor), **V18-09/10/11**, **V18-30**, **V18-32**

---

## SUIVI DES COMMITS

| Décision | Commit | Fichiers | Tests | Date |
|---|---|---|---|---|
| V18-13 | `295c064` | src/nuru_core.py (template) | py_compile | 2026-08-08 |
| V18-24 | `9eab913` | src/nuru_core.py, src/kernel/pipeline_steps.py | py_compile + 157 pytest | 2026-08-08 |
