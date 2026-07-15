<div align="center">

<img src="src/ui/assets/Gemini_Generated_Image_35cdt735cdt735cd_transparent.png" width="160" alt="NURU V15"/>

<br/>

# 🌀 NURU — Personal Cognitive OS

<i>De l'assistant IA agentic au système d'exploitation cognitif personnel.<br/>
Conçu pour tourner en local d'abord, sur un MacBook Pro M1 de 8 Go de RAM unifiée.</i>

<br/>

<p>
  <a href="NURU_V9.md"><img src="https://img.shields.io/badge/V15%20Spec-NURU_V9.md-00D4FF?style=for-the-badge" alt="V15 Spec"/></a>
  <a href="NURUV15.md"><img src="https://img.shields.io/badge/V15%20Consolidation-NURUV15.md-a855f7?style=for-the-badge" alt="V15 Consolidation"/></a>
  <img src="https://img.shields.io/badge/Platform-macOS%20M1%208GB-39FF14?style=for-the-badge&logo=apple&logoColor=white" alt="macOS M1 8GB"/>
  <img src="https://img.shields.io/badge/LLM-Phi--4--mini%20(MLX)-FFB000?style=for-the-badge" alt="LLM Phi-4-mini"/>
  <img src="https://img.shields.io/badge/Tests-151%20tests-success?style=for-the-badge" alt="151 tests"/>
  <img src="https://img.shields.io/badge/V15%20Phase%205-%E2%9C%85-success?style=for-the-badge" alt="Phase 5 done"/>
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
- **Python 3.11** ou supérieur
- HuggingFace CLI actif (`huggingface-cli login`) pour le téléchargement initial des modèles MLX (~3.5 Go)

---

## Quick Start

```bash
# Lancer le dashboard V12 (présence ambiante Z.ai — tray + floating widget)
python3 run_v12.py

# Chat CLI simple (léger, sans UI)
python3 cli.py

# Réindexation des documents
python3 reindex_all.py

# Tests
PYTHONPATH="" python3 -m pytest tests/ --ignore=tests/test_memory.py -v
```

| Commande | Effet |
|----------|-------|
| `python3 run_v12.py` | Interface ambiante V12 (tray icon + floating widget + orb animé) |
| `python3 cli.py` | Mode terminal pour usage SSH / serveur headless |
| `python3 reindex_all.py` | Indexe tous les documents du workspace |
| `PYTHONPATH="" pytest tests/` | Suite complète — 151 tests (RAG, agent, mémoire, router, KV cache) |

> **Note :** `PYTHONPATH=""` nécessaire à cause d'un conflit entre venv Python 3.13 et pydantic_core du système 3.11.

---

## V15 Phase 5 — Optimisations DeepSeek (terminée ✅)

V15 Phase 5 délivre 7 items d'optimisation sur le thème **DeepSeek-like efficiency** — petits spécialistes orchestrés qui tirent le maximum des 8 Go RAM.

| Item | Description | Effort | Statut |
|------|-------------|--------|--------|
| 38 | **LoRA-MoE adaptateur RAG** — Adapter LoRA spécifique pour le contexte RAG, chargé/déchargé à la volée | 1 sem | ✅ |
| 39 | **Speculative RAG** — Draft RAPID + vérification différée pour latence < 500ms | 1 sem | ✅ |
| 40 | **RAM Budget Manager** — Budget centralisé Go·s, déchargement forcé, seuils calibrés M1 8 Go | 3 j | ✅ |
| 41 | **KV Cache Persistant** — Cache clé/valeur sauvegardé sur disque pour reprise rapide | 5 j | ✅ |
| **42** | **KV Cache Compression (style MLA)** — Quantification int8 per-token + fenêtrage contextuel. -50% RAM | **2 sem** | **✅** |
| 43 | **CI/CD GitHub Actions** — Lint (black, isort) + test (pytest) sur Python 3.11/3.13 | 1 sem | ✅ |
| 44 | **ROADMAP.md à jour** | 1h | ✅ |

### KV Cache Compression — highlight technique

Le module `src/cache/kv_compress.py` implémente une quantification int8 per-token style Multi-head Latent Attention (MLA) :

