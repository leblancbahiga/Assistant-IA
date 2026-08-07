<div align="center">

<img src="src/ui/assets/Gemini_Generated_Image_35cdt735cdt735cd_transparent.png" width="160" alt="NURU V17"/>

<br/>

# 🌀 NURU — Personal Cognitive OS

<i>De l'assistant IA agentic au système d'exploitation cognitif personnel.<br/>
Conçu pour tourner en local d'abord, sur un MacBook Pro M1 de 8 Go de RAM unifiée.</i>

<br/>

<p>
  <img src="https://img.shields.io/badge/V17-Active-00D4FF?style=for-the-badge&logo=probot" alt="V17 Active"/>
  <img src="https://img.shields.io/badge/Platform-macOS%20M1%208GB-39FF14?style=for-the-badge&logo=apple&logoColor=white" alt="macOS M1 8GB"/>
  <img src="https://img.shields.io/badge/LLM-Phi--4--mini%20(MLX)-FFB000?style=for-the-badge" alt="LLM Phi-4-mini"/>
  <img src="https://img.shields.io/badge/Tests-953%20passing-success?style=for-the-badge" alt="953 tests"/>
  <img src="https://img.shields.io/badge/V17%20Phase%202-%E2%9C%85-success?style=for-the-badge" alt="Phase 2 done"/>
  <img src="https://img.shields.io/badge/Architecture-DeepSeek--like-8B5CF6?style=for-the-badge" alt="DeepSeek-like"/>
</p>

</div>

<br/>

---

## Why NURU?

La plupart des assistants IA promettent d'être "personnels". Leur implémentation concrète : ils envoient vos prompts vers un serveur cloud qui appartient à quelqu'un d'autre. Le "personnel" est dans le marketing, pas dans l'architecture.

NURU part du postulat inverse — **le personnel commence par l'exécution locale**. Le routeur envoie les requêtes simples vers **Phi-4-mini (4-bit MLX)** qui tourne sur le GPU M1. Le cloud — Groq, OpenRouter, DeepSeek — n'est contacté que **quand c'est vraiment nécessaire** (questions d'actualité, tâches que le local ne sait pas tenir, ou RAM sous le seuil critique).

Ce qui rend NURU différent d'un wrapper LLM local :

- **Système d'exploitation cognitif**, pas chatbot — la mémoire (Episodic/Semantic/User/Error), le sommeil (SleepCycleManager 3 phases light/deep/REM), et la persona (PersonaEngine) sont des citoyens de première classe du système, pas des add-ons.
- **Philosophie DeepSeek** — petits spécialistes orchestrés > monolithe. KV Cache Compression style MLA, LoRA adapter RAG, speculative decoding, RAM budget manager.
- **Privacy Layer** + opt-in granulaire par capteur (voix, vision écran, calendrier). Zéro fuite par défaut.
- **Agent Loop** sandboxé : planner → executor → verifier → recovery, avec approbation humaine pour les actions à risque.
- **Pipeline vocal local** (STT/TTS/VAD/wake word), présence animée Z.ai-style, latency sub-seconde sans réseau.
- **Monitoring RAM unifié** — RAMBudgetManager central avec boucle périodique, éviction contextuelle, callback `clear_reranker` / `_maybe_unload_embedder`.

Le but est simple : **vivre avec un JARVIS personnel sur la machine qu'on a déjà**, sans céder ses données à chaque requête.

---

## Installation

```bash
git clone https://github.com/leblancbahiga/NURU.git
cd NURU
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Configuration des clés API dans votre Keychain macOS (jamais dans le repo) :

```bash
# Une seule fois
security add-generic-password -a nuru -s com.nuru.assistant/groq -w "VOTRE_CLE_GROQ"
security add-generic-password -a nuru -s com.nuru.assistant/openrouter -w "VOTRE_CLE_OPENROUTER"
security add-generic-password -a nuru -s com.nuru.assistant/deepseek -w "VOTRE_CLE_DEEPSEEK"
```

Pré-requis validés :
- **macOS 13+** sur architecture Apple Silicon (M1/M2/M3)
- **8 Go de RAM unifiée** minimum — conçu spécifiquement pour ce budget
- **Python 3.13** (recommandé) ou ≥3.11
- HuggingFace CLI actif (`huggingface-cli login`) pour le téléchargement initial des modèles MLX (~3.5 Go)

---

## Quick Start

```bash
# Lancer le dashboard V17 (présence ambiante Z.ai — tray + floating widget)
python3 src/main.py

