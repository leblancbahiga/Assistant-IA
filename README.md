<div align="center">
  <img src="https://img.shields.io/badge/NURU-V10.2-00A3FF?style=for-the-badge&logo=python&logoColor=white" alt="NURU V10.2"/>
  <img src="https://img.shields.io/badge/Platform-macOS%20M1-39FF14?style=for-the-badge&logo=apple&logoColor=white" alt="macOS M1"/>
  <img src="https://img.shields.io/badge/RAM-8%20Go%20Unified-FFB000?style=for-the-badge" alt="8 Go RAM"/>
  <img src="https://img.shields.io/badge/Tests-54%2F59-success?style=for-the-badge" alt="54/59 Tests"/>
  <img src="https://img.shields.io/badge/Status-V10.2%20Actif%20(Certifié%20Audit)-00A3FF?style=for-the-badge" alt="Status V10.2 Actif"/>
</div>

<br/>

<h1 align="center">🌀 NURU — Assistant IA Local V10.2</h1>
<p align="center">
  <i>Agentic RAG System for Apple Silicon — Intent-First Routing + Cloud Multi-Provider + Memory V9</i>
</p>

<p align="center">
  <b>🇫🇷 Français</b> · Conçu pour MacBook Pro M1 (8 Go RAM unifiée) · <b>Privacy-first</b>
</p>

---

## ✨ Aperçu

**NURU V10.2** est un assistant IA personnel **agentic** qui combine :
- Un **routeur intent-first** (classification LLM via Groq ~100ms) qui décide AVANT tout appel d'outil
- Un **LLM local** (Phi-4-mini) pour le trivial et l'offline
- Un **LLM cloud multi-provider** (Groq, OpenCode Zen, OpenRouter, DeepSeek, Nvidia) avec circuit breaker
- Un **moteur RAG hybride multi-stratégie** : Vectoriel + FTS5 + HyDE + Query Rewriting + RRF
- Une **mémoire V9** structurée (épisodique, sémantique, utilisateur, erreurs) + mémoire V5
- Un **vérificateur de faits** post-génération avec boucle de rétroaction
- Le tout dans une **interface PySide6 cyberpunk 3 colonnes** (V10)

## 🚀 Fonctionnalités Clés V10

| Composant | Technologie | Détails |
|-----------|-------------|---------|
| **Routeur Intent** | LLM Classification (Groq, ~100ms) | GENERAL_KNOWLEDGE / RAG / WEB / SIMPLE |
| LLM Local (principal) | **Phi-4-mini-instruct 4-bit** (MLX) | ~2.5 Go RAM, ~12 tok/s sur M1 |
| LLM Cloud (multi-provider) | **Groq** (Llama 3.3 70B) → **OpenRouter** → **DeepSeek** → **Nvidia** | Circuit Breaker + Fallback |
| Embeddings | **multilingual-e5-base-mlx** | 768d, multilingue (FR/EN/Swahili) |
| Reranker | **cross-encoder/ms-marco-MiniLM-L6-v2** | Conditionnel (zone grise) |
| Mémoire | **V9 MemoryManager** (épisodique + sémantique + utilisateur) + **V5 MemoryStore** | 7 faits utilisateur |

### 🧠 Routeur Intent-First (V10)

Le routeur classifie la requête **avant** tout appel d'outil :

| Intent | Déclencheur | Action |
|--------|-------------|--------|
| `GENERAL_KNOWLEDGE` | Maths, logique, sciences, définitions | LLM répond directement (pas de RAG) |
| `DOCUMENT_KEYWORD` | CV, rapport, projet, fichier | Pipeline RAG + gate de score (≥0.15) |
| `WEB_SEARCH` | Actualité, prix, météo, président | CloudLLM + recherche web |
| `SIMPLE` | Salutations, identité | LLM local direct |
| `COMPLEX` | Cas ambigus | LLM Classification → routing |

**Classification 2-passes :**
- **Passe 1** (regex, 0ms) : patterns connaissance générale, documents, web
- **Passe 2** (LLM Groq, ~100ms) : cas ambigus non résolus par la Passe 1

### 🔍 RAG Hybride V10

