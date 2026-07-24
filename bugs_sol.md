# bugs_sol.md — Conclusions consolidées (4 audits)

> Généré 2026-07-21, MAJ après 5 phases d'audit forensique.  
> Code vérifié sur HEAD `629ce65` (branche `ui-v16-refonte`).

---

## 🔴 CRITIQUES IMMÉDIATES (corroborées par les 4 audits)

### P0-A. DOUBLE RETRIEVE RAG ← **NOUVEAU, CRITIQUE**

**Fichier :** `src/agent/orchestrator.py:443` + `:529`

**Pipeline réel :**
```
run(query)
  ├── _plan()                  ← 1er retrieve(query) — contexte JETÉ
  │     ├── rag.retrieve(query)      → context, result
  │     ├── PlanResult.rag_documents_found = result.documents_found  ← seul le métrique compte
  │     └── PlanResult.rag_confidence = result.confidence_label
  │                                    ↑ context est perdu !
  │
  └── _execute(query, plan)    ← 2e retrieve(query) — contexte reconstruit
        └── rag.retrieve(query)      → context, result
```

Chaque appel `retrieve()` coûte : 2 embeddings, vector search, BM25, RRF fusion, reranker, compression, context builder. **Tout ce travail est fait 2× par requête.**

**Autre sous-produit :** Les métadonnées de RAG (scores, documents) sont dans `_plan()` mais pas dans `_execute()`. La deuxième passe a ses propres scores.

**Correctif (5 min) :** Stocker le contexte RAG dans `PlanResult` et le réutiliser dans `_execute()`.

```python
@dataclass
class PlanResult:
    ...
    rag_context: str = ""          # ← AJOUT
    rag_rag_result: Any = None     # ← AJOUT
```

Dans `_plan()`, après `retrieve()` :
```python
plan.rag_context = context or ""
plan.rag_result = result
```

Dans `_execute()`, remplacer le 2e `retrieve()` par :
```python
result["rag_context"] = plan.rag_context
```

---

### P0-B. DOUBLE CONTEXTE MÉMOIRE ← **NOUVEAU**

**Fichier :** `src/agent/orchestrator.py:455` + `:543`

Même patron :
1. `_plan()` (l.455) : `mem.get_full_context(query)` — chargé, metrics extraits, **contexte texte perdu**
2. `_execute()` (l.543) : `mem.get_user_profile()` — chargé à nouveau (méthode différente, même base)

**Correctif :** Stocker le contexte mémoire dans `PlanResult`, éviter la double collecte.

---

### P0-C. `_safe_emit` cassé → signaux jamais transmis à l'UI (phase 4)

**Fichier :** `src/core/conversation_engine.py:374`

`QTimer.singleShot(0, lambda: signal.emit(value))` depuis un thread sans Qt event loop. Ce timer **ne se déclenche jamais**. Tous les signaux (`token_received`, `response_complete`, `strategy_changed`, `error_occurred`) sont perdus.

**Correctif :** `signal.emit(value)` direct.

---

### P0-D. `CLASSIFY_PROMPT.format(query=query)` envoie `<<QUERY>>`

**Fichier :** `src/routing/router.py:331`

Littéral. Le prompt contient `<<QUERY>>` mais le code utilise `.format(query=query)`. Python `str.format` utilise `{query}`, pas `<<QUERY>>`. Aucune substitution. Le LLM reçoit littéralement `<<QUERY>>` et retourne "GENERAL" par défaut.

**Correctif :** `.replace("<<QUERY>>", sanitize_for_prompt_injection(query))`.

---

### P0-E. `asyncio.run()` dans 4 modules mémoire

**Fichiers :** `semantic.py:367`, `episodic.py:221`, `errors.py:368`, `procedural.py:52`

`asyncio.run()` lève `RuntimeError` si une boucle tourne déjà. Le fallback crée une boucle éphémère — fragile et lent.

**Correctif rapide :** `self.embedder.embed_sync(text, is_query=False)` (méthode synchrone déjà existante).

**Correctif long :** Pipeline mémoire entièrement async (agenda V17).

---

### P0-F. `get_full_context` synchrone dans pipeline async

**Fichiers :** `src/rag_engine.py:1040`, `src/agent/orchestrator.py:455`, `src/core/orchestrator.py`