# Chat CLI simple (léger, sans UI)
python3 cli.py

# Réindexation des documents
python3 reindex_all.py

# Tests
unset PYTHONPATH && python3 -m pytest tests/ -v
```

| Commande | Effet |
|----------|-------|
| `python3 src/main.py` | Interface ambiante V17 (tray icon + floating widget + orb animé) |
| `python3 cli.py` | Mode terminal pour usage SSH / serveur headless |
| `python3 reindex_all.py` | Indexe tous les documents du workspace |
| `unset PYTHONPATH && pytest tests/` | Suite complète — 953 tests (RAG, agent, mémoire, router, LoRA) |

> **Note :** `unset PYTHONPATH` nécessaire pour éviter que l'environnement Hermes (Python 3.11) ne pollue le venv Python 3.13 avec ses dépendances compilées incompatibles.

---

## V17 — Monitoring & Branchements (phase 2 ✅)

V17 Phase 2 corrige les problèmes de branchement et de coordination identifiés par l'audit — les systèmes **existaient mais n'étaient pas connectés** au pipeline réel.

| Item | Problème | Correctif | Statut |
|:----:|:---------|:----------|:------:|
| 1 | `_safe_emit` non thread-safe | Signal direct (pas d'EventBus), déjà en place V17 | ✅ |
| 2 | 3 systèmes RAM non coordonnés | RAMBudgetManager central avec callbacks migrés + boucle périodique d'éviction | ✅ |
| 3 | Routes jamais reconstruites après clé API | `refresh_model_routes()` + EventBus `api_keys_updated` | ✅ |
| 4 | Absence de correlation ID dans logs | UUID hex[:12] dans `QueryContext` + fichier `logs/nuru.jsonl` | ✅ |
| 5 | Aucun timer/progression dans streaming | ⏱/✅ affiché pendant la génération | ✅ |
| 6 | Reranker toujours actif sous pression RAM | Éviction automatique via RAMBudgetManager.probe() | ✅ |
| 7 | `_embed_sync` dupliqué ×3 | Utilitaire partagé `src/memory/_embed_utils.py` | ✅ |
| 8 | AgentOrchestrator ~2000 lignes jamais branché | Warning log + documentation explicite | 🟢 Documentation |
| 9 | 450 `except Exception` silencieux | Blocs critiques corrigés, reste à poursuivre | 🟡 En cours |

---

## LoRA RAG — De l'entraînement à l'inférence (V17 ✅)

### Ce qui a changé (V17)

L'adaptateur LoRA entraîné (V16.4, 2000 itérations, val loss 1.155) était **correctement entraîné mais jamais chargé à l'inférence** — `set_lora_adapter()` n'était appelé nulle part en dehors des tests unitaires.

**V17 corrige ce trou de branchement :**

- `config.py` — Deux nouveaux champs : `lora_adapter_path` (défaut `data/adapters/rag`) et `lora_adapter_enabled` (coupe-circuit)
- `nuru_core.py` — Méthode `_init_lora_adapter()` appelée **au démarrage**, juste après `_init_model_routes()`
- `llm_local.py` — Propriété `lora_active` + flag `_lora_loaded` qui suit le succès réel de `load_adapters()`
- `orchestrator.py` — `lora_active` propagé dans les métadonnées de réponse (`event_data`) pour visibilité UI

```python
# Flux réel au démarrage (nuru_core.py:_init_lora_adapter)
adapter_file = Path("data/adapters/rag") / "adapters.safetensors"
if adapter_file.exists():           # ✅ 5.8 MB sur disque
    self.local_llm.set_lora_adapter("data/adapters/rag")   # ← était manquant