- **Gate de score** : `LOCAL_RAG` seulement si `top_score ≥ 0.15` (pas de faux positifs)
- **Score affiché** : utilise le score reranker (0.95), pas le RRF normalisé (0.33)
- **Tables DOCX** : extraction complète incluant les tableaux
- **Profil auto-détecté** : cv/rapport/note selon le nom du fichier
- **Seuils** : `rag_score_threshold=0.30` (V10.2: 0.40→0.30, moins de faux négatifs), `rag_score_fallback=0.25`

### 🧠 Mémoire V9

- **MemoryBridge** : connecte V5 (MemoryStore) + V9 (MemoryManager) au pipeline
- **UserMemory** : faits structurés (clé/valeur/catégorie/confiance)
- **EpisodicMemory** : souvenirs datés et contextuels
- **Injection prompt** : faits V9 injectés dans le system prompt via LongTermMemory

### 📊 Scores de confiance

| Score | Label | Affichage |
|-------|-------|-----------|
| ≥ 0.70 | HAUTE | 🟢 Vert |
| ≥ 0.40 | MOYENNE | 🟡 Jaune |
| < 0.40 | FAIBLE | 🔴 Rouge |

---

## 🏗️ Architecture

```
┌─────────────────┬──────────────────────────┬──────────────────────┐
│   Sidebar        │   Chat Central            │   Colonne Métriques  │
│  (260px)         │   (QStackedWidget)        │   (320px fixe)       │
│                  │                           │                      │
│                  │   🧃 TokenJuice          │   RAM 2.3/8.0G       │
│                  │       ↓                   │   TOK/S   RAG   MODE │
│                  │   🧠 Intent Router        │   12.5    0.95  RAG  │
│                  │     ├─ GENERAL → LLM      │   ──────────         │
│                  │     ├─ RAG    → Pipeline  │   📊 DIAGNOSTIC      │
│                  │     ├─ WEB    → Cloud     │   Stratégie active   │
│                  │     └─ SIMPLE → Local     │   Index Health       │
│                  │       ↓                   │   ──────────         │
│                  │   🔍 Pipeline RAG V10     │   🧠 MÉMOIRE V9      │
│                  │   Query Rewriter          │   7 faits user       │
│                  │   Multi-Strategy          │   Épisodique         │
│                  │   RRF + Dedup             │                      │
│                  │   Score Gate ≥0.15        │                      │
│                  │       ↓                   │                      │
│                  │   ☁️ CloudLLM Multi-Prov  │                      │
│                  │       ↓                   │                      │
│                  │   ✅ FactChecker          │                      │
│                  │       ↓                   │                      │
│                  │   📥 TraceCollector       │                      │
└─────────────────┴──────────────────────────┴──────────────────────┘
```

---

## 🐛 Corrections V10.2 (Audit certifié)

| # | Problème | Correctif | Rapport |
|---|----------|-----------|:-------:|
| 1 | **`import logging` manquant** dans `config.py` — toggles Settings plantés | `import logging` ajouté | #3 |
| 2 | **URL OpenRouter erronée** `api.openrouter.ai` (404) | `api.` retiré | #3 |
| 3 | **Fuite mémoire MLX** sur erreur streaming | `finally: self.unload()` dans `generate_stream()` | #1, #A |
| 4 | **`pysqlite3` bloquant** sur Python 3.11+ | `pysqlite3-binary` + import protégé try/except | #3 |
| 5 | **Prompt/RAG injection** — LLM peut recevoir des instructions adverses | `_sanitize_rag_query()` + `_sanitize_chunk_content()` (PromptGuard) | #1, #2, #5, #Final |
| 6 | **`confidence_label="HAUTE"`** sur retour RAG vide | Forcé à `"ABSENT"` | #3, #4 |
| 7 | **Seuil RAG 0.40 trop élevé** — faux négatifs documentaires | Réduit à `0.30` | #4, #2, #1, #A |
| 8 | **Fenêtre contextuelle bridée** (4096 tokens, Phi-4-mini 32K) | `max_prompt_tokens=8192`, `reserved_response=2048` | #A |
| 9 | **`except Exception` génériques** dans le pipeline | Hiérarchie `OrchestratorError` → `RAGError/LLMError/MemoryError` | #1, #2, #A |
| 10 | **Race condition cache sémantique** | `asyncio.Lock()` sur `get_cache()`/`set_cache()` | #2, #4 |

**Constats des 7 experts auditeurs :** consensus 7/7 — NURU sécurisé et stabilisé. Code mort V8 (`audio_tts.py`, `sqlite_compat.py`) déjà nettoyé. Modules V8 (MultiSearchOrchestrator, FactChecker, HyDE, decomposer) confirmés actifs.