`mem.get_full_context(query)` est synchrone, appelé sans `await` dans `async def retrieve()` et `async def _plan()`. Cascade : `get_full_context` → `semantic.recall` → `_embed_sync` → `asyncio.run()`. Le `RuntimeError` est catché par `except Exception` dans `retrieve()` (rag_engine.py) et `_plan()` (agent/orchestrator.py) → **silencieux**.

---

## 🟠 DÉFAUTS MAJEURS

### P1-A. AgentOrchestrator : singleton mutable, trop de responsabilités

**Fichier :** `src/agent/orchestrator.py`

- Singleton monstrueux (1229 lignes) avec 7+ sous-composants lazy
- Pas de `shutdown()` / `cleanup()` — objets vivent jusqu'à l'extinction
- Plan, Execute, Verify, Synthesize, Recovery dans la même classe
- 16+ `except Exception: logger.debug(...)` → **exceptions avalées**
- Les contextes RAG (200+ Ko) sont copiés dans `AgentTrace` → dupliqués

---

### P1-B. Pipeline opaque — pas de métriques intermédiaires

Aucune donnée entre les étapes :
- `embedding : 12 ms` ❌
- `vector search : 9 ms` ❌
- `reranker : 42 ms` ❌
- `compression : 5 ms` ❌

Impossible de savoir où est le goulot.

---

### P1-C. Pas d'observabilité (correlation ID, logs JSON, événements)

- Aucun `correlation_id` dans les logs
- Logs texte plat, pas de JSON structuré
- Pas d'événements métier (EventBus sous-utilisé)
- Pas de chronométrage par phase dans l'UI

---

### P1-D. Caches indépendants sans politique globale

Au moins 5 caches probables (embedding, retriever, mémoire, documents, LLM provider). Chacun retient ses données sans limite. En combinaison → pression RAM.

---

### P1-E. Aucune politique de destruction/cleanup

Pas de `close()`, `dispose()`, `release()` ou `cleanup()` dans :
- `MemoryManager`
- `RAGEngine`
- `AgentOrchestrator`
- `Router`
- `BrowserController`

Les modèles (embedder, reranker, LLM local) restent chargés en permanence.

---

### P1-F. Modèles jamais déchargés

- Embedder MLX (~400-500 Mo) — chargé à la 1re requête, jamais libéré
- Reranker cross-encoder (~500 Mo) — idem
- LLM local Phi-4 (~2 Go) — keep-alive infini

En cumul : ~3 Go de modèles qui ne redescendent jamais.

---

### P1-G. Pas de gestionnaire global de mémoire (Memory Supervisor)

Aucune coordination :
```
RAM > 60 % → vider caches
RAM > 70 % → décharger Browser
RAM > 80 % → décharger reranker
RAM > 90 % → décharger LLM local → forcer cloud
```

Aujourd'hui chaque composant agit en silo.

---

### P1-H. Pas de mode "M1 8 Go"

Profil dédié qui activerait automatiquement :
- Petit embedder (Qwen2-0.5B)
- Reranker désactivé par défaut
- Cache réduit
- Compression agressive
- 1 provider, 1 LLM max
- Pas de Browser (sauf si demandé)

---

## 🟡 DÉFAUTS MODÉRÉS

- RAG pipeline monolithique : impossible d'injecter des stratégies alternatives
- `TokenJuice` utilisé trop tard : compression après duplication des contextes
- Traces (`AgentTrace`) non limitées : aucune rotation/TTL
- Import paresseux de TOUS les sous-modules → 1re requête très lente
- Budget de tokens pas explicite (mémoire, RAG, prompt, historique)
- Score de confiance global absent : pas de décomposition `retrieval → rerank → memory → LLM`
- BrowserController non isolé dans un processus séparé
- `_sessions` dans AgentOrchestrator ne sont jamais nettoyées
- Contextes dupliqués dans `parts[]`, `trace`, `synthesis`, `response`
- Pas de machine d'état explicite (statuts = strings magiques)
- Reranker/SC désactivé sans notification UI
- `build_context` coupe les paires paires-impaire
- Pas de fallback web si RAG sous-score < 0.3
- `np.frombuffer(...).reshape(n, dim)` crash si dimensions incohérentes