```

### Pipeline d'entraînement (V16.4)

```text
RAG chunks (3993) → build_large_dataset.py → train.jsonl (384 ex, 18% piège)
                                                   └→ valid.jsonl (16 ex, 25% piège)
                                                         ↓
                                              lora_train.py V16.4
                                        Phi-4-mini-instruct-4bit (MLX)
                                            2000 iters, 4 layers, 1024 seq
                                         cosine_decay + warmup 30 + dropout 0.05
                                                         ↓
                                          adapters.safetensors (1.44M params)
```

### Résultats du training

| Iters | Train Loss | Val Loss | LR | RAM |
|-------|-----------|---------|-----|-----|
| 1 | — | 3.023 | 5.0e-05 | 3.78 GB |
| 500 | 1.335 | 1.269 | 4.4e-05 | 4.18 GB |
| 1000 | 1.134 | 1.228 | 3.5e-05 | 4.18 GB |
| 1500 | 0.921 | 1.301 | 1.6e-07 | 4.18 GB |
| **2000** | **0.897** | **1.155** | **3.2e-08** | **4.18 GB** |

- Durée : **3h46** sur M1 8 Go (13567s)
- Pas de crash GPU — `num_layers=4` + `grad_checkpoint` + `clear_cache_threshold`
- Pics mémoire : 4.18 GB (stable)

### Scripts associés

| Script | Rôle |
|--------|------|
| `scripts/build_large_dataset.py` | Génération dataset 400 ex depuis RAG |
| `scripts/lora_train.py` | Entraînement LoRA (config V16.4) |
| `scripts/eval_factual.py` | Évaluation factuelle avec questions réelles |

---

## Monitoring RAM unifié (V17)

V17 unifie les 3 systèmes RAM qui coexistaient indépendamment :

| Système | Rôle V16 | Rôle V17 |
|:--------|:---------|:---------|
| **RAMBudgetManager** | Budget Go·s, éviction | **Source de vérité unique** — monitoring périodique + callbacks |
| **RAMMonitor** | Polling RAM 1-5s + callbacks | Callbacks migrés vers RAMBudgetManager (fichier conservé) |
| **model_manager.py** | Cycle de vie MLX | Conservé utilisable, documentation ajoutée |

Le nouveau cycle de monitoring :

```python
async def _monitor_loop(self):
    while self._monitoring:
        await asyncio.sleep(self._interval)
        probe = self.probe()
        if probe.swap_percent >= self.hard_limit_pct:
            for cb in self._callbacks:
                cb()        # clear_reranker, _maybe_unload_embedder
            self.evict(target_pct=self.soft_limit_pct)
```

---

## V16 — Architectures de raisonnement (livrées ✅)

V16 implémente 3 architectures de raisonnement complémentaires, activées
automatiquement selon le type de requête et la confiance RAG.

### Pipeline décisionnel

```text
Requête →
  ├─ "tot:" / goal P0 + 15+ mots ───→ 🌳 Tree of Thoughts (agentic)
  ├─ COMPLEX / RAG complexe (>7 mots) → 💭 Chain of Thought
  ├─ RAG + confiance HAUTE/MOYENNE ──→ 🗳️ Self-Consistency (3 votes)
  └─ SIMPLE ──────────────────────────→ Streaming direct
```

### Self-Consistency (Item 35)

Réduit les hallucinations de ~40% sur les réponses RAG en générant 3 échantillons,
les regroupant par similarité TF-IDF, et ne retenant que le cluster majoritaire.
Seuil de vote calibré à 0.25 sur le modèle local Qwen-2.5-1.5B.

```python
# Activation automatique pour les requêtes RAG bien couvertes
use_self_consistency = intent == "RAG" and confidence_label in ("HAUTE", "MOYENNE")
```

- **Module** : [`src/learning/self_consistency.py`](src/learning/self_consistency.py)
- **Métriques** : 3 générations × ~500 tokens → ~10-15s sur M1 8Go

### Chain of Thought

Raisonnement transparent étape par étape pour les questions complexes.
Le prompt est enrichi d'une instruction de décomposition, puis le raisonnement
est extrait et formaté séparément de la réponse finale.

- **Module** : [`src/learning/chain_of_thought.py`](src/learning/chain_of_thought.py)
- **Activation** : 7+ mots + patterns (`explique`, `compare`, `analyse`, ...)
- **Overhead** : ~1000 tokens de raisonnement, ~15% précision supplémentaire

### Tree of Thoughts Agentic 🌟

Exploration BFS d'arbres de raisonnement avec **validation par actions réelles**.
Chaque branche peut déclencher un outil local via `[OUTIL: nom(paramètres)]` :
lecture de fichier, recherche RAG, interrogation mémoire, ou commande shell sécurisée.
Le résultat de l'outil est injecté comme preuve dans le score d'évaluation.

```python
Branche: "Je soupçonne une erreur dans config.yml"
  → [OUTIL: read_file(path="config.yml")]
  → Validation: fichier trouvé (+0.2)
  → Score final: 0.85 (vs 0.65 sans outil)
