# RAPPORT D'AUDIT DES ARTEFACTS LEGACY V4 — PROJET NURU

> Date : 2026-06-20
> Projet : /Users/leblancbahiga/Downloads/Assistant IA/src/
> Architecture : EventBus, PySide6, Python 3.11, M1 8Go

---

## TABLE DES MATIÈRES

1. [Vue d'ensemble — 100 fichiers Python dans src/](#1-vue-densemble)
2. [PluginSystem — stub vide (SUPPRIMÉ)](#2-pluginsystem)
3. [ReflectionEngine — stub vide (SUPPRIMÉ)](#3-reflectionengine)
4. [Les 3 routeurs — analyse de duplication](#4-les-3-routeurs)
5. [Les 4 (5) builds de prompt système](#5-les-4-5-builds-de-prompt)
6. [Imports conditionnels V4](#6-imports-conditionnels-v4)
7. [Dualité V4/V8+ — cartographie complète](#7-dualité-v4v8)
8. [Tests legacy V4](#8-tests-legacy-v4)
9. [Recommandations pour fusionner en UN routeur unique](#9-recommandations)

---

## 1. VUE D'ENSEMBLE

### Liste complète des 100 fichiers Python dans src/

```
src/__init__.py
src/ai/__init__.py
src/ai/archon_refiner.py
src/ai/archon_research.py
src/ai/verifier.py
src/audio.py
src/cache/__init__.py
src/cache/llm_cache.py
src/cli.py
src/cloud.py
src/config.py
src/context_manager.py
src/core/__init__.py
src/core/events.py
src/core/exceptions.py
src/core/inference_worker.py
src/core/model_manager.py
src/core/orchestrator.py
src/core/policies.py
src/core/prompt_guard.py
src/core/query_context.py
src/core/response_guard.py
src/core/router.py
src/cv_extractor.py
src/document_extractor.py
src/document_watcher.py
src/embedder.py
src/extraction.py
src/ingestion.py
src/infra/__init__.py
src/infra/cache.py
src/infra/logging_setup.py
src/learning/__init__.py
src/learning/feedback.py
src/learning/optimizer.py
src/learning/self_eval.py
src/learning/trace_collector.py
src/learning/tracker.py
src/llm_cloud.py
src/llm_local.py
src/long_term_memory.py
src/memory/__init__.py
src/memory/consolidation.py
src/memory/episodic.py
src/memory/errors.py
src/memory/manager.py
src/memory/retriever.py
src/memory/schema.py
src/memory/semantic.py
src/memory/user.py
src/memory_bridge.py
src/memory_store.py
src/nuru_brain.py
src/nuru_core.py
src/observability/__init__.py
src/ocr.py
src/orchestration/__init__.py
src/orchestration/llm_generator.py
src/orchestration/rag_pipeline.py
src/query_rewriter.py
src/rag/__init__.py
src/rag/chunking.py
src/rag/decomposer.py
src/rag/diagnostics.py
src/rag/fact_checker.py
src/rag/file_search.py
src/rag/hyde.py
src/rag/index_health.py
src/rag/multi_search.py
src/rag/query_rewriter.py
src/rag/spotlight.py
src/rag/types.py
src/rag/v2_chunking.py
src/rag_engine.py
src/ram_monitor.py
src/reranker.py
src/research/__init__.py
src/research/optimizer.py
src/research/web.py
src/runtime_manager.py
src/semantic_router.py
src/session/__init__.py
src/session/store.py
src/token_juice.py
src/tools/__init__.py
src/tools/document.py
src/tools/registry.py
src/ui/__init__.py
src/ui/components/agent_status.py
src/ui/components/agent_task_page.py
src/ui/components/architecture_page.py
src/ui/components/chat_bubble.py
src/ui/components/console_page.py
src/ui/components/conversation_list.py
src/ui/components/diagnostics_page.py
src/ui/components/documents_page.py
src/ui/components/feedback_page.py
src/ui/components/kpi_dashboard_page.py
src/ui/components/logs_page.py
src/ui/components/markdown_renderer.py
src/ui/components/memory_explorer.py
src/ui/components/memory_page.py
src/ui/components/mentions_popup.py
src/ui/components/nuru_widgets.py
src/ui/components/performance_memory_page.py
src/ui/components/performance_page.py
src/ui/components/right_panel.py
src/ui/components/sessions_page.py
src/ui/components/settings_page.py
src/ui/components/stat_card.py
src/ui/components/stats_page.py
src/ui/components/task_list.py
src/ui/components/toast.py
src/ui/components/tool_tester.py
src/ui/components/v6_system_page.py
src/ui/dashboard.py
src/ui/overlay.py
src/ui/state/actions.py
src/ui/state/app_state.py
src/ui/viewmodels/__init__.py
src/ui/viewmodels/chat_vm.py
src/ui/viewmodels/rag_diagnostic_vm.py
```

---

## 2. PLUGINSYSTEM — STUB VIDE

### Statut : ✅ DÉJÀ SUPPRIMÉ (Audit V10.3, Arch-01)

| Fichier | Ligne | Artefact | Description | Action |
|---------|-------|----------|-------------|--------|
| `src/nuru_core.py` | 19-21 | Commentaire | "NURU V10.3 — AUDIT-FIX : PluginSystem et ReflectionEngine supprimés (Arch-01). Étaient des stubs legacy (YAGNI)" | ✅ Documenter, garder commentaire |
| `src/nuru_core.py` | 130 | Commentaire | "self.plugins et self.reflection supprimés (stubs YAGNI)" | ✅ Documenter |

**Aucun call site ni import de PluginSystem ne subsiste ailleurs dans le code.**

---

## 3. REFLECTIONENGINE — STUB VIDE

### Statut : ⚠️ SUPPRIMÉ mais TRAÎNE dans NuruOrchestrator

| Fichier | Ligne | Artefact | Description | Action |
|---------|-------|----------|-------------|--------|
| `src/nuru_core.py` | 19-21 | Commentaire | Mentionne la suppression | ✅ Documentation |
| `src/nuru_core.py` | 130 | Commentaire | "self.plugins et self.reflection supprimés" | ✅ Documentation |
| `src/nuru_core.py` | 155-156 | Paramètre | `reflection_engine=None` passé à NuruOrchestrator | ⚠️ Supprimer le paramètre |
| `src/core/orchestrator.py` | 90 | Paramètre | `reflection_engine=None` dans `__init__` | ⚠️ Supprimer le paramètre |
| `src/core/orchestrator.py` | 103 | Stockage | `self.reflection = reflection_engine` | ⚠️ Supprimer |
| `src/core/orchestrator.py` | 411-420 | Bloc mort | `if self.reflection:` avec appel `self.reflection.analyze()` — ne s'exécute JAMAIS car None | 🔴 PORTER : supprimer le bloc (dead code) |

**Risque :** Faible. Le bloc `if self.reflection:` (lignes 411-420) ne s'exécute jamais. Suppression safe.

---

## 4. LES 3 ROUTEURS — ANALYSE DE DUPLICATION

### Routeur A : `src/semantic_router.py` (307 lignes)

| Ligne | Artefact | Description |
|-------|----------|-------------|
| 1-12 | Docstring | "Routeur Sémantique Hybride V10.1 pour NURU" |
| 30-36 | `CLASSIFY_PROMPT` | Prompt de classification LLM |
| 39-47 | `build_classify_prompt()` | Sanitization + template |
| 102-108 | `RouterResult` | Dataclass résultat |
| 112-307 | **`class SemanticRouter`** | Routeur 2-passes (regex → LLM) |
| 130-286 | `route()` | Méthode principale : N0-Cache, N1-Trivial, N2-Patterns, N3-LLM, N4-Spotlight, N5-Cloud, N6-Clarification |
| 288-302 | `_classify_with_llm()` | Classification LLM Groq |
| 304-307 | `route_with_context()` | Wrapper compat orchestrator |

### Routeur B : `src/core/router.py` (105 lignes)

| Ligne | Artefact | Description |
|-------|----------|-------------|
| 1 | Docstring | "Wrapper V4.5 autour de SemanticRouter avec PolicyEngine et stratégies hybrides" |
| 12-33 | `HybridStrategy` | Enum LOCAL_ONLY, LOCAL_CLOUD_VERIFY, CLOUD_PLAN_LOCAL, LOCAL_RAG_CLOUD |
| **37-98** | **`class Router(SemanticRouter)`** | **Héritage de SemanticRouter** |
| 47-54 | `__init__()` | Super().__init__() + PolicyEngine + hybrid_strategy |
| 56-93 | `route_with_context()` | **Override** : RAM escalation + Spotlight bypass + hybrid strategy |
| 95-98 | `set_hybrid_strategy()` | Changement à la volée |
| 101-105 | Patch dynamique | Ajoute `hybrid_strategy` à `RouterResult` (monkey-patch) |

### Routeur C : routing intégré dans `src/nuru_core.py` (435 lignes)

| Ligne | Artefact | Description |
|-------|----------|-------------|
| 9 | Import | `from src.semantic_router import SemanticRouter # V4 : Remplace IntentClassifier` |
| 10 | Import | `from src.core.router import Router # V5 : Routeur with PolicyEngine` |
| 112 | Docstring | "class NuruCore: Orchestrateur asynchrone principal de NURU V4" |
| 118 | Création | `self.router = Router(rag_engine=self.rag, is_online_check=self._is_online, cloud_llm=self.cloud_llm)` |
| 326-361 | `build_system_prompt()` | Prompt système basé sur l'intent (découle du routing) |
| 377-387 | `process_query()` | Délègue à `self.orchestrator.process_query()` |
| 425-434 | `process_query_v45()` | Délègue aussi à `self.orchestrator.process_query()` |
| 179-197 | `_is_online()` | Vérification synchrone multi-provider |
| 199-226 | `_check_cloud_online()` | Vérification asynchrone multi-provider |

### Appel réel du routing dans `src/core/orchestrator.py`

| Ligne | Artefact | Description |
|-------|----------|-------------|
| 206 | `route_result = await self.router.route_with_context(ctx, ...)` | **UN SEUL point d'appel** vers le routeur |
| 208-209 | `ctx.with_route()` + `_route_to_intent()` | Mapping decision → intent |

### BILAN ROUTEURS

```
SemanticRouter (src/semantic_router.py)  ←── classe de base
    ↑ hérite
Router (src/core/router.py)             ←── extension avec PolicyEngine
    ↑ utilisé par
NuruCore (src/nuru_core.py)             ←── conteneur qui instancie Router
    ↑ utilisé par
NuruOrchestrator (src/core/orchestrator.py)  ←── seul appelant réel via .route_with_context()
```

**La duplication est HIÉRARCHIQUE (pas parallèle).** Router étend SemanticRouter. NuruCore les contient. NuruOrchestrator les utilise. Pas de duplication fonctionnelle, mais un couplage inutile entre SemanticRouter (pur routing) et Router (policy).

---

## 5. LES 4 (5) BUILDS DE PROMPT SYSTÈME

### Build 1 : `SYSTEM_PROMPT_STATIC`

| Fichier | Ligne | Description |
|---------|-------|-------------|
| `src/nuru_core.py` | 47-109 | Prompt de base V8+ (~1500 tokens) avec toutes les instructions (connaissances générales, mode RAG strict, mode hybride, traçabilité, incertitude) |

### Build 2 : `NuruCore.build_system_prompt()`

| Fichier | Ligne | Description |
|---------|-------|-------------|
| `src/nuru_core.py` | 326-361 | Assemble SYSTEM_PROMPT_STATIC + intention-specific rules + faits Leblanc + procédures. Utilisé comme callback par NuruOrchestrator (ligne 503-508) |

### Build 3 : `NuruOrchestrator._build_prompt()`

| Fichier | Ligne | Description |
|---------|-------|-------------|
| `src/core/orchestrator.py` | 485-584 | Construit le prompt FINAL complet : système + RAG + query safe + instructions par intent. Inclut sanitization, session context, user_facts block. Utilise ContextBudget.allocate() |

### Build 4 : `ContextBudget._build_prompt()`

| Fichier | Ligne | Description |
|---------|-------|-------------|
| `src/context_manager.py` | 41-64 | Assemble le prompt avec balises <\|system\|>, <\|user\|>, sections RAG, user facts, history. Ancien format hérité. |

### Build 5 : `CLASSIFY_PROMPT` (prompt de classification)

| Fichier | Ligne | Description |
|---------|-------|-------------|
| `src/semantic_router.py` | 30-36 | Prompt de classification LLM (GENERAL/RAG/WEB) avec sanitation |
| `src/semantic_router.py` | 39-47 | `build_classify_prompt()` — wrapper avec sanitization |

### BILAN PROMPTS

```
SYSTEM_PROMPT_STATIC ───────→ build_system_prompt() ─────→ _build_prompt() [orchestrator]
    (template de base)     (ajoute rules + faits)        (assemble prompt final complet)
                                                                ↑
                                                    ContextBudget._build_prompt()
                                                    (formatage avec balises)
```

**Les 4 builds sont ENCHAÎNÉS (pas parallèles).** Mais il y a 2 `_build_prompt()` différents (orchestrator.py + context_manager.py) qui font quasiment la même chose avec des formats différents — duplication réelle.

---

## 6. IMPORTS CONDITIONNELS V4

### Aucun `if something_V4:` trouvé

Pas d'import conditionnel basé sur `V4` dans le projet. Les patterns proches :

| Fichier | Ligne | Pattern | Description |
|---------|-------|---------|-------------|
| `src/nuru_core.py` | 41 | `if "NuruOrchestrator" in dir():` | Guard anti-conflit V4→V8+ (avertit que les deux pipelines cohabitent) |
| `src/semantic_router.py` | 121-125 | `try: from src.rag.spotlight import SpotlightSearch` | Import optionnel de Spotlight |
| `src/semantic_router.py` | 208 | `if self.cloud_llm and self.is_online():` | Check connectivité pour LLM classify |
| `src/core/orchestrator.py` | 231 | `if self.response_guard.is_free:` | Check mode FREE |
| `src/core/router.py` | 101-105 | `if not hasattr(sr.RouterResult, 'hybrid_strategy'):` | Monkey-patch dynamique |

**Aucun import conditionnel V4 legacy. Le guard ligne 41 est le seul vestige de la dualité V4/V8+ explicite.**

---

## 7. DUALITÉ V4/V8+ — CARTOGRAPHIE COMPLÈTE PAR FICHIER

### `src/nuru_core.py` — **18 occurrences V4/V45/V8+**

| Ligne | Balise | Description | Safe à supprimer ? |
|-------|--------|-------------|-------------------|
| 9 | `# V4` | "SemanticRouter remplace IntentClassifier" | Commentaire, safe |
| 10 | `# V5` | "Router avec PolicyEngine" | Commentaire, safe |
| 25 | `# V4` | "RAMMonitor: Monitoring RAM" | Commentaire, safe |
| 26 | `# V4.5` | "DocumentWatcher: Auto-indexation watchdog" | Commentaire, safe |
| 27 | `# V4.5` | "NuruOrchestrator: Nouvel orchestrateur" | Commentaire, safe |
| 28 | `# V4.5` | "PolicyEngine: Moteur de politiques" | Commentaire, safe |
| 29 | `# V4.5` | "PostSessionExtractor: Extraction post-session" | Commentaire, safe |
| 36-45 | `Guard V8+` | "migration V4.5→V8+ en cours" — `if "NuruOrchestrator" in dir()` | 🔴 PORTER : supprimer quand migration finie |
| 47 | `V8+` | "Tu es NURU V8+" dans SYSTEM_PROMPT_STATIC | 🔄 Garder (contenu) |
| 112 | `V4` | "class NuruCore: Orchestrateur asynchrone principal de NURU V4" | ⚠️ Renommer en "V8+" |
| 115 | `# V4` | "Routeur Sémantique Hybride" | Commentaire, safe |
| 133 | `# V4` | "Monitoring RAM actif" | Commentaire, safe |
| 143 | `# V4.5` | "Orchestrateur pipeline" | Commentaire, safe |
| 157 | `# V4.5` | "callback prompt" | Commentaire, safe |
| 159 | `V4.5` | "NuruOrchestrator V4.5 initialisé" | Log, safe |
| 168 | `# V4.5` | "Extracteur post-session" | Commentaire, safe |
| 237 | `# V4.5` | "Document watcher watchdog" | Commentaire, safe |
| 421-426 | `V4.5` | **`process_query_v45()`** — méthode suffixée | 🔴 PORTER : supprimer ou renommer |
| 425 | `V4.5` | "Version V4.5 du pipeline" | Docstring |

### `src/core/orchestrator.py` — **5 occurrences V4.5/V8+**

| Ligne | Balise | Description | Safe ? |
|-------|--------|-------------|--------|
| 1 | `V4.5` | "NURU V4.5 — Orchestrateur asynchrone principal" | ⚠️ Renommer en V8+ |
| 64 | `V4.5` | "NuruOrchestrator: ... pipeline NURU V4.5" | Docstring |
| 90 | `V4.5` | "callback pour construire le prompt système" | Commentaire |
| 118 | `V4.5` | "Long-Term Memory" | Commentaire |
| 278 | `V4.5` | "injection des faits utilisateur Long-Term Memory" | Commentaire |

### `src/core/router.py` — **2 occurrences V4.5**

| Ligne | Balise | Description | Safe ? |
|-------|--------|-------------|--------|
| 1 | `V4.5` | "Wrapper V4.5 autour de SemanticRouter" | ⚠️ Renommer |
| 42 | `V4.5` | "Cache TTL hérité de SemanticRouter V4.5" | Commentaire |

### `src/rag_engine.py` — **7 occurrences V4/V45/V8+**

| Ligne | Balise | Description | Safe ? |
|-------|--------|-------------|--------|
| 100 | `V8+` | "RAGDiagnostic sérialisé" | Commentaire |
| 101 | `V8+` | "HAUTE / MOYENNE / FAIBLE / ABSENT" | Commentaire |
| 112 | `V4` | "Reranker sémantique" | Commentaire |
| 116 | `V4.5` | "seuils configurés pour reranker conditionnel" | Commentaire |
| 356 | `V4` | "compatible V4" | Commentaire |
| 615 | `V4` | "Recherche hybride avec confidence gate dynamique V4" | Docstring |
| 630 | `V8+` | "Diagnostic RAG temps réel" | Commentaire |
| 639 | `V8+` | "MultiSearch orchestrateur" | Commentaire |
| 752-760 | `V4.5` | "Reranker CONDITIONNEL", "FIX PyTorch/MLX Conflict" | Commentaires |
| 890 | `V4.5` | "top_k réduit de 30 à 15" | Commentaire |

### `src/ingestion.py` — **4 occurrences V4/V45/V6**

| Ligne | Balise | Description | Safe ? |
|-------|--------|-------------|--------|
| 17-19 | `V4` | "Moteur d'ingestion de documents pour le RAG V4" | Docstring |
| 103 | `V4.5` | "Chunking sémantique contextuel" | Commentaire |
| 168 | `V4` | "Boucle d'auto-indexation V4" | Docstring |
| 176 | `V4` | "Scan auto-indexation V4 démarré..." | Log |

### `src/reranker.py`

| Ligne | Balise | Description | Safe ? |
|-------|--------|-------------|--------|
| 2 | `V4` | "Reranker 2 étages pour NURU V4." | Docstring, safe |

### `src/core/policies.py`

| Ligne | Balise | Description | Safe ? |
|-------|--------|-------------|--------|
| 1 | `V4.5` | "Moteur de politiques de décision pour NURU V4.5" | Docstring, safe |

### `src/core/events.py`

| Ligne | Balise | Description | Safe ? |
|-------|--------|-------------|--------|
| 1 | `V4.5` | "Bus d'événements unifié pour NURU V4.5." | Docstring |

### `src/core/query_context.py`

| Ligne | Balise | Description | Safe ? |
|-------|--------|-------------|--------|
| 1 | `V4.5` | "Conteneurs de données immutables pour le pipeline NURU V4.5." | Docstring |
| 17-20 | `V8+` | "Sprint 5 : already_retried, already_fact_checked" | Commentaire |
| 28 | `V8+` | "Sprint 5 : Guards anti-boucle" | Commentaire |

### `src/document_watcher.py`

| Ligne | Balise | Description | Safe ? |
|-------|--------|-------------|--------|
| 1 | `V4.5/V5` | "Document watcher pour auto-indexation temps réel (V4.5/V5)" | Docstring |

### `src/rag/__init__.py`

| Ligne | Balise | Description | Safe ? |
|-------|--------|-------------|--------|
| 1 | `V4.5` | "NURU V4.5 — Pipeline RAG" | Docstring |

### `src/infra/logging_setup.py`

| Ligne | Balise | Description | Safe ? |
|-------|--------|-------------|--------|
| 1 | `V4.5` | "Configuration des logs structurés avec loguru pour NURU V4.5" | Docstring |

### `src/llm_local.py`

| Ligne | Balise | Description | Safe ? |
|-------|--------|-------------|--------|
| 10 | `V4.5` | "ModelManager: Gestion RAM centralisée" | Commentaire |
| 25 | `V4.5` | "Délégation au ModelManager" | Commentaire |

### `src/memory_store.py` — **4 occurrences V8+**

| Ligne | Balise | Description | Safe ? |
|-------|--------|-------------|--------|
| 117 | `V8+` | "Retourne (response, diagnostic) si trouvé" | Commentaire |
| 144 | `V8+` | "Tenter de parser le diagnostic embarqué" | Commentaire |
| 160 | `V8+` | "Stocke le diagnostic embarqué" | Commentaire |
| 164 | `V8+` | "Embarquer le diagnostic dans la réponse" | Commentaire |

---

## 8. TESTS LEGACY V4

| Fichier | Lignes | Description |
|---------|--------|-------------|
| `tests/test_v4_integration.py` | 114 | Test d'intégration V4 : SemanticRouter + RAGEngine + Reranker + RAMMonitor |
| `tests/test_v45_modules.py` | 668 | Tests unitaires V4.5 : PolicyEngine, QueryContext, EvidencePack, RRF, Cache... |
| `tests/test_semantic_router.py` | — | Test du routeur sémantique |

---

## 9. RECOMMANDATIONS POUR FUSIONNER EN UN ROUTEUR UNIQUE

### Problème identifié

```
ACTUEL :
  SemanticRouter (src/semantic_router.py)       ← routing pur (cache + patterns + LLM)
      ↑ héritage
  Router (src/core/router.py)                   ← PolicyEngine + hybrid strategy
      ↑ instanciation dans
  NuruCore (src/nuru_core.py)                   ← conteneur
      ↑ délégation
  NuruOrchestrator (src/core/orchestrator.py)   ← seul appelant via .route_with_context()
```

### Solution recommandée : UN SEUL ROUTEUR

**Fusionner SemanticRouter + Router en un seul fichier :**

| Action | Détail |
|--------|--------|
| 📦 Créer | `src/routing/` nouveau package |
| 📦 Déplacer | `SemanticRouter` + `RouterResult` + `HybridStrategy` dans `src/routing/router.py` |
| ♻️ Fusionner | Les 2 `route_with_context()` en une seule méthode dans la classe fusionnée |
| 🧹 Supprimer | `src/semantic_router.py` (307 lignes) |
| 🧹 Supprimer | `src/core/router.py` (105 lignes) |
| 🔗 Mettre à jour | Les imports dans `nuru_core.py`, `orchestrator.py`, `rag_pipeline.py`, `tests/` |

**Schéma cible :**
```
src/routing/
├── __init__.py          # exporte Router, RouterResult, HybridStrategy
├── router.py            # class Router (fusionné)
├── router_result.py     # RouterResult dataclass + HybridStrategy enum
├── patterns.py          # TRIVIAL_PATTERNS, RAG_KEYWORDS, GENERAL_KNOWLEDGE_PATTERNS, WEB_SEARCH_PATTERNS
└── classify.py          # CLASSIFY_PROMPT + build_classify_prompt()
```

---

## RÉSUMÉ DES ACTIONS PRIORITAIRES

| # | Action | Fichiers impactés | Risque | Effort |
|---|--------|-------------------|--------|--------|
| 1 | 🔴 Supprimer le bloc `if self.reflection:` (dead code) | `src/core/orchestrator.py:411-420` | Faible | 5 min |
| 2 | 🔴 Supprimer `process_query_v45()` (duplication de `process_query()`) | `src/nuru_core.py:425-434`, `src/core/inference_worker.py:56` | Moyen | 30 min |
| 3 | 🟡 Supprimer paramètre `reflection_engine` de NuruOrchestrator | `src/core/orchestrator.py:90,103`, `src/nuru_core.py:155-156` | Faible | 10 min |
| 4 | 🟡 Fusionner SemanticRouter + Router → `src/routing/` | 3 fichiers supprimés, 3 créés | Moyen | 2h |
| 5 | 🟡 Supprimer guard `if "NuruOrchestrator" in dir():` | `src/nuru_core.py:41-45` | Faible | 5 min |
| 6 | 🟢 Renommer docstrings V4/V4.5 → V8+ dans 15 fichiers | Multiples fichiers | Faible | 30 min |
| 7 | 🟢 Supprimer `tests/test_v4_integration.py` (obsolète) | `tests/test_v4_integration.py` | Faible | 5 min |
| 8 | 🔵 Fusionner les 2 `_build_prompt()` (orchestrator.py + context_manager.py) | `src/core/orchestrator.py:485`, `src/context_manager.py:41` | Moyen | 1h |

---

*Fin du rapport.*