---

## ✅ CORRECTIFS DÉJÀ APPLIQUÉS

| Correctif | Fichier | Statut |
|-----------|---------|--------|
| Parser SSE fallback `message.content` | `llm_cloud.py:304-310` | ✅ appliqué |
| Timeout httpx 60s | `llm_cloud.py:287` | ✅ appliqué |
| `yield token` avant `is_cancelled` | `llm_generator.py:211` | ✅ appliqué |
| `_spawn_background` timeout 60s + cap 20 | `orchestrator.py:781` | ✅ appliqué |
| RAMBudget soft_limit 4.0, swap_warning 50% | `ram_budget.py` | ✅ appliqué |
| `should_force_cloud()` si RAM < 1 Go | `ram_budget.py` | ✅ appliqué |
| Forçage cloud auto si swap > 80% | `ram_budget.py` | ✅ appliqué |
| Nettoyage fichiers morts (~665 Mo) | Racine | ✅ appliqué |
| 43 PDFs corrompus réparés | Documents/ | ✅ appliqué |
| ModelRouter dynamique | `nuru_core.py` | ✅ appliqué |

---

## 📋 PLAN D'ACTION PRIORISÉ

### Phase 1 — Bloquer l'hémorragie ✅ APPLIQUÉ

| # | Action | Fichier | Effort | Statut |
|:-:|--------|---------|--------|:------:|
| 1 | Éviter double retrieve RAG (stocker dans PlanResult) | `agent/orchestrator.py` | 10 lignes | ✅ |
| 2 | Éviter double memory (stocker dans PlanResult) | `agent/orchestrator.py` | 5 lignes | ✅ |
| 3 | `_safe_emit` : `signal.emit(value)` direct | `conversation_engine.py:374` | 1 ligne | ✅ |
| 4 | `CLASSIFY_PROMPT` : `.replace()` au lieu de `.format()` | `router.py:331` | 1 ligne | ✅ |
| 5 | `_do_stream` : fallback `content` direct | `llm_cloud.py:311` | +1 elif | ✅ |
| 6 | `embed_sync` direct (évite `asyncio.run()`) | 4 fichiers mémoire | 4×1 ligne | ✅ |

### Phase 2 — Architecture (cette semaine)

- Rendre `get_full_context` async + `await` dans `retrieve()`
- `_is_online` async + cache TTL
- Déchargement conditionnel de l'embedder (si swap > 50%)
- Timer progressif dans l'UI (chat_page.py)
- Correlation ID + logs JSON

### Phase 3 — Réflexion conception

- **ResourceManager global** : supervise mémoire, coordonne chargements/déchargements
- Politiques : `RAM > X % → libérer Y`
- Mode profil "M1 8 Go"
- Budget de tokens par composant
- Découpage de `AgentOrchestrator` (actuellement 1229 lignes)
- Pipeline RAG en composants indépendants (vector, BM25, fusion, reranking, compression)
- Browser isolé dans processus séparé
- Métriques par étape → dashboard temps réel

---

## État des lieux

| Métrique | Avant correctifs | Après P1 | Cible |
|----------|:---:|:---:|:---:|
| RAM au repos | 4.3+ Go bloquants | ~3.2 Go (modèles chargés) | <2.5 Go |
| Temps 1re requête | 20-30 s | ~12-15 s (double retrieve) | <5 s |
| Temps requête suivante | 15-20 s | ~8-12 s | <3 s |
| Swap permanent | 93-96% | inchangé (modèles) | <30% |
| Taux hallucination | inconnu | devrait baisser (route correct) | <5% |
| Réponses affichées | 0% | ✅ devrait passer | 100% |

---

*Document consolidé des 4 audits forensiques reçus.  
Dernière MAJ : 2026-07-21*

---

## KERNEL SPRINT — Session 2026-07-23

### Décision : Chemin A — Composants du noyau (5 modules)

Ordre validé : state.py → event_bus.py → metrics.py → resources.py → enregistrement NuruCore.

### État avant session

