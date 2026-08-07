# Audit NURU — Synthèse Multi-Expert

**Projet :** NURU (Assistant IA local, M1 8 Go RAM)
**Objet :** Audit du branchement Kernel ↔ Applications
**Source :** Rapports soumis séquentiellement par l'utilisateur

---

## Structure

| Section | Contenu |
|---------|---------|
| `#N — Rapport` | Chaque rapport d'audit, ses findings, son verdict |
| `📊 Tableau récapitulatif` | Consolidation finale après tous les rapports |
| `🎯 Correctifs appliqués` | Suivi des corrections par priorité |

---

## Rapport #1 — Audit d'intégration du Kernel NURU (2026-07-23)

**Source :** `audit_kernel.md` (916 lignes)
**Approche :** Analyse statique du code source concaténé
**Verdict global :** « Kernel beau moteur, mais tourne à vide » — intégration estimée à **20 %**

---

### Score

| Catégorie | Note | Détail |
|-----------|:----:|--------|
| Architecture Kernel | ✅ Solide | ServiceRegistry, cycle de vie, singleton propre |
| Intégration Kernel ↔ App | ❌ 20 % | 2/28 services réellement utilisés |
| Qualité du code | ⚠️ Correct | Héritage V12-V15 encore dominant |
| Robustesse (exceptions) | ❌ Critique | Exceptions LLM non capturées → chat muet |
| Consommation RAM | ❌ Critique | Fuites Qt, ThreadPoolExecutor, double cache |
| Connexions UI → Kernel | ❌ 0 % | Pages créées avant que le Kernel soit prêt |

---

### Findings

**Légende :** ✅ ALREADY_FIXED | ✅ FIXED | ❌ CONFIRMED | ⏭️ NOT_APPLICABLE | ⚠️ DISPUTED | 🟡 PARTIALLY TRUE

#### 🔴 Critiques (5)

| ID | Finding | Fichiers | Verdict | Action |
|----|---------|----------|---------|--------|
| **C1** | **Chat muet** — `RuntimeError` de `LocalLLM.generate_stream` non capturée dans `process_query` ni `ConversationEngine._process` | `orchestrator.py`, `conversation_engine.py`, `llm_local.py` | ❌ CONFIRMED | Capturer `Exception` partout + toujours émettre un signal |
| **C2** | **Documents « module non disponible »** — `LegacyDocsPage` instancié avant que `RAGEngine` soit prêt | `src/ui/pages/documents_page.py`, `src/ui/components/documents_page.py` | ❌ CONFIRMED | Rendre tolérant à `None` ou attendre `engine_ready` |
| **C3** | **Fuite RAM Qt** — `QTimer` jamais arrêtés dans `StatsPage`, `KpiDashboardPage`, `PerformancePage` | Stats, KPI, Performance pages | ❌ CONFIRMED | Ajouter destructeurs / `closeEvent` |
| **C4** | **Fuite RAM ThreadPoolExecutor** — `LocalLLM._mlx_executor` jamais fermé | `llm_local.py` (close jamais appelée) | ❌ CONFIRMED | Appeler `close()` dans `NuruCore.shutdown` |
| **C5** | **Double cache** — `KernelCache` + `LLMCache` coexistent sans synchronisation | `kernel/cache.py`, `cache/llm_cache.py` | ❌ CONFIRMED | Unifier (garder 1 des 2) |

#### 🟡 Majeures (7)

| ID | Finding | Fichiers | Verdict | Action |
|----|---------|----------|---------|--------|
| **M1** | **Dashboard non alimenté** — setters `set_memory_store` / `set_rag_engine` jamais appelés | `app.py`, `main_window.py`, `dashboard_page.py` | ❌ CONFIRMED | Injection des services dans `MainWindow._register_default_pages` |
| **M2** | **Panneau droit incohérent** — `psutil` au lieu de `KernelMetrics` | `right_inspector.py` | ❌ CONFIRMED | Remplacer par `kernel.get('metrics').collect()` |
| **M3** | **Agents vides** — `proactive_engine` pas prêt au chargement de la page | `agents_page.py` | ❌ CONFIRMED | Attendre signal `engine_ready` |
| **M4** | **Outils vides** — `mcp_server` / `mcp_client` None | `tools_page.py` | ❌ CONFIRMED | Idem M3 |
| **M5** | **Mémoire inaccessible** — `memory_store` jamais rafraîchi après disponibilité | `memory_page.py` | ❌ CONFIRMED | Connecter signal de disponibilité |
| **M6** | **Modèles — sélection impossible** — liste codée en dur, pas connectée à `ModelRouter` | `models_page.py` | ❌ CONFIRMED | Générer dynamiquement depuis `ModelRouter.routes` |
| **M7** | **Scheduler inactif** — `KernelScheduler.start()` jamais appelé | `nuru_core.py`, `scheduler.py` | ❌ CONFIRMED | Appeler `start()` + migrer les tâches |

#### 🟢 Architecturales (5)