- **`quantize_kv_cache()`** — fp16 → uint8 per-token avec `min`/`scale` par élément
- **`dequantize_kv_cache()`** — restore transparent (ratio SNR mesuré > 40 dB)
- **`window_kv_cache()`** — fenêtrage glissant N tokens (défaut : 2048)
- **`compression_stats()`** — rapport économie en temps réel

Économie : **~50 %** en int8 pur, jusqu'à **~75 %** combiné avec fenêtrage.
Swap M1 8 Go : de 90% → objectif ~50%.

---

## What's inside — catalog of modules

NURU V15 — architecture **petits spécialistes orchestrés** (philosophie DeepSeek).

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

### 🔍 RAG hybride

| Module | Ce qu'il fait | Source |
|--------|---------------|--------|
| **RAGEngine** | Pipeline 2-passes — HyDE OR query rewriting, vector + FTS5, RRF, reranker conditionnel. | `src/rag_engine.py` |
| **MultiSearchOrchestrator** | Single source de search — vector + BM25 + grep + HyDE en parallèle, fusion par rangs. | `src/rag/multi_search.py` |
| **LoRA RAG Adapter** | Adapter LoRA chargé/déchargé à la volée sur le contexte RAG (Item 38). | `src/llm_local.py` |
| **Speculative RAG** | Draft rapide + vérification différée pour latence < 500ms (Item 39). | `src/rag/speculative.py` |
| **HierarchicalChunker V2** | 4 niveaux (document/section/subsection/paragraph), max 4000 chars/chunk. | `src/rag/v2_chunking.py` |
| **HyDE** | Expansion hypothétique — génère passages fictifs pour mieux embedder. | `src/rag/hyde.py` |
| **Decomposer** | Décompose les queries multi-hop en sous-questions. | `src/rag/decomposer.py` |
| **FactChecker** | Vérification factuelle post-génération sur chunks sourcés. | `src/rag/fact_checker.py` |

### 💾 Cache & compression

| Module | Ce qu'il fait | Source |
|--------|---------------|--------|
| **KVPersistentCache** | Cache clé/valeur persistant sur disque avec save/load. | `src/cache/kv_cache.py` |
| **KVCompress** | Quantification int8 per-token + fenêtrage contextuel. Économie 50-75% RAM. | `src/cache/kv_compress.py` |

### 🤖 Agent Loop

| Module | Ce qu'il fait | Source |
|--------|---------------|--------|
| **AgentOrchestrator** | ReAct (Thought-Action-Observation loop) avec mémoire. | `src/agent/orchestrator.py` |
| **TaskPlanner** | Décompose un objectif en steps exécutables. | `src/agent/planner.py` |
| **Executor** | Exécute les steps. Sandbox shell, approbation humaine pour actions risquées. | `src/agent/executor.py` |
| **Verifier** | Valide le résultat d'une exécution avant de continuer. | `src/agent/verifier.py` |
| **RecoveryEngine** | Reprend l'exécution après une erreur — diagnostique, retry, escalade. | `src/agent/recovery.py` |
| **ToolRegistry** | Catalogue des tools — shell, navigateur, fichiers, calendrier. | `src/tools/registry.py` |

### 🧩 Cloud routing

| Module | Ce qu'il fait | Source |
|--------|---------------|--------|
| **CloudLLM** | Multi-provider avec Circuit Breaker — Groq primaire, OpenRouter/DeepSeek fallback. | `src/llm_cloud.py` |
| **LocalLLM** | MLX Phi-4-mini 4-bit. Keep-alive 5 min, déchargement auto si RAM critique. Support adapters LoRA. | `src/llm_local.py` |
| **TokenJuice** | Compression tokens -40% à -50% (regex). 0 coût d'inférence. | `src/token_juice.py` |

### 🎙️ Voice & vision

| Module | Ce qu'il fait | Source |
|--------|---------------|--------|
| **AudioEngine** | STT (mlx-whisper) + TTS (Piper/Kokoro). Auto-stop 15s. | `src/audio.py` |
| **OCR** | Tesseract + fallback cloud. Lecture d'images / scans. | `src/ocr.py` |

