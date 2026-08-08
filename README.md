<div align="center">

<img src="src/ui/assets/Gemini_Generated_Image_35cdt735cdt735cd_transparent.png" width="160" alt="NURU V18.1"/>

<br/>

# 🌀 NURU — Personal Cognitive OS

<i>De l'assistant IA agentic au système d'exploitation cognitif personnel.<br/>
Conçu pour tourner en local d'abord, sur un MacBook Pro M1 de 8 Go de RAM unifiée.</i>

<br/>

<p>
  <img src="https://img.shields.io/badge/V18.1-Active-00D4FF?style=for-the-badge&logo=probot" alt="V18.1 Active"/>
  <img src="https://img.shields.io/badge/Platform-macOS%20M1%208GB-39FF14?style=for-the-badge&logo=apple&logoColor=white" alt="macOS M1 8GB"/>
  <img src="https://img.shields.io/badge/LLM-Phi--4--mini%20(MLX)-FFB000?style=for-the-badge" alt="LLM Phi-4-mini"/>
  <img src="https://img.shields.io/badge/Tests-1076%20executes-8B5CF6?style=for-the-badge" alt="1076 tests"/>
  <img src="https://img.shields.io/badge/Contrat%20V18-41%20decisions-FF6B6B?style=for-the-badge" alt="Contrat V18"/>
  <img src="https://img.shields.io/badge/Architecture-Kernel%20%2B%20Pipeline%20Engine-8B5CF6?style=for-the-badge" alt="Kernel"/>
</p>

</div>

<br/>

---

## Why NURU?

La plupart des assistants IA promettent d'être "personnels". Leur implémentation concrète : ils envoient vos prompts vers un serveur cloud qui appartient à quelqu'un d'autre. Le "personnel" est dans le marketing, pas dans l'architecture.

NURU part du postulat inverse — **le personnel commence par l'exécution locale**. Le routeur envoie les requêtes simples vers **Phi-4-mini (4-bit MLX)** qui tourne sur le GPU M1. Le cloud — OpenCode Zen (primaire), Groq, OpenRouter, DeepSeek — n'est contacté que **quand c'est vraiment nécessaire** (questions d'actualité, tâches que le local ne sait pas tenir, ou RAM sous le seuil critique).

Ce qui rend NURU différent d'un wrapper LLM local :

- **Système d'exploitation cognitif**, pas chatbot — la mémoire (Episodic/Semantic/User/Error), le sommeil (SleepCycleManager 3 phases light/deep/REM), et la persona (PersonaEngine) sont des citoyens de première classe du système, pas des add-ons.
- **Architecture Kernel** (V16+) — `NuruKernel` : point d'entrée unique, services enregistrés dans un `ServiceRegistry`, accès par `kernel.get('nom')`, cycle de vie géré (boot → services → shutdown). Le Kernel ne répond jamais — il orchestre.
- **Pipeline Engine composable** (V16+) — ReceiveQuestion → Route → Retrieve → BuildContext → Generate → Validate → Respond. Chaque étape est un step isolé qui accède aux services via le kernel.
- **Philosophie DeepSeek** — petits spécialistes orchestrés > monolithe. KV Cache Compression, speculative decoding, RAM budget manager.
- **Privacy Layer** + opt-in granulaire par capteur (voix, vision écran, calendrier). Zéro fuite par défaut.
- **Pipeline vocal local** (STT/TTS/VAD/wake word), présence animée Z.ai-style.
- **Monitoring RAM unifié** — `RAMBudgetManager` central avec boucle périodique, éviction contextuelle, callback `clear_reranker` / `_maybe_unload_embedder`.

Le but est simple : **vivre avec un JARVIS personnel sur la machine qu'on a déjà**, sans céder ses données à chaque requête.

---

## Installation