| ID | Finding | Fichiers | Verdict | Action |
|----|---------|----------|---------|--------|
| **A1** | `get_budget()` → `kernel.get('resources')` | `rag_engine.py`, `llm_local.py`, etc. | ❌ CONFIRMED | Remplacer tous les appels |
| **A2** | Deux routeurs (V12 + KernelRouter V16) | `routing/`, `kernel/router.py` | ❌ CONFIRMED | Conserver un seul |
| **A3** | PipelineEngine jamais utilisé | `conversation_engine.py`, `kernel/pipeline.py` | ❌ CONFIRMED | Remplacer `process_query` par `pipeline.run` |
| **A4** | Embedder non enregistré dans le Kernel | `nuru_core.py`, `embedder.py` | ❌ CONFIRMED | Enregistrer + injecter partout |
| **A5** | `NuruCore` crée tout lui-même (pas d'IoC) | `nuru_core.py` | ❌ CONFIRMED | Refactor majeure : recevoir les services |

---

### Correctifs proposés uniques par ce rapport

1. **Unifier les caches** (garder `LLMCache`, supprimer `KernelCache`)
2. **PipelineEngine** comme remplacement de `orchestrator.process_query`
3. **Signal `engine_ready`** dans `ConversationEngine` pour toutes les pages UI
4. **Injection de dépendances** via Kernel (remplacer singletons)

---

### Plan en 3 phases

| Phase | Délai | Contenu |
|-------|-------|---------|
| 🔴 Phase 0 | Urgence (48h) | C1+C2+C3+C4 (chat, documents, fuites RAM) |
| 🟡 Phase 1 | 1 semaine | M1-M7 (dashboard, panneau droit, agents, outils, scheduler) |
| 🟢 Phase 2 | 1 mois | A1-A5 (refactor architecturale, injection DI) |

---

*Prochain audit à venir...*

---

## Rapport #2 — Audit Technique Complet (2026-07-23)

**Source :** `audit_kernel1.md` (1860 lignes)
**Approche :** Analyse statique du code source concaténé + traçage des attributs `engine.xxx`
**Verdict global :** « Kernel structurellement présent mais fonctionnellement vide » — 4 problèmes fondamentaux identifiés

---

### Score

| Catégorie | Note | Détail |
|-----------|:----:|--------|
| Architecture Kernel | ⚠️ Problèmes structurels | Singleton mais pas point d'entrée ; cycle de vie cassé |
| Couverture des enregistrements | ❌ 50 % | 28/42 services enregistrés |
| Robustesse (exceptions) | ❌ Critique | Idem R#1 — exceptions non capturées |
| Consommation RAM | ❌ Critique | ~5.9 Go estimés avec composants inutiles |
| Noms d'attributs `engine.xxx` | ❌ **5 erreurs de nom** | `memory_store`, `proactive_engine`, `rag_engine._ingestion` inexistants |

---

### Nouveaux findings (non couverts par R#1)

#### 🔴 Critiques spécifiques au R#2

| ID | Finding | Fichiers | Nouveauté |
|----|---------|----------|-----------|
| **C2b** | **Documents — `ingestion_engine` mal extrait** : `rag_engine._ingestion` n'existe PAS. L'ingestion est dans `engine.ingestion`, pas dans RAGEngine. | `documents_page.py` | ✅ Nouveau — R#1 n'avait pas identifié la cause racine exacte |
| **C4** | **`engine.memory_store` n'existe pas** → MemoryPage vide. L'attribut est `engine.memory`. | `memory_page.py` | ✅ **Nouveau** — R#1 n'avait pas vu le mauvais nom |
| **C6** | **RAMMonitor obsolète** — tourne en double avec RAMBudgetManager. ~30-50 Mo inutiles + timer 5s. | `ram_monitor.py`, `nuru_core.py` | ✅ **Nouveau** — R#1 ne mentionnait pas RAMMonitor |
| **C7** | **KernelMetrics ne démarre jamais** — `boot()` appelé avant que la boucle asyncio soit active. `start()` log warning et abandonne. Timer 5s vide. ~50 Mo. | `kernel/metrics.py`, `nuru_core.py` | ✅ **Nouveau** — cause de l'échec de démarrage identifiée |
| **C8** | **KernelCache jamais utilisé** — 5 régions configurées (750 Mo potentiels), zéro accès métier. | `kernel/cache.py` | ✅ **Nouveau** — R#1 suggérait unifier, R#2 propose supprimer |

**Note** : C1 (chat muet), C2 (documents), C3 (fuites Qt), C5 (double cache), M1-M7 sont confirmés par les deux rapports.

#### 🟡 Majeures spécifiques au R#2

| ID | Finding | Nouveauté |
|----|---------|-----------|
| **M3b** | **`engine.proactive_engine` n'existe pas** — l'attribut est `engine.proactive` | ✅ Nouveau (cause racine précise) |
| **M7b** | **KernelScheduler.start() n'a pas de boucle** — juste un flag, pas de `_run()` ou `create_task()` | ✅ Nouveau |
| **M8** | **15+ composants non enregistrés** : MCPServer, MCPClient, TraceCollector, ArchonRefiner, ResearchArchon, EvidenceVerifier, StrictRAGGuard, FeedbackCollector, PerformanceTracker, SelfEvaluator, StrategyOptimizer | ✅ Nouveau |
| **M9** | **KernelMetrics.start() échoue** — asyncio.get_running_loop() avant que la loop soit active | ✅ Nouveau |

#### 🟢 Architecturales spécifiques au R#2

| ID | Finding | Nouveauté |
|----|---------|-----------|
| **A6** | **Kernel singleton mais pas point d'entrée** — NuruCore crée les services AVANT de les enregistrer. IoC violé. | ✅ Nouveau |
| **A7** | **Propriétés typées du Kernel inutilisées** — `kernel.router`, `kernel.rag_engine` (retournent Any, jamais appelées) | ✅ Nouveau |
| **A8** | **Cycle de vie cassé** — `boot()` appelé depuis le thread principal, pas le thread asyncio | ✅ Nouveau |
| **A9** | **Dépendance circulaire implicite** — KernelResources importe get_budget() (singleton global) | ✅ Nouveau |
| **A10** | **PipelineEngine jamais appelé** — flux réel passe par NuruOrchestrator, pas par les steps | ✅ Nouveau |

---

### Convergences et divergences entre R#1 et R#2

| Sujet | R#1 | R#2 | Consensus |
|-------|-----|-----|-----------|
| Chat muet (C1) | ❌ Confirmé | ❌ Confirmé | ✅ **Consensus total** |
| Documents (C2) | ❌ Confirmé | ❌ Cause racine précise : `_ingestion` inexistant | ✅ **Consensus** + détail |
| Mémoire (C4) | ❌ Confirmé | ❌ Cause racine : mauvais nom d'attribut | ✅ **Consensus** + détail |
| Double cache (C5) | Unifier (garder LLMCache) | Supprimer KernelCache | ⚠️ **Approche différente** |
| KernelMetrics | Réutiliser via Kernel | Supprimer (inutilisé) | ⚠️ **Divergence** |
| KernelScheduler | Démarrer `start()` | Supprimer (utiliser create_task) | ⚠️ **Divergence** |
| Noms d'attributs | Non détaillé | **5 erreurs identifiées** | ✅ Complémentaire |
| RAMMonitor | Non mentionné | Supprimer (obsolète) | ✅ Nouveau |
| PipelineEngine | Utiliser (remplacer process_query) | Constat : jamais appelé | ✅ **Consensus sur le constat** |

---

### Plan de correction consolidé (R#1 + R#2)

#### 🔴 P0 — Correctifs immédiats (convergence totale)

| ID | Correction | Fichiers | Temps |
|----|-----------|----------|-------|
| C1 | Capturer `Exception` dans `process_query` + `_process` + émettre erreur UI | `orchestrator.py`, `conversation_engine.py`, `llm_generator.py` | 30 min |
| C2+C2b | Corriger `DocumentsPage` : `engine.ingestion` au lieu de `rag_engine._ingestion` | `documents_page.py` | 15 min |
| C4 | Corriger `MemoryPage` : `engine.memory` au lieu de `engine.memory_store` | `memory_page.py` | 10 min |
| C6 | Supprimer RAMMonitor (obsolète, remplacé par RAMBudgetManager) | `ram_monitor.py`, `nuru_core.py` | 20 min |

#### 🟡 P1 — Correctifs RAM + connexions

| ID | Correction | Temps |
|----|-----------|-------|
| C3 | Arrêter QTimer dans destructeurs des pages stats/performance/KPI | 30 min |
| C4 | Appeler `LocalLLM.close()` dans NuruCore.shutdown | 10 min |
| C8 | Supprimer KernelCache (inutilisé) | 15 min |
| M3b | Corriger `AgentsPage` : `engine.proactive` au lieu de `engine.proactive_engine` | 10 min |
| M8 | Enregistrer les 15+ composants manquants dans le Kernel | 30 min |

#### 🟢 P2 — Architecturales

| ID | Correction | Temps |
|----|-----------|-------|
| M7 | Démarrer KernelScheduler ou le supprimer (décision à prendre) | 1h |
| M2 | Remplacer psutil par KernelMetrics dans l'Inspector | 1h |
| M1 | Injecter services dans le Dashboard via Kernel | 1h |
| A1-A10 | Refactor IoC : Kernel créateur de services | 1-2 jours |

---

### Correctifs proposés uniques par ce rapport

1. **Supprimer RAMMonitor** (obsolète, ~30-50 Mo) — non mentionné par R#1
2. **Supprimer KernelCache** (inutilisé, ~750 Mo théoriques) — R#1 suggérait unifier
3. **Corriger 5 noms d'attributs `engine.xxx`** erronés : `memory_store`→`memory`, `proactive_engine`→`proactive`, `rag_engine._ingestion`→`engine.ingestion`
4. **Enregistrer 15+ composants manquants** (MCPServer, ArchonRefiner, etc.) dans le Kernel
5. **Supprimer les propriétés typées inutiles** du Kernel (`kernel.router`, etc.)

---

*Fin des deux rapports. Consolidation et correctifs en attente de validation.*

---

## Rapport #3 — Audit Architectural Complet (2026-07-23)

**Source :** `audit_kernel2.md` (3289 lignes)
**Structure :** 5 sous-audits (N°1 Architecture, N°2 Flux Chat, N°3 UI Modules, N°4 Cache/Scheduler/Metrics, N°5 Cartographie + Plan)
**Approche :** Analyse architecturale transverse — ne donne pas de bugs ligne par ligne mais des patterns structurels
**Verdict global :** « Le problème n'est pas la qualité du code, c'est la migration inachevée vers le Kernel »

---

### Score

| Catégorie | Note | Détail |
|-----------|:----:|--------|
| Architecture Kernel (conception) | ✅ 9/10 | Pipeline, Registry, Cache, Scheduler bien conçus |
| Intégration Kernel ↔ App | ❌ **20 %** | 3 orchestrateurs coexistent |
| Unicité des services | ❌ **Double instances** | Memory, Router, Scheduler, Cache: ×2 partout |
| EventBus centralisé | ❌ Contourné | Communication directe entre modules |
| Pipeline unique | ❌ 3 pipelines | ConversationEngine → NuruCore → Kernel Pipeline |
| Cycle de vie | ❌ Cassé | UI créée AVANT que le Kernel soit prêt |
| Recommandation vs R#1/R#2 | ⚠️ **Ne pas fixer les bugs → refondre l'architecture** |

---

### Nouveaux findings (non couverts par R#1 ni R#2)

#### 🔴 Critiques (cause racine identifiée par R#3)

| ID | Finding | Impact | Nouveauté |
|----|---------|--------|-----------|
| **R3-C1** | **3 orchestrateurs coexistent** : ConversationEngine, NuruCore, Kernel Pipeline. Aucun n'est la source de vérité. | État `THINKING` persistant, réponses perdues, événements non propagés | ✅ **Nouveau** — diagnostic le plus profond |
| **R3-C2** | **Double instances de TOUS les services** : Memory A (dans ConversationEngine) vs Memory B (dans Kernel). Idem pour Router, Scheduler, Cache, Metrics. | Dashboard lit A, Chat écrit B → menus vides, données incohérentes | ✅ **Nouveau** — explique TOUS les symptômes simultanément |
| **R3-C3** | **EventBus contourné** : les modules communiquent directement (Qt signals, callbacks) au lieu de passer par l'EventBus central. | Événements émis dans un sous-système jamais consommés ailleurs | ✅ **Nouveau** |
| **R3-C4** | **Démarrage inversé** : UI créée AVANT que le Kernel soit prêt. L'ordre devrait être Kernel → Services → UI. | Pages avec `engine.xxx = None`, placeholders partout | ✅ **Nouveau** (confirme et approfondit A8 de R#2) |

#### 🟡 Majeures

| ID | Finding |
|----|---------|
| **R3-M1** | **QTimer non managés** — chaque sous-module a son propre timer (Dashboard 1s, Monitoring 2s, Scheduler 5s, Memory 30s). Aucun arrêt centralisé. |
| **R3-M2** | **Thread workers non nettoyés** — workers créés sans `deleteLater()`, threads sans `quit()+wait()` |
| **R3-M3** | **Signaux Qt connectés multiple fois** — accumulation de slots pour un même signal → RAM + CPU |

#### 🟢 Architecturales

| ID | Finding |
|----|---------|
| **R3-A1** | Fonctions dupliquées entre ancienne et nouvelle arch : Scheduler, Cache, Metrics, Router, Memory, Pipeline existent en ×2 |
| **R3-A2** | Pas de point de démarrage unique — `run.py`→`ConversationEngine` au lieu de `run.py`→`Kernel.start()` |
| **R3-A3** | Managers à supprimer (ConversationManager, MemoryManager, ToolManager, AgentManager, SchedulerManager, ModelManager) → services Kernel |

---

### Convergences et divergences entre les 3 rapports

| Sujet | R#1 | R#2 | R#3 | Consensus |
|-------|-----|-----|-----|-----------|
| Chat muet (C1) | ❌ Confirmé | ❌ Confirmé | ❌ Cause racine : 3 orchestrateurs | ✅ **Convergence** |
| Documents (C2) | ❌ Confirmé | ❌ Cause précise : `_ingestion` | ❌ Cause racine : service absent du registre | ✅ **Complémentaire** |
| Mémoire (C4) | ❌ Confirmé | ❌ Mauvais nom `memory_store` | ❌ Cause racine : 2 MemoryManager distincts | ✅ **Complémentaire** |
| Double cache (C5) | Unifier | Supprimer | Supprimer (cause racine du problème) | ⚠️ Consensus sur le constat |
| KernelMetrics | Réutiliser | Supprimer | Supprimer (doublon Monitoring) | ⚠️ **R#1 vs R#2+R#3** |
| KernelScheduler | Démarrer | Supprimer | Supprimer (doublon QTimer) | ⚠️ **R#1 vs R#2+R#3** |
| **Que faire ?** | Fixer les bugs (Phase 0/1/2) | Fixer les bugs + supprimer les doublons | **Ne PAS fixer — refondre l'architecture d'abord** | ⚠️ **Divergence majeure** |

---

### Plan de correction consolidé (3 rapports)

#### Option A — Fix rapide (convergence R#1 + R#2, ~3h)

Corriger les bugs immédiats sans refondre l'architecture :
- C1 (chat muet) + C2 (documents) + C4 (mémoire) + C6 (RAMMonitor)
- Noms d'attributs `engine.xxx` erronés
- QTimer, ThreadPoolExecutor

**Risque** (selon R#3) : les correctifs locaux seront fragiles tant que l'architecture duale persiste.

#### Option B — Refonte Kernel-first (recommandation R#3, 1-2 semaines)

1. Faire de `NuruKernel` le point de démarrage unique (`run.py → Kernel.start() → UI`)
2. Le Kernel devient l'unique créateur de tous les services
3. Interdire toute instanciation directe (`Router()`, `MemoryManager()`, etc.)
4. EventBus unique pour toutes les communications
5. Pipeline unique (Kernel Pipeline remplace Orchestrator)
6. UI passive (observe des modèles, ne va pas chercher les données)

**Avantage** : traite la cause racine, élimine tous les symptômes simultanément.
**Inconvénient** : plus long, plus risqué (régressions).

---

### Correctifs proposés uniques par ce rapport

1. **Plan de migration en 6 étapes** : Kernel → Registry → Services → Plugins → UI (vs l'ordre actuel inversé)
2. **Architecture cible complète** : diagramme à 3 couches (Kernel / Services / Qt Models)
3. **Suppression de tous les `*Manager`** : ConversationManager, MemoryManager, ToolManager, AgentManager, SchedulerManager, ModelManager
4. **UI passive** : Dashboard observe un MetricsModel au lieu de `psutil` directement

---

*Fin des cinq rapports d'audit. Consolidation complète. En attente de décision.*

---

## Rapport #4 — Audit Technique NURU Kernel (2026-07-23)
**Source :** `audit_kernel3.md` (1946 lignes)
**Auteur :** Vibe (Mistral AI)
**Approche :** Audit structuré avec tables de connexion, diagrammes Mermaid, tests unitaires

### Nouveautés uniques (non couvertes par R#1-3)
- **DocumentsManager** et **ModelManager** comme nouveaux fichiers à créer dans `src/core/`
- **ContextBudget** à réduire : `max_prompt_tokens=4096` (au lieu de 8192), `reserved_response=1024`
- **EventBus compatible Qt** : transformation en `QObject` pour émettre directement dans le thread UI
- **Stratégie de tests complète** : unitaires (Kernel services, Chat flow, Metrics, Cache, Scheduler) + intégration + performance
- **Checklist de déploiement** : 15 étapes pré-déploiement, 6 post-déploiement
- **Diagrammes Mermaid** cible vs actuel

### Convergences
Mêmes diagnostics que R#1-3 : Chat contourne le Kernel, Dashboard ne lit pas KernelMetrics, Documents non enregistré, Cache inactif, Scheduler vide, RAM excessive.

---

## Rapport #5 — Audit Technique Intégration Kernel (2026-07-23)
**Source :** `audit_kernel4.md` (1546 lignes)
**Approche :** Analyse la plus détaillée avec numéros de ligne, correctifs de code complets, 3 étapes de correction

### Nouveautés uniques (non couvertes par R#1-4)

#### 🔴 Critiques
| ID | Finding | Impact |
|----|---------|--------|
| **R5-C1** | **Fuite de boucle asyncio par message** : `InferenceWorker` crée une nouvelle boucle à chaque message sans la libérer correctement. ~40 Mo × 20 messages = **800 Mo de fuite cumulative** | 🔴 RAM critique |
| **R5-C2** | **Reranker persistant** 800 Mo jamais déchargé, gardé en mémoire même sans usage, sans coordination avec RAMBudgetManager | 🔴 OOM |
| **R5-C3** | **Embedder dupliqué 3×** (RAGEngine, EpisodicMemory, SemanticMemory) cassent le singleton via threads distincts. **1,35 Go** de perte | 🔴 RAM |
| **R5-C4** | **EventBus en pull au lieu de push** : file passive jamais drainée → accumulation infinie en RAM. Solution : modèle push asynchrone | 🔴 Fuite mémoire |
| **R5-C5** | **Imports lourds statiques dans Documents** : `fitz`, `docx`, `openpyxl` importés en global scope → crash si package manquant | 🔴 Module cassé |

#### 🟡 Majeures
| ID | Finding |
|----|---------|
| **R5-M1** | **KV Cache en Float32 par défaut** : 800 Mo pour un contexte de 4000 tokens. Solution : forcer `kv_bits=8` dans `stream_generate()` |
| **R5-M2** | **`gc.collect()` et `mx.clear_cache()` jamais appelés** après déchargement de modèle → allocations Metal orphelines |
| **R5-M3** | **ThreadPoolExecutor jamais `shutdown()`** dans `LocalLLM` → threads orphelins accumulés à chaque rechargement |

#### 🟢 Correctifs de code spécifiques (R#5 uniquement)
1. **`documents_page.py`** : déplacer `import fitz` / `docx` / `openpyxl` dans les méthodes (lazy imports)
2. **`ingestion_engine`** : résoudre via `kernel.get("ingestion")` au lieu de `rag_engine._ingestion`
3. **`MemoryPage`** : appeler `set_data(data)` sur `MemoryExplorer` et passer `memory_store` à `PerformanceMemoryPage`
4. **`LocalLLM.unload()`** : ajouter `gc.collect()` puis `mx.clear_cache()`
5. **`stream_generate()`** : forcer `kv_bits=8`
6. **`EventBus`** : passer de pull (drain) à push (emit + notify subscribers)

---

## Synthèse finale — Cinq rapports d'audit

### Scores des rapports

| Rapport | Lignes | Approche | Précision code | Profondeur archi | Spécificité NURU |
|---------|:------:|----------|:--------------:|:----------------:|:----------------:|
| R#1 (Leblanc) | 916 | Bugs ligne par ligne | 🟢 Très haute | 🔵 Moyenne | 🟢 Native |
| R#2 | 1860 | Bugs + traces code | 🟢 Très haute | 🔵 Moyenne | 🟢 Native |
| R#3 (Leblanc) | 3289 | Architecture 360° | 🔵 Haute | 🟢 Très haute | 🟢 Native |
| R#4 (Mistral) | 1946 | Audit structuré + tests | 🟡 Générique | 🔵 Haute | 🟡 Moyenne |
| R#5 | 1546 | Technique détaillé | 🟢 Très haute | 🔵 Haute | 🟢 Native |

### Consensus unanime (5/5 rapports)

| Module | Diagnostic | Priorité |
|--------|-----------|:--------:|
| **Chat** | Contourne le Kernel, appelle NuruCore.orchestrator directement | 🔴 P0 |
| **Documents** | Service non enregistré dans le Kernel + imports statiques cassés | 🔴 P0 |
| **Mémoire** | 2 MemoryManager distincts (V5 et V9), l'UI lit le mauvais | 🔴 P0 |
| **Dashboard** | Appels psutil directs au lieu de KernelMetrics | 🟡 P1 |
| **Agents** | AgentOrchestrator jamais instancié ni enregistré | 🟡 P1 |
| **Outils** | ToolOrchestrator.setup() jamais appelé | 🟡 P1 |
| **Modèles** | Liste statique codée en dur dans l'UI, pas de lien avec ModelRouter | 🟡 P1 |
| **Cache** | Multiples caches concurrents, RAM jamais libérée | 🟡 P1 |
| **Scheduler** | Existe mais aucune tâche ne lui est soumise | 🟡 P1 |
| **RAM** | Embedder ×3, Reranker persistant, fuite asyncio par message | 🔴 P0 |

### Divergences entre rapports

| Sujet | R#1 | R#2 | R#3 | R#4 | R#5 | Majorité |
|-------|-----|-----|-----|-----|-----|:--------:|
| **Stratégie** | Fixer bugs | Fixer + supprimer | **Refondre d'abord** | Fixer + tests | Fixer + optimiser | Fixer (3/5) |
| **KernelMetrics** | Réutiliser | Supprimer | Supprimer | Réutiliser | Réutiliser | Réutiliser (3/5) |
| **KernelScheduler** | Démarrer | Supprimer | Supprimer | Démarrer | Démarrer | Démarrer (3/5) |
| **KernelCache** | Unifier | Supprimer | Supprimer | Unifier | Unifier | Unifier (3/5) |
| **EventBus** | — | — | Créer central | Compatible Qt | Push-based | Push-based (2/5) |
| **Documents** | — | _ingestion None | Service absent | DocumentsManager | Imports lazy | Complémentaire |

### Plan consolidé

```
Phase 0 — Flash (2-3h)
  ├─ Chat muet : brancher ConversationEngine._process() sur PipelineEngine
  ├─ Documents : lazy imports fitz/docx/openpyxl + kernel.get("ingestion")
  ├─ Mémoire : set_data() sur MemoryExplorer + memory_store pour PerformanceMemoryPage
  └─ RAM critic : gc.collect() + mx.clear_cache() dans unload()

Phase 1 — Infrastructure (1-2 jours)
  ├─ Noms d'attributs engine.xxx (memory_store→memory, proactive_engine→proactive)
  ├─ ThreadPoolExecutor.shutdown() dans LocalLLM.close()
  ├─ QTimer drainer EventBus → push-based EventBus
  ├─ KernelMetrics → EventBus → Dashboard (remplace psutil direct)
  └─ Embedder singleton via kernel.get("embedder")

Phase 2 — Kernel-first (1-2 semaines)
  ├─ NuruKernel = point de démarrage unique (run.py → Kernel.start() → UI)
  ├─ Plus de création directe : kernel.get() partout
  ├─ Services manquants : DocumentsManager, ModelManager, ToolOrchestrator
  ├─ KernelScheduler reçoit toutes les tâches (remplace asyncio.create_task)
  ├─ KernelCache unifié (LLMCache + RAGCache en régions)
  ├─ KV Cache 8-bit (kv_bits=8) pour diviser l'empreinte mémoire par 2
  └─ Pipeline Engine remplace l'ancien pipeline historique
```

### Fichiers à modifier (top 10 critiques)

| Fichier | Changement | Priorité |
|---------|-----------|:--------:|
| `src/core/conversation_engine.py` | _process() → kernel.get("pipeline").run_stream() | 🔴 P0 |
| `src/ui/components/documents_page.py` | Lazy imports fitz/docx/openpyxl | 🔴 P0 |
| `src/ui/pages/documents_page.py` | kernel.get("ingestion") au lieu de rag_engine._ingestion | 🔴 P0 |
| `src/ui/pages/memory_page.py` | set_data() sur MemoryExplorer | 🔴 P0 |
| `src/llm_local.py` | unload() += gc.collect() + mx.clear_cache() | 🔴 P0 |
| `src/llm_local.py` | stream_generate(kv_bits=8) | 🟡 P1 |
| `src/core/inference_worker.py` | Boucle asyncio réutilisée (pas de new_event_loop() par message) | 🟡 P1 |
| `src/core/events.py` | EventBus push-based (au lieu de drain pull) | 🟡 P1 |
| `src/ui/panels/right_inspector.py` | kernel.get("metrics") au lieu de psutil direct | 🟡 P1 |
| `src/kernel/__init__.py` | Enregistrer tous les services manquants | 🟡 P1 |

---

## Rapport #6 — Audit Final : Synthèse des Causes Racines dans le Code (2026-07-23)

**Source :** `audit_kernel5.md` (17 lignes, 4.6 Ko)
**Auteur :** Leblanc (même voix que R#1/R#3)
**Approche :** Méta-analyse — ne répète pas les bugs, connecte les causes racines entre les couches

### Nouveautés critiques (non couvertes par R#1-5)

| ID | Finding | Impact | Nouveauté |
|----|---------|--------|-----------|
| **R6-C1** | **Pages UI mises en cache définitivement** : `NavigationController.navigate_to()` crée chaque page UNE SEULE fois via factory, puis la cache. Si l'utilisateur clique avant la fin de l'init asynchrone de `NuruCore`, la page reçoit `engine.xxx = None` et **ne se reconstruit jamais**. | 🔴 Explique "Mémoire vide", "Documents non disponible", "Agents vides" comme un problème d'ordre d'init, pas d'absence de service | ✅ **Nouveau** — le bug est dans `nav_controller.py` + `MainWindow.set_engine()` |
| **R6-C2** | **`MainWindow.set_engine()` a un commentaire sans code** : ligne ~355 : `# Màj des pages qui dépendent de l'engine` suivi d'**aucune implémentation** | 🔴 Les pages ne sont jamais rafraîchies après l'init async | ✅ **Nouveau** |
| **R6-C3** | **`KernelMetrics.start()` jamais appelée** : la boucle périodique async de `KernelMetrics` n'est démarrée nulle part → seul le mode "collecte à la demande" fonctionne | 🟡 Métriques jamais mises à jour automatiquement | ✅ **Nouveau** |
| **R6-C4** | **Agents : confusion entre UI et vrai système ReAct** : la page Agents affiche ProactiveEngine + RoutineScheduler, pas `AgentOrchestrator` (2000 lignes, câblé côté pipeline mais gaté par `config.agent_loop_enabled=False` et limité aux requêtes COMPLEX) | 🟡 L'UI Agent ne montre pas le vrai système | ✅ **Nouveau** |
| **R6-C5** | **Outils : 2 registres non unifiés** : MCPServer = 4 outils codés en dur dans `_register_mcp_tools()`. `ToolRegistry` (22 outils) jamais exposé via MCP | 🟡 | Confirmé |
| **R6-C6** | **Modèles : placeholder explicite** : `models_list` codé en dur, docstring dit "Phase 2b : placeholder" — pas un bug de câblage, une fonctionnalité jamais implémentée | 🟢 Confirmation | |

### Plan de correction actualisé (6 rapports)

#### Top 10 fichiers à modifier (priorité 🔴 = bloque NURU)

| # | Fichier | Bug | Fix | Priorité |
|:-:|---------|-----|-----|:--------:|
| 1 | `src/ui/navigation/nav_controller.py` | `navigate_to()` crée 1× puis cache définitivement | Forcer reconstruction ou update après init async | 🔴 P0 |
| 2 | `src/ui/main_window.py` ~355 | `set_engine()` commente "Màj des pages" sans code | Ajouter le refresh des pages après init | 🔴 P0 |
| 3 | `src/core/conversation_engine.py` | `_process()` ignore PipelineEngine du Kernel | Rediriger vers `pipeline.run_stream()` | 🔴 P0 |
| 4 | `src/ui/components/documents_page.py` | Imports lourds en global scope (fitz, docx, openpyxl) | Lazy imports dans les méthodes | 🔴 P0 |
| 5 | `src/ui/pages/documents_page.py` | `rag_engine._ingestion` n'existe pas | `kernel.get("ingestion")` ou appeler `set_ingestion()` existante | 🔴 P0 |
| 6 | `src/ui/pages/memory_page.py` | `set_data()` jamais appelé sur MemoryExplorer | Appeler après init | 🔴 P0 |
| 7 | `src/llm_local.py` `unload()` | gc.collect() + mx.clear_cache() manquants | Ajouter après `del self._model` | 🔴 P0 |
| 8 | `src/ui/pages/dashboard_page.py` | `psutil` direct au lieu de `kernel.metrics.collect()` | Remplacer | 🟡 P1 |
| 9 | `src/kernel/metrics.py` | `start()` jamais appelée | Démarrer dans NuruCore.__init__() | 🟡 P1 |
| 10 | `src/tools/orchestrator.py` | `ToolOrchestrator.setup()` jamais appelé | Appeler dans NuruCore.__init__() | 🟡 P1 |

#### Top 10 correctifs RAM (M1 8 Go)

| # | Fichier | Bug | Économie |
|:-:|---------|-----|:--------:|
| 1 | `src/llm_local.py` `stream_generate()` | `kv_bits=8` manquant | ~400 Mo |
| 2 | `src/llm_local.py` `unload()` | Pas de `mx.clear_cache()` | ~200 Mo |
| 3 | `src/core/inference_worker.py` | Boucle asyncio par message | ~800 Mo (20 tours) |
| 4 | `src/rag_engine.py` | CrossEncoderReranker jamais déchargé | ~800 Mo |
| 5 | Multiples fichiers | Embedder ×3 (RAGEngine, Episodic, Semantic) | ~900 Mo |
| **Total** | | | **~3.1 Go économisables** |

---

*Six rapports d'audit analysés et consolidés. En attente de décision sur la stratégie de correction.*

---

## Rapport #4 — NURU Kernel Integration Audit Report (2026-07-23)

**Source :** `audit_kernel3.md` (1946 lignes)
**Auteur :** Vibe (Mistral AI)
**Approche :** Analyse systématique avec plan d'action, snippets de code, tests, checklist de déploiement
**Verdict :** « Kernel conçu comme système nerveux central mais contourné par la plupart des modules »

---

### Nouveaux findings (non couverts par R#1, R#2, R#3)

| ID | Finding | Nouveauté |
|----|---------|-----------|
| **R4-F1** | **Créer `DocumentsManager`** (nouvelle classe wrapper) pour exposer l'ingestion au Kernel | ✅ Nouveau — les autres rapports proposaient de corriger l'existant |
| **R4-F2** | **Créer `ModelManager`** (nouvelle classe wrapper) pour exposer les modèles via `kernel.get("models")` | ✅ Nouveau |
| **R4-F3** | **Enregistrer les composants lourds** (Embedder, Reranker, LocalLLM) dans `KernelResources` avec callbacks d'eviction | ✅ Nouveau — détail d'implémentation |
| **R4-F4** | **Réduire `ContextBudget`** — `max_prompt_tokens` de 8192→4096, `reserved_response` de 2048→1024 | ✅ Nouveau |
| **R4-F5** | **Stratégie de tests** — unitaires (kernel.get), intégration (flux chat), performance (RAM) | ✅ Nouveau |
| **R4-F6** | **Factories pour dépendances circulaires** — `kernel.register_factory("router", lambda: Router(llm=kernel.get("llm")))` | ✅ Nouveau — approche élégante |

---

### Synthèse : ce que chaque rapport apporte d'unique

| Trouvaille | R#1 | R#2 | R#3 | R#4 |
|------------|:---:|:---:|:---:|:---:|
| Chat muet — exceptions non capturées | ✅ | ✅ | — | — |
| Noms d'attributs `engine.xxx` erronés (5) | — | ✅ | — | — |
| RAMMonitor obsolète à supprimer | — | ✅ | — | ✅ |
| 3 orchestrateurs coexistent (cause racine) | — | — | ✅ | — |
| Double instances de tous les services | — | — | ✅ | — |
| Créer `DocumentsManager` / `ModelManager` | — | — | — | ✅ |
| Enregistrer composants lourds + eviction | — | — | — | ✅ |
| Réduire ContextBudget (4096 tokens) | — | — | — | ✅ |
| Stratégie de tests formelle | — | — | — | ✅ |
| Plan de migration Kernel-first (6 étapes) | — | — | ✅ | ✅ |

---

*Fin du quatrième rapport. En attente de la suite.*