### 📊 Observability

| Module | Ce qu'il fait | Source |
|--------|---------------|--------|
| **RAMMonitor** | Surveillance continue, seuils calibrés M1 8 Go, callbacks déchargement. | `src/ram_monitor.py` |
| **RAMBudgetManager** | Budget Go·s, déchargement forcé si dépassé (Item 40). | `src/core/ram_budget.py` |
| **EventBus** | Bus d'événements thread-safe async. Singleton — fusion V3/V4.5. | `src/core/events.py` |
| **TraceCollector** | Queue async des traces de session → `~/.nuru/traces.db`. | `src/learning/trace_collector.py` |
| **Optimizer** | Mining périodique des traces → improvements auto. | `src/learning/optimizer.py` |

---

## Project structure

```
nuru/
├── run_v12.py                  # Entry point PySide6 — V12 ambient presence (Z.ai)
├── cli.py                      # Entry point CLI
├── pyproject.toml              # Python ≥3.11 · pytest · pydantic · mlx-lm
├── config/
│   ├── settings.yaml           # Config user (clés sensibles dans Keychain)
│   └── default.yaml            # Defaults infra
├── .github/workflows/
│   └── ci.yml                  # CI/CD — lint + test (push/PR main)
├── src/
│   ├── nuru_core.py            # V15 orchestrator (compatibility facade)
│   ├── llm_local.py            # MLX Phi-4-mini + LoRA adapters
│   ├── llm_cloud.py            # Groq/OpenRouter/DeepSeek
│   ├── rag_engine.py           # RAG factory + types
│   ├── cache/
│   │   ├── kv_cache.py         # KVPersistentCache
│   │   └── kv_compress.py      # Quantification int8 + fenêtrage
│   ├── routing/
│   │   ├── router.py           # Routeur unifié 6-niveaux
│   │   ├── prompt_builder.py   # DynamicPromptBuilder
│   │   └── semantic_router.py  # Intent router NLP-lite
│   ├── core/
│   │   ├── orchestrator.py     # NuruOrchestrator — pipeline réel
│   │   ├── policies.py         # PolicyEngine — seuils centralisés
│   │   ├── prompt_guard.py     # Anti-injection
│   │   ├── response_guard.py   # StrictRAGGuard
│   │   ├── model_manager.py    # Cycle de vie modèles MLX
│   │   ├── ram_budget.py       # RAMBudgetManager (Item 40)
│   │   ├── reflexion.py        # ReflexionEngine (auto-évaluation)
│   │   ├── confidence.py       # ConfidenceCalibrator
│   │   ├── events.py           # EventBus singleton
│   │   ├── exceptions.py       # Hiérarchie d'exceptions typées
│   │   └── inference_worker.py # TokenReceiver (legacy compat)
│   ├── rag/
│   │   ├── multi_search.py     # Single source of truth retrieval
│   │   ├── v2_chunking.py      # Hierarchical chunker
│   │   ├── hyde.py             # Hypothetical Document Embeddings
│   │   ├── decomposer.py       # Multi-hop decomposition
│   │   ├── speculative.py      # Speculative RAG (Item 39)
│   │   ├── fact_checker.py     # Vérification post-génération
│   │   ├── diagnostics.py      # Diagnostic persistant
│   │   ├── index_health.py     # Santé de l'index
│   │   └── spotlight.py        # Recherche fichiers locaux
│   ├── agent/                  # Agent Loop V12
│   ├── memory/                 # MemoryManager V9
│   ├── audio.py                # STT/TTS
│   ├── ocr.py                  # Vision OCR
│   ├── tools/                  # ToolRegistry + SandboxShell
│   ├── ui/                     # V12 ambient UI (PySide6)
│   └── learning/               # TraceCollector + Optimizer + 3 architectures raisonnement
├── tests/
│   ├── test_kv_compress.py     # 24 tests — compression KV
│   ├── test_lora_adapter.py    # 6 tests — LoRA RAG adapter
│   ├── test_semantic_router.py # 85 tests — routing NLP-lite
│   ├── test_session.py         # 11 tests — session store
│   ├── test_naming_collisions.py # Anti-collision classes
│   ├── test_memory.py          # Mémoires cognitives
│   ├── mocks/
│   │   └── mlx.py              # Mock MLX partagé (ModuleType)
│   └── ...                     # 37 fichiers, 151 tests
├── NURUV15.md                  # Plan de consolidation V15 (81 propositions)
├── NURU_V9.md                  # Spec complète V9
├── NURU_V14_VISION.md          # Vision V14
└── ROADMAP.md                  # Roadmap unifiée
```