```bash
git clone https://github.com/leblancbahiga/Assistant-IA.git
cd Assistant-IA
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Configuration des clés API dans votre Keychain macOS (jamais dans le repo) :

```bash
# Une seule fois
security add-generic-password -a nuru -s com.nuru.assistant/groq -w "VOTRE_CLE_GROQ"
security add-generic-password -a nuru -s com.nuru.assistant/openrouter -w "VOTRE_CLE_OPENROUTER"
security add-generic-password -a nuru -s com.nuru.assistant/deepseek -w "VOTRE_CLE_DEEPSEEK"
security add-generic-password -a nuru -s com.nuru.assistant/opencode_zen -w "VOTRE_CLE_OPENCODE_ZEN"
```

Pré-requis validés :
- **macOS 13+** sur architecture Apple Silicon (M1/M2/M3)
- **8 Go de RAM unifiée** minimum — conçu spécifiquement pour ce budget
- **Python 3.13** (recommandé) ou ≥3.11
- HuggingFace CLI actif (`huggingface-cli login`) pour le téléchargement initial des modèles MLX (~3.5 Go) — NURU tourne ensuite en **mode offline forcé** (`HF_HUB_OFFLINE=1`)

---

## Quick Start

```bash
# Lancer NURU (nouvelle UI)
python3 run.py

# Ancienne UI (AmbientApp)
python3 run.py --legacy

# Réindexation des documents
python3 reindex_all.py

# Tests
unset PYTHONPATH && .venv/bin/python -m pytest tests/ -v
```

| Commande | Effet |
|----------|-------|
| `python3 run.py` | Nouvelle UI (par défaut, flag `USE_NEW_UI` dans `src/config.py`) |
| `python3 run.py --legacy` | Ancienne UI ambient (tray + floating widget + orb) |
| `python3 reindex_all.py` | Indexe tous les documents du workspace |
| `unset PYTHONPATH && pytest tests/` | Suite complète — 1076 tests exécutés (1100 collectés − 24 désélectionnés) |

> **Note :** `unset PYTHONPATH` nécessaire pour éviter que l'environnement Hermes (Python 3.11) ne pollue le venv Python 3.13 avec ses dépendances compilées incompatibles. `run.py` purge lui-même PYTHONPATH et force `HF_HUB_OFFLINE=1` au démarrage.

---

## V18.1 — État actuel (août 2026)

NURU est gouverné par un **contrat d'architecture** : [`V18.md`](V18.md) — 41 décisions validées (V18-01 → V18-41, dont 34a/b) issues de 6 rapports d'audit expert (~17 650 lignes), analysés et débattus contradictoirement (rounds 1-7 + avis croisés Round A, 6 revues indépendantes).

| Élément | État |
|:--------|:-----|
| **Contrat V18** | 41 décisions ENGAGÉES, traçabilité complète (rapport → débat → V18.md → commit) |
| **V18-13** (nettoyage template mort) | ✅ Implémenté (`295c064`) — prérequis bloquant de V18-24 |
| **V18-24** (rebranchement prompt système RAG) | ✅ Implémenté (`9eab913`) — via `build_system_prompt`, A/B en attente |
| **V18.1 C1** (services fantômes) | ✅ Implémenté (`aefa2fb`) — `archon_refiner` / `trace_collector` débranchés proprement (logger.warning throttlé au lieu de try/except silencieux + coroutine jetée) |
| **Reste du contrat** | ⏸️ En attente d'implémentation — ordre et dépendances formalisés dans V18.md §1 |
| **Checklist** | [`CHECKLIST_V18_IMPLEMENTATION.md`](CHECKLIST_V18_IMPLEMENTATION.md) — source de vérité d'implémentation |
| **Problèmes connus** | [`PROBLEMES_NURU.md`](PROBLEMES_NURU.md) — registre P1-P16 (hallucinations, répétition, RAM, outils non branchés…) |
| **Contrat d'équipe** | [`AGENTS.md`](AGENTS.md) — 27 règles + gouvernance pour l'équipe d'agents Hermes (lead/architect/coder/tester/reviewer) |

### Priorités contractuelles en attente (extrait)

- **V18-01** — Reranker multilingue MLX natif direct (Qwen3-Reranker-0.6B-mxfp8 / jina-reranker-v3-4bit), suppression de l'étape PyTorch (mmarco absent du cache HF + offline forcé → étape inexécutable).
- **V18-02** — État RAG typé `has_valid_evidence` calculé après rerank, migration par couche (7 fichiers / 17 sites).
- **V18-27** — Budget GPU Metal dynamique `mlx_budget = max(1.0, available_Go - 0.5)` + bascule cloud forcée sur OOM.
- **V18-31** — Fast-Fail RAG vide indépendant du mode (refus immédiat pour `intent == "RAG"` sans contexte).
- **V18-40 (P0)** — SQLite sync → `asyncio.to_thread` (l'event loop est bloqué pendant chaque recherche RAG → freezes UI).
- **V18-41** — Contrat de performance : swap < 85 %, TTFT < 30 s, recall@5 ≥ 85 %, zéro hallucination sourcée = la définition de « V18 livré ».

---

## LoRA RAG — DÉSACTIVÉ (décision V17.4 définitive)

> **État réel : `config/settings.yaml` → `lora_adapter_enabled: false`.** Le modèle base Phi-4-mini répond seul. L'annonce historique « LoRA branché à l'inférence » est **obsolète** — l'adaptateur entraîné produisait des réponses contaminées (dataset v1/v2 à 100 % de meta-discours) et a été **définitivement désactivé** (`aa818c5`).

Ce qui reste utile de l'expérience LoRA (documenté pour référence) :

- L'infrastructure est intacte : `llm_local.py` expose `set_lora_adapter()` / `lora_active`, `config.lora_adapter_path` pointe vers `data/adapters/rag`.
- Le dataset historique était la cause racine : réponses à structure fixe (meta-discours) → boucles absurdes. Un éventuel ré-entraînement ne se fera que sur des réponses **naturelles** sourcées, jamais sur des templates.
- `rep_penalty 1.15` + `SAMPLING_PROFILES` (audit B-3) sont actifs pour le modèle base.

### Pipeline d'entraînement historique (V16.4, référence)

```text
RAG chunks (3993) → build_large_dataset.py → train.jsonl (384 ex, 18% piège)
                                                   └→ valid.jsonl (16 ex, 25% piège)
                                                         ↓
                                              lora_train.py V16.4
                                        Phi-4-mini-instruct-4bit (MLX)
                                            2000 iters, 4 layers, 1024 seq
                                                         ↓
                                          adapters.safetensors (1.44M params)
                                          val loss 1.155 · 3h46 sur M1 8 Go