```

- **Module** : [`src/learning/tree_of_thoughts.py`](src/learning/tree_of_thoughts.py)
- **Paramètres** : profondeur 3, 2 branches/noeud, max 20 noeuds
- **5 outils** : `read_file`, `search_files`, `search_memory`, `rag_query`, `run_command`

```text
┌─────────────────────────────────────────────────────────┐
│              V16 — RAISONNEMENT (livrée ✅)              │
│  Self-Consistency · Chain of Thought · ToT Agentic      │
│  └─ Validation outil via [OUTIL: nom(args)]             │
╞═════════════════════════════════════════════════════════╡
│              V17 — MONITORING & BRANCHEMENTS ✅         │
│  RAMBudgetManager central · LoRA branché à l'inférence  │
│  Routes auto-rebuild · Factorisation embed              │
╞═════════════════════════════════════════════════════════╡
│              V16.4 — LORA RAG FINE-TUNING ✅            │
│  Dataset 384 ex · 2000 iters · 4 layers M1             │
│  Training 3h46 · Score éval 68% (20/29)                 │
╞═════════════════════════════════════════════════════════╡
│              V15 — OPTIMISATIONS (terminée ✅)           │
│  LoRA RAG · Speculative · KV Compression · RAM Budget   │
│  CI/CD · ROADMAP                                        │
╞═════════════════════════════════════════════════════════╡
│              V12 — FONDATIONS (stable)                  │
│  PersonaEngine · Privacy Layer · SleepCycleManager      │
│  ModelRouter · CostGuard · Pipeline vocal               │
└─────────────────────────────────────────────────────────┘
```

---

## What's inside — catalog of modules

NURU V17 — architecture **petits spécialistes orchestrés** (philosophie DeepSeek).

### 🧠 Cognitive core

| Module | Ce qu'il fait | Source |
|--------|---------------|--------|
| **Self-Consistency** ✅ | 3 votes TF-IDF, consensus scoring, seuil 0.25 calibré pour modèle 1.5B | [`src/learning/self_consistency.py`](src/learning/self_consistency.py) |
| **Chain of Thought** ✅ | Détection de complexité (7+ mots), raisonnement étape par étape, extraction réponse | [`src/learning/chain_of_thought.py`](src/learning/chain_of_thought.py) |
| **Tree of Thoughts Agentic** ✅ | BFS profondeur 3, 2 branches, validation par actions réelles (lecture fichier, RAG, mémoire, shell) | [`src/learning/tree_of_thoughts.py`](src/learning/tree_of_thoughts.py) |
| **PolicyEngine** | Seuils RAM/Reranker/Score centralisés. `should_rerank()`, `should_use_cloud()`, `route_from_score()`. | [`src/core/policies.py`](src/core/policies.py) |
| **PromptGuard** | Anti-injection — neutralise 50+ motifs, échappe délimiteurs, normalisation Unicode. | [`src/core/prompt_guard.py`](src/core/prompt_guard.py) |
| **StrictRAGGuard** | Modes STRICT/HYBRID/FREE. Bloque les réponses non-citées. | [`src/core/response_guard.py`](src/core/response_guard.py) |
| **EvidenceVerifier** | Valide chaque `[Source: X]` dans les chunks RAG injectés. | [`src/ai/verifier.py`](src/ai/verifier.py) |
| **DynamicPromptBuilder** | Construit le prompt dynamiquement selon intent/facts/procedures. | [`src/routing/prompt_builder.py`](src/routing/prompt_builder.py) |
| **ReflexionEngine** | Auto-évaluation post-réponse — calibre la confiance, ajuste le ton. | [`src/core/reflexion.py`](src/core/reflexion.py) |
| **ConfidenceCalibrator** | Calibration des scores de confiance sur les réponses. | [`src/core/confidence.py`](src/core/confidence.py) |

### 📚 Memory & learning

| Module | Ce qu'il fait | Source |
|--------|---------------|--------|
| **MemoryManager** | 4 mémoires unifiées : Episodic/Semantic/User/Error + WorkingMemory | `src/memory/manager.py` |
| **MemoryBridge** | Pont entre MemoryStore (legacy V3) et MemoryManager V9. | `src/memory_bridge.py` |
| **GoldMemory** | Corrections utilisateur persistantes. Recherche exacte ou embedding (seuil 0.92). | `src/gold_memory.py` |
| **PostSessionExtractor** | Extrait préférences/entités après chaque session → user_profile. | `src/extraction.py` |
| **User Profile** | Profil utilisateur seedé + faits persistants dans la mémoire cognitive. | `scripts/seed_user_profile.py` |
| **SelfConsistencyEngine** | 3 votes TF-IDF, clustering par similarité cosinus, consensus scoring. Réduit les hallucinations RAG de ~40%. | [`src/learning/self_consistency.py`](src/learning/self_consistency.py) |
| **ChainOfThoughtEngine** | Raisonnement étape par étape avec extraction réponse. Seuil d'activation : complexité >7 mots. | [`src/learning/chain_of_thought.py`](src/learning/chain_of_thought.py) |
| **TreeOfThoughtsEngine** | BFS profondeur 3, validation agentic via outils MCP/locaux. `[OUTIL: nom(args)]` déclenche une action réelle. | [`src/learning/tree_of_thoughts.py`](src/learning/tree_of_thoughts.py) |
| **Embed utils** (V17) | Factorisation `_embed_sync` — utilitaire partagé entre episodic/procedural/semantic/errors | `src/memory/_embed_utils.py` |

### 🔍 RAG hybride

| Module | Ce qu'il fait | Source |
|--------|---------------|--------|
| **RAGEngine** | Pipeline 2-passes — HyDE OR query rewriting, vector + FTS5, RRF, reranker conditionnel. | `src/rag_engine.py` |
| **MultiSearchOrchestrator** | Single source de search — vector + BM25 + grep + HyDE en parallèle, fusion par rangs. | `src/rag/multi_search.py` |
| **LoRA RAG Adapter** (V17) | Adaptateur LoRA chargé **automatiquement** au démarrage — corrigé V17 (n'était jamais appelé avant) | `src/llm_local.py` + `nuru_core.py:183` |
| **Speculative RAG** | Draft rapide + vérification différée pour latence < 500ms (Item 39). | `src/rag/speculative.py` |
| **HierarchicalChunker V2** | 4 niveaux (document/section/subsection/paragraph), max 4000 chars/chunk. | `src/rag/v2_chunking.py` |
| **HyDE** | Expansion hypothétique — génère passages fictifs pour mieux embedder. | `src/rag/hyde.py` |
| **Decomposer** | Décompose les queries multi-hop en sous-questions. | `src/rag/decomposer.py` |
| **FactChecker** | Vérification factuelle post-génération sur chunks sourcés. | `src/rag/fact_checker.py` |

### 🤖 Agent Loop

> ⚠️ **V17 : ce module n'est pas branché au pipeline conversationnel actif.** AgentOrchestrator, TaskPlanner, Executor, Verifier, Recovery et ResumeManager existent (~2000 lignes) mais ne sont pas importés par ConversationEngine ni par NuruCore. Conservé pour usage futur. Voir `src/agent/__init__.py`.

| Module | Ce qu'il fait | Source |
|--------|---------------|--------|
| **AgentOrchestrator** (⚠️ dormant) | ReAct (Thought-Action-Observation loop) avec mémoire. | `src/agent/orchestrator.py` |
| **TaskPlanner** (⚠️ dormant) | Décompose un objectif en steps exécutables. | `src/agent/planner.py` |
| **Executor** (⚠️ dormant) | Exécute les steps. Sandbox shell, approbation humaine pour actions risquées. | `src/agent/executor.py` |
| **Verifier** (⚠️ dormant) | Valide le résultat d'une exécution avant de continuer. | `src/agent/verifier.py` |
| **RecoveryEngine** (⚠️ dormant) | Reprend l'exécution après une erreur — diagnostique, retry, escalade. | `src/agent/recovery.py` |

### 🧩 Cloud routing

| Module | Ce qu'il fait | Source |
|--------|---------------|--------|
| **CloudLLM** | Multi-provider avec Circuit Breaker — OpenCode Zen primaire, OpenRouter/DeepSeek fallback. | `src/llm_cloud.py` |
| **LocalLLM** | MLX Phi-4-mini 4-bit. Keep-alive 5 min, déchargement auto si RAM critique. Support adapters LoRA. | `src/llm_local.py` |
| **ModelRouter** | Routage 6-niveaux (trivial, doc, web, RAG, complex, local), priorité cloud/local, recalcule auto après clé API (V17). | `src/routing/` |
| **TokenJuice** | Compression tokens -40% à -50% (regex). 0 coût d'inférence. | `src/token_juice.py` |

### 🎙️ Voice & vision

| Module | Ce qu'il fait | Source |
|--------|---------------|--------|
| **AudioEngine** | STT (mlx-whisper) + TTS (Piper/Kokoro). Auto-stop 15s. | `src/audio.py` |
| **OCR** | Tesseract + fallback cloud. Lecture d'images / scans. | `src/ocr.py` |

### 📊 Observability

| Module | Ce qu'il fait | Source |
|--------|---------------|--------|
| **RAMBudgetManager** (V17) | Source de vérité unique — monitoring périodique, éviction, callbacks `clear_reranker` + `_maybe_unload_embedder`. Seuils calibrés M1 8 Go. | `src/core/ram_budget.py` |
| **EventBus** | Bus d'événements thread-safe async. Singleton — utilisé pour la reconstruction auto des routes. | `src/core/events.py` |
| **TraceCollector** | Queue async des traces de session → `~/.nuru/traces.db`. | `src/learning/trace_collector.py` |
| **Optimizer** | Mining périodique des traces → improvements auto. | `src/learning/optimizer.py` |
| **Logs JSON** (V17) | Fichier `logs/nuru.jsonl` structuré avec correlation ID UUID pour débogage. | `src/infra/logging_setup.py` |

---

## Project structure

```text
nuru/
├── src/main.py                  # Entry point PySide6 — V17 ambient presence
├── cli.py                       # Entry point CLI
├── pyproject.toml               # Python ≥3.11 · pytest · pydantic · mlx-lm
├── bugs_sol.md                  # Tracker des bugs fixes (source de vérité)
├── config/
│   └── settings.yaml            # Config user (clés sensibles dans Keychain)
├── data/
│   └── adapters/rag/            # LoRA adapters.safetensors (V16.4 → branché V17)
├── src/
│   ├── nuru_core.py             # V17 NuruCore — init + routes + LoRA
│   ├── llm_local.py             # MLX Phi-4-mini + LoRA adapters (lora_active)
│   ├── llm_cloud.py             # OpenCode Zen / OpenRouter / DeepSeek
│   ├── rag_engine.py            # RAG factory + types
│   ├── routing/
│   │   ├── router.py            # ModelRouter unifié (clear_routes V17)
│   │   └── prompt_builder.py    # DynamicPromptBuilder
│   ├── core/
│   │   ├── orchestrator.py      # NuruOrchestrator — pipeline réel
│   │   ├── policies.py          # PolicyEngine — seuils centralisés
│   │   ├── prompt_guard.py      # Anti-injection
│   │   ├── response_guard.py    # StrictRAGGuard
│   │   ├── model_manager.py     # Cycle de vie modèles MLX (non branché)
│   │   ├── ram_budget.py        # RAMBudgetManager — monitoring unifié V17
│   │   ├── reflexion.py         # ReflexionEngine (auto-évaluation)
│   │   ├── confidence.py        # ConfidenceCalibrator
│   │   ├── events.py            # EventBus singleton (V17: api_keys_updated)
│   │   ├── exceptions.py        # Hiérarchie d'exceptions typées
│   │   └── query_context.py     # QueryContext avec correlation_id V17
│   ├── rag/
│   │   ├── multi_search.py      # Single source of truth retrieval
│   │   ├── v2_chunking.py       # Hierarchical chunker
│   │   ├── hyde.py              # Hypothetical Document Embeddings
│   │   ├── decomposer.py        # Multi-hop decomposition
│   │   ├── speculative.py       # Speculative RAG (Item 39)
│   │   ├── fact_checker.py      # Vérification post-génération
│   │   └── diagnostics.py       # Diagnostic persistant
│   ├── agent/                   # Agent Loop — ⚠️ DORMANT V17 (warning au démarrage)
│   ├── memory/
│   │   ├── manager.py           # MemoryManager V9
│   │   ├── _embed_utils.py      # V17 — utilitaire partagé d'embedding
│   │   ├── episodic.py          # Mémoire épisodique
│   │   ├── procedural.py        # Mémoire procédurale
│   │   ├── semantic.py          # Mémoire sémantique
│   │   └── errors.py            # Mémoire d'erreurs
│   ├── audio.py                 # STT/TTS
│   ├── ocr.py                   # Vision OCR
│   ├── tools/                   # ToolRegistry + SandboxShell
│   ├── infra/
│   │   └── logging_setup.py     # V17 — logs JSON structurés + rotation
│   ├── ui/                      # V17 ambient UI (PySide6)
│   └── learning/                # TraceCollector + Optimizer + 3 architectures raisonnement
├── logs/
│   └── nuru.jsonl               # V17 — logs applicatifs structurés
└── tests/
    ├── test_lora_adapter.py     # 6 tests — LoRA RAG adapter
    ├── test_naming_collisions.py# Anti-collision classes
    ├── test_memory.py           # Mémoires cognitives
    ├── test_router.py           # Routage 6-niveaux
    ├── test_orchestrator_pipeline.py # Pipeline complet
    └── ...                      # 37 fichiers, 953 tests