---

## V16 — Architectures de raisonnement (livrées ✅)

V16 implémente 3 architectures de raisonnement complémentaires, activées
automatiquement selon le type de requête et la confiance RAG.

### Pipeline décisionnel

```
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

```
┌─────────────────────────────────────────────────────────┐
│              V16 — RAISONNEMENT (livrée ✅)              │
│  Self-Consistency · Chain of Thought · ToT Agentic      │
│  └─ Validation outil via [OUTIL: nom(args)]             │
╞═════════════════════════════════════════════════════════╡
│              V15 — OPTIMISATIONS (terminée ✅)          │
│  LoRA RAG · Speculative · KV Compression · RAM Budget   │
│  CI/CD · ROADMAP                                        │
╞═════════════════════════════════════════════════════════╡
│              V12 — FONDATIONS (stable)                  │
│  PersonaEngine · Privacy Layer · SleepCycleManager      │
│  ModelRouter · CostGuard · Pipeline vocal               │
└─────────────────────────────────────────────────────────┘
```

---

## Tests

| Suite | Tests | Commande |
|-------|-------|----------|
| KV Cache Compression | 24 | `PYTHONPATH="" pytest tests/test_kv_compress.py -v` |
| LoRA RAG Adapter | 6 | `PYTHONPATH="" pytest tests/test_lora_adapter.py -v` |
| Semantic Router | 85 | `PYTHONPATH="" pytest tests/test_semantic_router.py -v` |
| Session Store | 11 | `PYTHONPATH="" pytest tests/test_session.py -v` |
| Anti-collision | 2 | `PYTHONPATH="" pytest tests/test_naming_collisions.py -v` |
| RAG Scoring | 26 | `PYTHONPATH="" pytest tests/test_rag_scoring.py -v` |
| Memory (GPU réel) | 15 | `pytest tests/test_memory.py -v` *(3 échecs connus)* |
| **Total** | **151+** | `PYTHONPATH="" pytest tests/ --ignore=tests/test_memory.py -v` |

> `PYTHONPATH=""` évite un conflit pydantic_core entre l'environnement système (Python 3.11) et le venv (3.13).

---

## Documentation

| Document | Lire si... |
|----------|-----------|
| [`NURUV15.md`](NURUV15.md) | Tu veux le plan de consolidation V15 — 81 propositions issues de 7 audits, phases d'exécution | |
| [`NURU_V9.md`](NURU_V9.md) | Tu veux la spec complète V12 — phases, sprints, décisions architecturales |
| [`NURU_V14_VISION.md`](NURU_V14_VISION.md) | Tu veux ce qui vient après V15 — GoalMemory, LiveKit, Skills |
| [`ROADMAP.md`](ROADMAP.md) | Une vue macro de la roadmap unifiée |
| [`NURU_AUDIT_SYNTHESE.md`](NURU_AUDIT_SYNTHESE.md) | Tu veux le contexte des 7 audits experts |
| [`NURU_AUDIT_2026-06-21_V12.md`](NURU_AUDIT_2026-06-21_V12.md) | Tu veux les P0 du moment |

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
- **Groq, OpenRouter, DeepSeek** — couche cloud optionnelle
- **Stanford SAIL** — inspirations architecturales OpenJarvis
- **HuggingFace** — hébergement des modèles et embeddings

---

## License

MIT. Voir [`LICENSE`](LICENSE).

---

*Document mis à jour le 15 juillet 2026 — NURU V16 Raisonnement ✅ — Self-Consistency · CoT · ToT Agentic — 130+ tests ✅*