```

---

## Architecture — Kernel & Pipeline (V16+)

### NuruKernel

```python
# src/kernel/kernel.py — point d'entrée unique, singleton
kernel.register("rag_engine", self.rag)      # ServiceRegistry
kernel.register("local_llm", self.local_llm)
rag = kernel.get("rag_engine")               # accès par nom, pas d'import direct
```

Le Kernel gère le cycle de vie complet : boot → enregistrement des services → shutdown (`ServiceRegistry.stop_all`). Les ~22 services réels sont enregistrés dans `nuru_core.py` : `state`, `metrics`, `resources`, `kernel_router`, `scheduler`, `cache`, `cloud_llm`, `rag_engine`, `router`, `web_search`, `local_llm`, `memory`, `audio`, `context_budget`, `runtime`, `event_bus`, `ingestion`, `orchestrator`, `rag_pipeline`, `response_guard`, `session_store`, `llm_gen`…

### Pipeline Engine

```text
ReceiveQuestion → Route → Retrieve → BuildContext → Generate → Validate → Respond
```

`src/kernel/pipeline_steps.py` — chaque step est composable et accède aux services via `kernel.get()` (pas de dépendance directe à l'orchestrateur). Le flux réel d'une requête : normalisation + session → routage (intent) → RAG hybride + fallback web → assemblage du contexte (gardes, compression) → génération (ToT/CoT/Self-Consistency/streaming) → validation (StrictRAG, mémoire) → réponse UI.

### Monitoring RAM unifié (V17)

| Système | Rôle |
|:--------|:-----|
| **RAMBudgetManager** | Source de vérité unique — monitoring périodique + callbacks + éviction (`src/core/ram_budget.py`) |
| **RAMMonitor** | Déjà inerte (start commenté depuis V17) — suppression validée V18-29 |
| **model_manager.py** | Cycle de vie MLX conservé utilisable |

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

### Pipeline décisionnel

```text
Requête →
  ├─ "tot:" / goal P0 + 15+ mots ───→ 🌳 Tree of Thoughts (agentic)
  ├─ COMPLEX / RAG complexe (>7 mots) → 💭 Chain of Thought
  ├─ RAG + confiance HAUTE/MOYENNE ──→ 🗳️ Self-Consistency (3 votes)
  └─ SIMPLE ──────────────────────────→ Streaming direct