| Composant | Statut | Détail |
|-----------|--------|--------|
| ServiceRegistry | ✅ LIVE — 189L | thread-safe, factory lazy, lifecycle start/stop, snapshot |
| NuruKernel facade | ✅ LIVE — 211L | singleton, 18 accesseurs typés, boot/shutdown |
| EventBus (core/events.py) | ✅ LIVE — 96L | singleton thread-safe, subscribe/emit/emit_sync/drain — DÉJÀ enregistré via `NuruCore.__init__` ligne 152 |
| RAMBudgetManager (core/ram_budget.py) | ✅ LIVE — 441L | politique M1, monitoring loop, éviction priorisée — PAS ENCORÉ enregistré comme service kernel (singleton global `get_budget()` encore actif) |
| SessionMemory (core/session_memory.py) | ✅ LIVE — 105L | buffer FIFO 6 messages, thread-safe — singleton global `get_session_memory()` encore actif |
| KernelState (kernel/state.py) | ✅ Phase 3.6a — LIVE | index état global, thread-safe, property kernel.state |
| KernelMetrics (kernel/metrics.py) | ✅ Phase 3.6b — LIVE | collecteur périodique (psutil), property kernel.metrics |
| KernelResources (kernel/resources.py) | ✅ Phase 3.6c — LIVE | wrapper RAMBudgetManager, property kernel.resources — `get_budget()` remplacé dans NuruCore, reste legacy modules |
| PipelineEngine (kernel/pipeline.py + steps) | ✅ Phase 3.9 — LIVE | 7 steps composables, PipelineContext, cycle de vie kernel |
| KernelRouter (kernel/router.py) | ✅ Phase 3.8 — LIVE | classifieur 5-bucket minimal, zero LLM, cache TTL |
| KernelScheduler (kernel/scheduler.py) | ✅ Phase 3.10 — LIVE | 7 priorités, files, conscience RAM, pause/resume/cancel |
| KernelCache (kernel/cache.py) | ✅ Phase aval — LIVE | 5 régions, TTL, priorité éviction, intégré à KernelResources |

### Constats d'audit (avant écriture)

1. **Le code existant est plus mûr que la skill ne le décrit.** EventBus déjà enregistré et utilisé. RAMBudgetManager est un singleton sous `get_budget()`. Pas de régresseur bloquant.

2. **Les modules consommateurs (ingestion, orchestration, memory/*.py, agent/orchestrator.py) utilisent déjà l'injection par constructeur.** Le "3.5c" est à 95% déjà appliqué — les migrations sont des fignolages sans valeur architecturale aujourd'hui.

3. **Les vrais couplages à éliminer :** `llm_generator.py:162` (get_budget() appelé en inline), `agent/orchestrator.py:254` (RAGEngine instancié local), `rag/index_health.py:87` (RAGEngine instancié local).

### Plan M1 — kernel/state.py (PAS ENCORÉ ÉCRIT)

**Vocation :** Index léger de l'état global — le kernel "sait", pas "décide". Ne duplique PAS SessionMemory/MemoryStore/ConversationEngine — les référence. Thread-safe.

**API prévue :**
- `state.get("key")` / `state.set("key", value)` — registre clé-valeur simple
- `state.active_model` / `state.activate_model("phi-4-mini")` — LLM actif
- `state.active_worker` / `state.activate_worker(worker)` — worker en cours
- `state.conversation_id` — ID de conversation courante
- `state.ram_pressure()` — délègue à RAMBudgetManager (si enregistré)
- `state.snapshot()` — dict complet pour debug/monitoring UI

**Contrainte M1 :** Aucune dépendance croisée. Si `RAMBudgetManager` n'est pas encore enregistré dans le kernel, `ram_pressure()` retourne None silencieusement.

### Point de départ pour demain

1. **Écrire** `src/kernel/state.py` (~100 lignes)
2. **Tester** : `python -c "from src.kernel.state import KernelState; print('OK')"`
3. **Câbler** : ajouter property `state` sur `NuruKernel` + enregistrer dans `NuruCore.__init__`
4. **Passe** aux M2-M4, même process

### Environnement

- Machine : M1 8 Go (swap permanent si PyCharm + Chrome + Teams)
- Repo : `/Users/leblancbahiga/Downloads/Assistant IA/`
- Dernier commit : `eaa56c8` (Phase 3.5b)
- Test : `python -c "import src; print('OK')"` après chaque module