```

---

## Tests

| Suite | Tests | Commande |
|-------|-------|----------|
| Agent orchestrator | 47 | `unset PYTHONPATH && pytest tests/test_agent.py -v` |
| ArchonRefiner | 10 | `unset PYTHONPATH && pytest tests/test_archon_refiner.py -v` |
| File ops | 51 | `unset PYTHONPATH && pytest tests/test_file_ops.py -v` |
| Browser control | 80 | `unset PYTHONPATH && pytest tests/test_browser_ctrl.py -v` |
| Router | 200+ | `unset PYTHONPATH && pytest tests/test_router.py -v` |
| Orchestrator pipeline | 50+ | `unset PYTHONPATH && pytest tests/test_orchestrator_pipeline.py -v` |
| LoRA | 6 | `unset PYTHONPATH && pytest tests/test_lora_adapter.py -v` |
| **Total** | **953 passed** | `unset PYTHONPATH && pytest tests/ -v` |

> `unset PYTHONPATH` évite que l'environnement Hermes (Python 3.11) ne fournisse des extensions numpy/pydantic compilées incompatibles avec Python 3.13.

---

## Contributing

NURU est **un projet personnel de Leblanc BAHIGA Mudarhi** — ingénieur agronome et informaticien travaillant dans les chaînes de valeur agricoles en Afrique centrale et orientale (IITA, FAO, USAID). Pas ouvert aux contributions externes pour le moment.

- **Issues** : ouvrez sur GitHub
- **Discussions** : pour les questions d'architecture

Code sous licence MIT — voir [`LICENSE`](LICENSE).

---

## Built on the shoulders of

- **Apple MLX** — framework MLX qui rend Phi-4-mini viable sur M1
- **Microsoft** — **Phi-4-mini-instruct-4bit** (3.8B params)
- **OpenCode Zen / Groq / OpenRouter / DeepSeek** — couche cloud optionnelle
- **Stanford SAIL** — inspirations architecturales OpenJarvis
- **HuggingFace** — hébergement des modèles et embeddings

---

## License

MIT. Voir [`LICENSE`](LICENSE).

---

*Document mis à jour le 22 juillet 2026 — NURU V17 — Monitoring & Branchements ✅ — LoRA chargé à l'inférence — 953 tests passent ✅*