```

- **Self-Consistency** — 3 échantillons, clustering TF-IDF, cluster majoritaire. Seuil 0.25 calibré sur modèle local. Module : `src/learning/self_consistency.py`.
- **Chain of Thought** — décomposition transparente pour 7+ mots + patterns (`explique`, `compare`, `analyse`…). Module : `src/learning/chain_of_thought.py`.
- **Tree of Thoughts Agentic** — BFS profondeur 3, 2 branches, validation par actions réelles via `[OUTIL: nom(paramètres)]` (lecture fichier, RAG, mémoire, shell sécurisé). Module : `src/learning/tree_of_thoughts.py`.

```text
┌─────────────────────────────────────────────────────────┐
│              V18.1 — CONTRAT D'ARCHITECTURE ✅          │
│  41 décisions V18-01→41 · débats rounds 1-7 + Round A   │
│  V18-13 ✅ V18-24 ✅ C1 services fantômes ✅             │
╞═════════════════════════════════════════════════════════╡
│              V18 — STABILISATION (en cours)             │
│  Reranker MLX · état RAG typé · budget Metal dynamique  │
│  Fast-Fail · SQLite to_thread · contrat de performance  │
╞═════════════════════════════════════════════════════════╡
│              V17.x — MONITORING & CORRECTIFS ✅         │
│  RAMBudgetManager central · SAMPLING_PROFILES · routes  │
│  LoRA désactivé définitivement (V17.4)                  │
╞═════════════════════════════════════════════════════════╡
│              V16 — RAISONNEMENT (livrée ✅)             │
│  Self-Consistency · Chain of Thought · ToT Agentic      │
╞═════════════════════════════════════════════════════════╡
│              V12 — FONDATIONS (stable)                  │
│  PersonaEngine · Privacy Layer · SleepCycleManager      │
│  ModelRouter · CostGuard · Pipeline vocal               │
└─────────────────────────────────────────────────────────┘
```

---

## What's inside — catalog of modules

NURU V18.1 — architecture **Kernel + petits spécialistes orchestrés** (philosophie DeepSeek).

### 🧠 Cognitive core

| Module | Ce qu'il fait | Source |
|--------|---------------|--------|
| **NuruKernel** | Façade centrale, singleton. Enregistre les services, gère boot/shutdown, répond par `kernel.get()`. | `src/kernel/kernel.py` |
| **PipelineEngine** | Steps composables ReceiveQuestion → Route → Retrieve → BuildContext → Generate → Validate → Respond. | `src/kernel/pipeline.py` + `pipeline_steps.py` |
| **ServiceRegistry** | Registre des ~22 services + lifecycle adaptatif (stop → close → cleanup → unload, V18-26). | `src/kernel/registry.py` |
| **Self-Consistency** ✅ | 3 votes TF-IDF, consensus scoring, seuil 0.25 calibré. | `src/learning/self_consistency.py` |
| **Chain of Thought** ✅ | Détection de complexité (7+ mots), raisonnement étape par étape. | `src/learning/chain_of_thought.py` |
| **Tree of Thoughts Agentic** ✅ | BFS profondeur 3, validation par actions réelles (fichier, RAG, mémoire, shell). | `src/learning/tree_of_thoughts.py` |
| **PromptGuard** | Anti-injection — neutralise 50+ motifs, échappe délimiteurs, normalisation Unicode. | `src/core/prompt_guard.py` |
| **StrictRAGGuard** | Modes STRICT/HYBRID/FREE. Bloque les réponses non-citées. | `src/core/response_guard.py` |
| **EvidenceVerifier** | Valide chaque `[Source: X]` dans les chunks RAG injectés. | `src/ai/verifier.py` |
| **DynamicPromptBuilder** | Construit le prompt dynamiquement selon intent/facts/procedures. | `src/routing/prompt_builder.py` |
| **ReflexionEngine** | Auto-évaluation post-réponse — calibre la confiance, ajuste le ton. | `src/learning/reflexion_engine.py` |
| **ConfidenceCalibrator** | Calibration des scores de confiance sur les réponses. | `src/learning/confidence_calibrator.py` |
| **PolicyEngine** | Seuils RAM/Reranker/Score centralisés. ⚠️ `should_rerank()` orpheline (0 appel) — gelée V18-21. | `src/core/policies.py` |

### 📚 Memory & learning

| Module | Ce qu'il fait | Source |
|--------|---------------|--------|
| **MemoryManager** | 4 mémoires unifiées : Episodic/Semantic/User/Error + WorkingMemory | `src/memory/manager.py` |
| **GoldMemory** | Corrections utilisateur persistantes. Recherche exacte ou embedding (seuil 0.92). | `src/gold_memory.py` |
| **PostSessionExtractor** | Extrait préférences/entités après chaque session → user_profile. | `src/extraction.py` |
| **Embed utils** | Utilitaire d'embedding partagé entre episodic/procedural/semantic/errors | `src/memory/_embed_utils.py` |
| **TraceCollector** | ⚠️ V18.1 C1 : débranché du pipeline actif (coroutine jetée corrigée) — conservé pour mining futur. | `src/learning/trace_collector.py` |
| **Optimizer** | Mining périodique des traces → improvements auto. | `src/learning/optimizer.py` |

### 🔍 RAG hybride

| Module | Ce qu'il fait | Source |
|--------|---------------|--------|
| **RAGEngine** | Pipeline 2-passes — HyDE OR query rewriting, vector + FTS5, RRF, reranker conditionnel. | `src/rag_engine.py` |
| **MultiSearchOrchestrator** | Single source de search — vector + BM25 + grep + HyDE en parallèle, fusion par rangs. | `src/rag/multi_search.py` |
| **Reranker** | Cross-encoder `ms-marco-MiniLM-L-6-v2` (EN-only, 88 Mo, en cache) — ⏸️ bascule MLX natif multilingue prévue V18-01. | `src/reranker.py` |
| **Speculative RAG** | Draft rapide + vérification différée pour latence < 500ms. | `src/rag/speculative.py` |
| **HierarchicalChunker V2** | 4 niveaux (document/section/subsection/paragraph), max 4000 chars/chunk. | `src/rag/v2_chunking.py` |
| **HyDE** | Expansion hypothétique — génère passages fictifs pour mieux embedder. | `src/rag/hyde.py` |
| **Decomposer** | Décompose les queries multi-hop en sous-questions. | `src/rag/decomposer.py` |
| **FactChecker** | Vérification factuelle post-génération sur chunks sourcés. | `src/rag/fact_checker.py` |
| **QueryRewriter** | Rewriting cloud (cooldown post-échec) — ⏸️ gate offline V18-06. | `src/query_rewriter.py` |

> **État typé RAG** (V18-02, en attente) : le marqueur texte « AUCUNE SOURCE » sera remplacé par un booléen `has_valid_evidence` calculé une seule fois après le rerank, lu par toutes les couches en aval.

### 🧩 Cloud routing

| Module | Ce qu'il fait | Source |
|--------|---------------|--------|
| **CloudLLM** | Multi-provider avec Circuit Breaker — OpenCode Zen primaire, OpenRouter/DeepSeek fallback. | `src/llm_cloud.py` |
| **LocalLLM** | MLX Phi-4-mini 4-bit. Keep-alive 120 s, déchargement auto si RAM critique. Thread d'inférence dédié (`_mlx_executor`). | `src/llm_local.py` |
| **ModelRouter** | Routage 6-niveaux (trivial, doc, web, RAG, complex, local), priorité cloud/local. | `src/routing/` |
| **HybridStrategy** | Enum `local_only|verify|plan|rag` legacy — ⏸️ réalignement 3 modes réels prévu V18-25. | `src/routing/router.py` |

### 🎙️ Voice & vision

| Module | Ce qu'il fait | Source |
|--------|---------------|--------|
| **AudioEngine** | STT (mlx-whisper) + TTS (Piper/Kokoro). Auto-stop 15s. | `src/audio.py` |
| **OCR** | Tesseract + fallback cloud. Lecture d'images / scans. | `src/ocr.py` |
| **Vision / Voice** | Modules dédiés (dossiers `src/vision/`, `src/voice/`). | `src/vision/`, `src/voice/` |

### 📊 Observability

| Module | Ce qu'il fait | Source |
|--------|---------------|--------|
| **RAMBudgetManager** | Source de vérité unique — monitoring périodique, éviction, callbacks. Seuils calibrés M1 8 Go. | `src/core/ram_budget.py` |
| **EventBus** | Bus d'événements thread-safe async. Singleton. | `src/core/events.py` |
| **KernelMetrics / KernelState** | Métriques et état exposés par le kernel aux vues UI (signaux `metrics_updated`). | `src/kernel/metrics.py`, `src/kernel/state.py` |
| **Logs JSON** | Fichier `logs/nuru.jsonl` structuré avec correlation ID UUID. | `src/infra/logging_setup.py` |

### 🤖 Agent Loop & outils

> ⚠️ **Non branchés au pipeline conversationnel actif.** `AgentOrchestrator`, TaskPlanner, Executor, Verifier, Recovery existent (~2000 lignes) mais ne sont pas importés par le pipeline Kernel. Le step `Act` (branchage de `ToolRegistry`, 22 outils) est **gaté off par défaut** — planifié V18.1 (V18-09/10/11). `src/tools/` est complet mais jamais connecté au pipeline.

---

## Project structure

```text
nuru/
├── run.py                       # Entry point unique V16+ (purge PYTHONPATH, HF_HUB_OFFLINE=1)
├── pyproject.toml               # Python ≥3.11 · pytest · pydantic · mlx-lm
├── AGENTS.md                    # Contrat d'ingénierie équipe Hermes (27 règles)
├── V18.md                       # CONTRAT D'ARCHITECTURE — 41 décisions engagées
├── CHECKLIST_V18_IMPLEMENTATION.md  # Source de vérité d'implémentation
├── PROBLEMES_NURU.md            # Registre des problèmes P1-P16
├── bugs_sol.md                  # Tracker historique des bugs fixes
├── config/
│   └── settings.yaml            # Config user (clés sensibles dans Keychain)
├── data/
│   └── adapters/rag/            # LoRA DÉSACTIVÉ (lora_adapter_enabled: false)
├── src/
│   ├── kernel/                  # Noyau — kernel.py, pipeline.py, pipeline_steps.py,
│   │                            # registry.py, resources.py, scheduler.py, state.py, metrics.py
│   ├── nuru_core.py             # Boot du kernel + enregistrement des ~22 services
│   ├── llm_local.py             # MLX Phi-4-mini (thread dédié, keep-alive 120s)
│   ├── llm_cloud.py             # OpenCode Zen / OpenRouter / DeepSeek
│   ├── rag_engine.py            # RAG factory + types
│   ├── routing/                 # ModelRouter + DynamicPromptBuilder
│   ├── core/                    # ram_budget, policies, prompt_guard, response_guard,
│   │                            # orchestrator (legacy), events, exceptions, query_context
│   ├── rag/                     # multi_search, v2_chunking, hyde, decomposer,
│   │                            # speculative, fact_checker, query_rewriter, diagnostics
│   ├── agent/                   # Agent Loop — ⚠️ dormant (step Act gaté off)
│   ├── memory/                  # manager + episodic/procedural/semantic/errors + _embed_utils
│   ├── learning/                # self_consistency, chain_of_thought, tree_of_thoughts,
│   │                            # reflexion_engine, confidence_calibrator, trace_collector, optimizer
│   ├── tools/                   # ToolRegistry + SandboxShell — ⚠️ jamais branché au pipeline
│   ├── ui/                      # app.py, main_window, conversation_surface, floating_widget…
│   ├── mcp/                     # MCPServer/MCPClient — gel V18-21
│   ├── vision/ voice/ personality/ privacy/ security/ research/ session/
│   │   ingestion/ knowledge/ proactive/ orchestration/ observability/ plugins/ models/
│   └── infra/                   # logging_setup (logs JSON + rotation)
├── logs/
│   └── nuru.jsonl               # Logs applicatifs structurés
└── tests/                       # 45 fichiers
    ├── test_c1_ghost_services.py    # V18.1 C1 — 4 tests (débranchement propre)
    ├── test_lora_adapter.py         # 6 tests — LoRA adapter
    ├── test_memory.py               # Mémoires cognitives
    ├── test_router.py               # Routage 6-niveaux
    └── ...
