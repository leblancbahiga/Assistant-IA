# NURU Roadmap

> Mise à jour : 2026-07-10
> Version : 0.15.0 (V15 Phase 5)

---

## ✅ Phases V15 complétées

### Phase 1 — Fondation AgentOrchestrator (Sprint 1)
- ✅ Fusion AgentOrchestrator (src/agent/ + src/tools/) → module unique
- ✅ Couche consentement (`src/consent/`) avec user profile seed
- ✅ Suppression `sqlite_compat.py` (lecture mémoire brute)
- ✅ Fusion `src/security/` → `prompt_guard.py`
- ✅ Session streaming asynchrone (SSE-like sans threads)
- ✅ Déchargement modèle après timeout (90 Go·s budget RAM)
- ✅ Tests anti-collision noms de classes

### Phase 2 — RAG Fondation (Sprint 2)
- ✅ RAG Injection (embed + BM25 hybride)
- ✅ HyDE async
- ✅ Chunk overlap 100 tokens
- ✅ HyDE conditionnel (seulement si confiance < 0.7)
- ✅ Agent loop (max 3 itérations, stop si confiance > 0.8)
- ✅ Confidence label sur réponses
- ✅ RRF fusion rank-BM25 + embedding cosine

### Phase 3 — Infrastructure critique (Sprint 3)
- ✅ `pysqlite3-binary` pour éviter conflit sqlite3
- ✅ Endpoint conditionnel OpenRouter
- ✅ try/finally SQLite transactions
- ✅ done_callback pour arrêt gracieux InferenceWorker
- ✅ MemoryHub unifié -> MemoryManager

### Phase 4 — Mémoire cognitive
- ✅ WorkingMemory (courte durée, session locale)
- ✅ ConfidenceCalibrator (calibration confiance)
- ✅ ReflexionEngine (auto-évaluation)
- ✅ ProceduralMemory (procédures réutilisables)
- ✅ RAG benchmark pipeline
- ✅ Reranker sémantique (cross-encoder style)
- ✅ Nettoyage `nuru_core.py` → wrapper orchestrator
- ✅ Tokenizer conscient (comptage tokens réel vs estimation)
- ✅ Semantic Router (routing par intention NLP-lite)

### Phase 5 — Optimisations DeepSeek
| Item | Description | Effort | Statut |
|------|-------------|--------|--------|
| 38 | LoRA-MoE adaptateur RAG (P1 #49) | 1 sem | ✅ |
| 39 | Speculative RAG (P1 #48) | 1 sem | ✅ |
| 40 | RAM Budget Manager (P0 #23) | 3 j | ✅ |
| 41 | KV Cache Persistant (P2 #64) | 5 j | ✅ |
| **42** | **KV Cache Compression style MLA (P2 #74)** | **2 sem** | **✅** |
| 43 | CI/CD GitHub Actions (P2 #63) | 1 sem | 🔄 en cours |
| 44 | ROADMAP.md à jour (P2 #56) | 1h | 🔄 en cours |

### Phase 6 — Dataset & consolidation
| Item | Description | Statut |
|------|-------------|--------|
| 45 | Tests anti-collision noms | ✅ |
| 46 | Dataset 93 QA (validation fiable) | ✅ |
| 35 | Self-Consistency (P0 #29) — **BLOQUÉ** | 🚫 |

---

## 🚫 Bloqué

- **Item 35 — Self-Consistency** : Nécessite N≥3 générations parallèles.
  Sur M1 8 Go swap 90 %, chaque appel ≈ 2,5 Go → OOM/latence > 30 s.
  **Déblocage** : KV Cache Compression (Item 42, maintenant ✅). Réévaluer en V16.

## 📊 Métriques actuelles

| Métrique | Valeur |
|----------|--------|
| Tests passants | 151/154 (3 préexistants `test_memory.py`) |
| RAM cache (fp16) | ~80-160 MB / 512 tokens |
| RAM cache (int8) | ~40-80 MB / 512 tokens |
| Swap | 90 % (7,4 Go / 8 Go) |
| Python | 3.13 (CI : 3.11 + 3.13) |

## 🎯 V15 restant

| Item | Effort estimé | Dépendances |
|------|--------------|-------------|
| 43 — CI/CD (P2 #63) | ~1 sem | Aucune |
| 44 — ROADMAP.md (P2 #56) | ~1h | Aucune |

## 🗺 V16 — Preview

### Architecture
- **Philosophie** : Petits spécialistes orchestrés > monolithe (approche DeepSeek)
- **OS cognitif** : Mémoire > LLM, Objectifs > Prompts, UX > Benchmarks

### Candidats
- Self-Consistency (si swap < 50 % après Item 42)
- Pipeline feedback continu (NURU self-improvement)
- Dashboard analytics (stats usage, top sources)
- Architecture plugins extensible
- Support multi-modèle (pas que MLX)

## 🔧 Problèmes connus

- 3 tests `test_memory.py` échouent (besoin GPU/embeddings réels — mlx non disponible dans l'environnement de test isolé)
- `PYTHONPATH=""` requis pour executer les tests (env mixte 3.11/3.13 → crash pydantic_core)
- Swap élevé en continue (90%) — objectif V15 : 0 swap