## 🐛 Corrections V10.1

| # | Problème | Correctif |
|---|----------|-----------|
| 1 | **Profile Boost x2.5** favorisait les CV | Supprimé — tous les fichiers égaux |
| 2 | **Dashboard V7** — pages V10 vierges | Navigation V10 + label V10 |
| 3 | **source_list non défini** après suppression Profile Boost | Variable initialisée |
| 4 | **Tables DOCX non extraites** | Extraction ajoutée dans `_parse_file` |
| 5 | **Profil chunking toujours "cv"** | `detect_profile()` auto-détecte cv/rapport/note |
| 6 | **Timeout indexation 30s** | Porté à 120s pour les gros fichiers |
| 7 | **RAG-par-défaut** — "je ne trouve pas" pour maths/logique | Routeur intent-first + GENERAL_KNOWLEDGE |
| 8 | **Scores affichés = 0.33%** | Score reranker utilisé (0.95) au lieu du RRF |
| 9 | **Mémoire V9 non câblée** | MemoryBridge V5+V9 + _load_v9_page_data corrigé |
| 10 | **#8B949E dans le texte** | Color code retiré du label MemoryExplorer |
| 11 | **Agent "Inactif"** | Changé en "Prêt — en attente de tâche" |
| 12 | **Sessions/Documents** sans données | `_wire_page_dependencies` crée les instances |
| 13 | **`embed()` async appelé synchrone** | Remplacé par `embed_sync()` |
| 14 | **`import re` conditionnel** | Déplacé au niveau module |
| 15 | **remove_file_index** — database locked | Retry 3x + BEGIN IMMEDIATE + busy_timeout |

---

## 📁 Structure du projet

```
src/
├── core/
│   ├── orchestrator.py      # NuruOrchestrator V4.5
│   ├── router.py             # Router (wrapper SemanticRouter + PolicyEngine)
│   ├── exceptions.py         # Hiérarchie: OrchestratorError → RAGError|LLMError|MemoryError
│   ├── response_guard.py     # StrictRAGGuard
│   └── policies.py           # PolicyEngine (RAM + fallback)
├── rag/
│   ├── multi_search.py       # Multi-stratégie + RRF
│   ├── chunking.py           # SemanticChunker
│   ├── v2_chunking.py        # HierarchicalChunkerV2 (auto-detect profile)
│   └── spotlight.py          # Spotlight (mdfind macOS)
├── memory/
│   ├── manager.py            # MemoryManager V9
│   ├── user.py               # UserMemory (faits structurés)
│   ├── episodic.py           # EpisodicMemory
│   └── semantic.py           # SemanticMemory
├── ui/
│   ├── dashboard.py          # CyberDashboard V10
│   ├── styles.qss            # Thème Deep Ocean
│   └── components/
│       ├── console_page.py   # Chat
│       ├── documents_page.py # Base documentaire
│       ├── sessions_page.py  # Historique sessions
│       ├── memory_page.py    # Mémoire V5
│       ├── memory_explorer.py # Mémoire V9
│       ├── diagnostics_page.py # Diagnostics RAG
│       ├── v6_system_page.py # État modules V10
│       ├── agent_status.py   # Widget agent
│       └── stats_page.py     # Statistiques V10
├── semantic_router.py        # Routeur intent-first (Passe 1 + LLM)
├── long_term_memory.py       # Adaptateur MemoryBridge → orchestrator
├── memory_bridge.py          # Pont V5+V9
├── rag_engine.py             # Moteur RAG hybride
├── ingestion.py              # Indexation documents
├── embedder.py               # Embeddings MLX
├── llm_local.py              # Phi-4-mini MLX
├── llm_cloud.py              # Multi-provider cloud
├── config.py                 # Configuration
├── nuru_core.py              # NuruCore (orchestrateur principal)
├── token_juice.py            # Compression tokens
└── reranker.py               # Cross-encoder reranker
```

---

## 🚀 Installation

```bash
# Cloner le dépôt
git clone <url>
cd "Assistant IA"

# Installer les dépendances
pip install -r requirements.txt

# Lancer le dashboard
python3 src/ui/dashboard.py
```

---

*Document mis à jour le 14 juin 2026 — NURU V10.2 — Audit certifié 7 experts*