```

---

## Tests

**État vérifié le 8 août 2026** : 1100 tests collectés, **24 désélectionnés** via `pyproject.toml` (`addopts`) → 1076 exécutés. La réactivation progressive des tests désélectionnés est planifiée (V18-33, après le benchmark V18-15).

| Suite | Tests | Commande |
|-------|-------|----------|
| **Total exécuté** | **1076** | `unset PYTHONPATH && .venv/bin/python -m pytest tests/ -v` |
| Collectés (avec désélectionnés) | 1100 | `pytest tests/ --collect-only` |
| C1 ghost services (V18.1) | 4 | `pytest tests/test_c1_ghost_services.py -v` |
| LoRA | 6 | `pytest tests/test_lora_adapter.py -v` |

> **Échecs connus au 8 août 2026 (9)** : `test_rag_scoring.py::test_confidence_label_*` (×3, seuils à recalibrer), `test_lora_adapter.py::TestLoRAConfig::test_load_*` (×3, comportement adapter désactivé), `test_shell_exec.py` (×2, sandbox shell), `test_integration.py::test_generate_streaming`. Chacun tracé dans PROBLEMES_NURU.md — aucun n'est masqué.
>
> `unset PYTHONPATH` évite que l'environnement Hermes (Python 3.11) ne fournisse des extensions numpy/pydantic compilées incompatibles avec Python 3.13.

---

## Références d'audit

Le travail V18 est adossé à un corpus d'audit externe consultable (dossier `~/Downloads/audit/`) :

- 8 rapports d'audit NURU V16/V17 (dont `AUDIT_NURU_EXPERT_2026-08-06_*.md`)
- 6 analyses assistant (`ANALYSE_AUDIT_1..6_2026-08-06.md`) — chaque recommandation vérifiée code-à-code
- Débats contradictoires rounds 1-7 + avis croisés Round A (6 revues indépendantes) — arbitrages dans `~/Downloads/Rapport audit/revue/` (`ARBITRAGE_REVUE1..6_2026-08-08.md`)
- Verdict global Round A : **FEU VERT 6/6** (CG 9.4/10), conditions de gouvernance intégrées au contrat

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

*Document mis à jour le 8 août 2026 — NURU V18.1 — Contrat d'architecture 41 décisions · V18-13 ✅ V18-24 ✅ · Services fantômes débranchés · LoRA désactivé · 1076 tests exécutés*
