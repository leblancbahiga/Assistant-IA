# NURU V15 — Plan de consolidation

**Compilation des propositions retenues issues des 7 audits experts + 7 expertises DeepSeek**
Document évolutif — mis à jour à chaque nouveau rapport.

---

## Sources des audits

### Audit #1 — Claude (Anthropic), 7 juillet 2026
*Fichier : `NURU_Audit_V15_2026-07-07.docx`*

### Audit #2 — Cabinet d'architecture logicielle (rapport 1/2), juillet 2026
*Fichier : `AuditV15_1.md`*
Score : 58/100

### Audit #3 — Cabinet d'architecture logicielle (rapport 2/2), juillet 2026
*Fichier : `AuditV15_2.md`*
> ⚠️ **Note :** Score 29/100 significativement plus bas que les autres (54-58/100). Plusieurs critiques sont caduques (RRF, Query Rewriting, Hierarchical Chunker, MLX existent déjà dans le code V12). Ce rapport semble basé sur des patterns génériques plutôt qu'une lecture réelle du dépôt. Les propositions réellement nouvelles sont retenues ci-dessous.

### Audit #4 — Cabinet d'architecture logicielle (rapport 3/3), juillet 2026
*Fichier : `AuditV15_3.md`*
> ✅ Score 54/100, cohérent avec le consensus. Lecture réelle du code. Diagnostics précis (RAG Injection, guerre des 4 mémoires, HyDE synchrone, tokenizer approximatif).

### Audit #5 — Rapport complémentaire, juillet 2026
*Fichier : `AuditV15_4.md`*
> ✅ Score 71/100 (échelle /15). Le plus optimiste sur la vision produit (14/15), le plus sévère sur la performance (4/15). Diagnostics précis : RAM (breakdown chiffré), Lost-in-the-Middle, sur-utilisation HyDE, chunking trop large.

### Audit #6 — Audit global de maturité, juillet 2026
*Fichier : `AuditV15_5.md`*
> ✅ Rapport le plus long (589 lignes), score 4.8/10 → 8.8/10 cible. Bugs précis et actionnables (confidence_label, normalisation RRF, tableaux DOCX, métadonnées embeddings, pysqlite3, URL OpenRouter, async leaks).

### Audit #7 — Rapport senior architectural complet, juillet 2026
*Fichier : `AuditV15_6.md`*
> ✅ Rapport le plus structuré (828 lignes), score 5.2/10 → 7.8/10 cible. Recoupe massivement les autres rapports. Apports uniques : Self-Consistency (3-way voting), MemoryHub 6 types, ErrorRecovery + Verifier loop, roadmap V15-V17 cohérente 6 mois.

---

## Diagnostic central (consensus des 7 audits)

> **Score global : consensus 55-60/100** (audits #1: 58/100, #2: 58/100, #3: 29/100 outlier, #4: 54/100, #5: 71/100 échelle /15, #6: 48/100, #7: 52/100)
>
> **Problème n°1 : le mur des 8 Go RAM.** Breakdown chiffré par l'audit #5 : macOS 2.5 Go + UI PySide6 0.5 Go + LLM 4-bit 4.2 Go = quasi rien pour RAG/embeddings/STT/TTS. Résultat : swapping permanent, latence, freeze. La priorité V15 est d'abord une guerre de la RAM.
>
> **Problème n°2 : métriques RAG non fiables.** Recall@5 à 92% basé sur 5 documents, normalisation RRF biaisée, confidence_label trompeur.
>
> **Problème n°3 : fragmentation par duplication.** 4 modules mémoire concurrents, 2 AgentOrchestrator, 2 couches sécurité.
>
> **Problème n°4 : Lost-in-the-Middle & HyDE contre-productif.** Les petits modèles locaux (3B 4-bit) reçoivent trop de contexte RAG, ignorent le milieu du prompt et hallucinent.
>
> **Problème n°5 : bugs concrets non résolus.** confidence_label, normalisation RRF, tableaux DOCX, pysqlite3, URL OpenRouter, fuites SQLite/async.
>
> **Problème n°6 : sécurité résiduelle.** RAG Injection / Path Traversal non mitigé.

---

## Propositions retenues

Les propositions sont numérotées de façon **unique et séquentielle** sur l'ensemble du document. Les items marqués **INFIRMÉ** ou **NUANCÉ** l'ont été par vérification du code réel (Expert #7).

### 🔴 P0 — Critique (avant V15 — quick wins)

| # | Proposition | Source | Effort |
|---|-------------|--------|--------|
| 1 | **Fusionner les 2 AgentOrchestrator** — `src/agent/orchestrator.py` (Planner/Executor/Verifier/Recovery) avec `src/tools/agent_orchestrator.py` (seul appelé). Garder un seul module. | #1 | 1-2 sem | ✅ |
| 2 | **Brancher Privacy & Consent Layer** — `src/privacy/consent_layer.py` appelé avant tout accès capteur. | #1 | 1-2 sem | ✅ |
| 3 | **Corriger pyproject.toml** — remplacer PyQt6 par PySide6 + ajouter `[project.dependencies]`. | #1, #2 | 1-2 h | ✅ |
| 4 | ➡️ **INFIRMÉ** — Tests morts : les 12 fichiers non collectés échouent sur `ModuleNotFoundError: mlx` ou `PySide6` (dépendances Apple Silicon). 738/815 passent. | #2 | — |
| 5 | ➡️ **INFIRMÉ** — `pipeline_offline` : le test passe après `pip install cachetools`. Vrai problème : absence de `cachetools` dans `pyproject.toml` (déjà #3). | #2 | — |
| 6 | ➡️ **INFIRMÉ** — Identité hardcodée : `nuru_core.py` ne contient aucune occurrence. `src/identity_manager.py` dédié existe déjà. | #2 | — |
| 7 | **Supprimer `sqlite_compat.py`** — lecture mémoire brute CPython via `id()+offset`, risque de segfault latent. | #1 | 10 min | ✅ |
| 8 | **Fusionner `src/security/` dans `prompt_guard.py`** — une seule couche de sécurité. | #1 | 1-2 h | ✅ |
| 9 | ➡️ **INFIRMÉ** — Doublons logging : `logging_config.py` n'existe pas dans le dépôt. Hallucination du modèle d'audit. | #2 | — |
| 10 | **Nettoyer les fichiers `_diag_*.py`, `_check_*.py`, `_test_*.py`** de la racine vers `scripts/` ou `tests/`. | #1 | 1 h | ✅ |
| 11 | **Streaming des tokens** — callback de génération MLX pour envoyer les tokens un par un à l'UI (effet wow immédiat). | #3 | 1 j | ✅ |
| 12 | **Unload des modèles après réponse** — purger le LLM de la VRAM 5s après génération. | #3 | 2 h | ✅ |
| 13 | **Ajouter un test d'intégrité anti-collision de noms de classes.** | #1 | 2-3 h | ✅ |
| 14 | **Indicateur UI d'état interne** — cercle animé "Analyse..." → "Génération..." pendant le RAG. | #3 | 4 h |
| 15 | **Sécuriser RAG Injection & Path Traversal** — `sanitize_path()`, `FileGuard`, regex PromptGuard. | #4 | 4 h |
| 16 | **Rendre HyDE asynchrone** — wrapper dans `asyncio.to_thread`. | #4 | 2 h |
| 17 | **Réduire la taille max des chunks à 1000 car.** — les chunks 4000 car. noient les petits modèles 4-bit (Lost-in-the-Middle). | #5 | 1 h |
| 18 | **Désactiver HyDE sur les modèles <7B** + **activation dynamique** : si écart top-1/top-5 > 0.3, la requête est ambiguë → activer HyDE ; sinon BM25/vectoriel direct. | #5, Expert #6 | 2 h |
| 19 | **Dynamic VRAM Paging** — déchargement agressif de TOUS les modèles dés qu'inactifs. | #5 | 4 h |
| 20 | **Limiter l'Agent Loop à 3 itérations max** — éviter les boucles infinies d'erreur. | #5 | 1 h |
| 21 | **Corriger `confidence_label`** — **NUANCÉ** (Expert #7) : le gating calibre déjà HAUTE/MOYENNE/FAIBLE selon le score RRF avec ABSENT sur recherche vide. Reste un HAUTE par défaut (l.671) commenté "non utilisé pour le gating". Action : supprimer la valeur par défaut. | #6 | 15 min |
| 22 | **Corriger la normalisation RRF biaisée** — utiliser un `max_possible` fixe. | #6 | 1 h |
| 23 | **Extraire les tableaux DOCX avec en-têtes** — préserver la structure tabulaire. | #6 | 2 h |
| 24 | **Séparer contenu et métadonnées dans les embeddings** — supprimer les préfixes `[Doc - Section]` (10-17% du chunk). | #6 | 1 h |
| 25 | **Remplacer `pysqlite3` par `sqlite3` standard**. | #6 | 30 min |
| 26 | **Corriger l'URL OpenRouter** — vérifier et mettre à jour l'endpoint API. | #6 | 15 min |
| 27 | **Ajouter `try/finally` pour les connexions SQLite** — fuites mémoire dans `rag_engine.py`. | #6 | 1 h |
| 28 | **Ajouter `add_done_callback` pour les `create_task` async** — 3 tâches sans await dans `orchestrator.py` et `nuru_core.py`. | #6 | 1 h |
| 29 | **Self-Consistency (3-way voting)** — 3 réponses + vote majoritaire par similarité cosinus (-40% hallucinations). **⚠️ Coût : x3 RAM et latence** — nécessite VRAM Paging (#19) ou LoRA-MoE (#49) pour être viable sur M1 8 Go. | #7 | 1 sem |
| 30 | **MemoryHub : mémoire unifiée 6 types** — Working, Episodic, Semantic, Procedural, User, Error + ConsolidationWorker (daemon 6h) + **Memory Router** (gate classifieur, -60% requêtes mémoire). | #7, Expert | 2 sem |
| 31 | **Décodage spéculatif (Speculative Decoding)** — petit modèle (SmolLM2-360M) prédit 5 tokens, Phi-4-mini valide. Gain : +50 à +150% vitesse sur M1. Zéro occurrence dans le code actuel (confirmé Expert #7). | Expert DeepSeek | 1 sem |

### 🟡 P1 — Majeur (Sprint V15)

| # | Proposition | Source | Effort |
|---|-------------|--------|--------|
| 32 | **Implémenter WorkingMemory** — contexte de session persisté avec TTL. | #2 | 8 h |
| 33 | **Implémenter ConfidenceCalibrator** — score de fiabilité par réponse (FAIT / INFÉRENCE / HYPOTHÈSE). | #2 | 8 h |
| 34 | **Implémenter ReflexionEngine** — auto-critique + correction en 2 passes max. **⚠️ Coût : 2x tokens et latence** — nécessite décodage spéculatif (#31) ou optimisation pipeline M1. | #2 | 24 h |
| 35 | **Implémenter ProceduralMemory** — workflows appris par l'usage. | #2 | 16 h |
| 36 | **Harnais de benchmark RAG** — 30-50 paires question/document connu, Recall@5/10, MRR, NDCG. | #1, #2 | 8 h |
| 37 | **Activer le reranker systématiquement** (pas conditionnel). | #2 | 4 h |
| 38 | **Nettoyer `nuru_core.py`** — archiver le pipeline V4 legacy (`process_query()`). | #1 | 2-3 j |
| 39 | **Small-to-Big Retrieval** — récupérer petits chunks pertinents, puis document parent complet. | #3 | 8 h |
| 40 | **Sandbox pour outils** — liste blanche de répertoires, protection injection PDF. | #3 | 8 h |
| 41 | **Unifier les 4 modules mémoire en MemoryManager 6 couches** — `memory_store`, `memory/`, `long_term_memory`, `memory_bridge` fusionnés. | #4 | 1 sem |
| 42 | **Tokenizer réel de Phi-4** — remplacer `len(text)//4` par le tokenizer HuggingFace/MLX. | #4 | 4 h |
| 43 | **Semantic Router ultra-léger** — remplacer le routing LLM par embeddings + cosine similarity (0 inference LLM). ⬆️ Remonté en P1 sur recommandation Expert #7 (équivalent MoE gating). | #5, Expert #7 | 8 h |
| 44 | **Time-Weighted Retrieval** — pondération temporelle des souvenirs épisodiques. | #5 | 8 h |
| 45 | **Remplacer BM25 maison par `rank_bm25`** — le BM25 actuel n'a pas d'IDF ni de normalisation. | #6 | 2 h |
| 46 | **Ajouter HNSW à sqlite-vec** — recherche vectorielle approchée. | #6 | 4 h |
| 47 | **Dataset d'évaluation RAG étendu** — 20+ questions agronomiques. | #6 | 4 h |
| 48 | **Speculative RAG** — petit modèle génère réponse rapide sans RAG ; RAG tourne en parallèle. Si docs >0.7, re-génère avec contexte. Latence perçue <500ms pour 80% des requêtes. | Expert DeepSeek | 1 sem |
| 49 | **MoE logiciel local (LoRA-MoE)** — UN modèle de base en RAM, adaptateurs LoRA (<50 Mo) chargés/déchargés dynamiquement par domaine (RAG, Code, Conversation). | Expert DeepSeek | 2 sem |
| 50 | **RAMBudgetManager** — arbitre dynamique LLM/RAG/STT/TTS/UI selon la tâche. | Expert DeepSeek | 1 sem |

### 🔵 P2 — Modéré (Sprint V15+)

| # | Proposition | Source | Effort |
|---|-------------|--------|--------|
| 51 | **Intégrer SleepCycleManager** — consolidation mémoire pendant l'inactivité. | #1, #2 | 16 h |
| 52 | **Implémenter GoalMemory + ProjectMemory** — suivi d'objectifs long terme. | #2 | 40 h |
| 53 | **Étendre ToolRegistry** — création/modification fichiers, sandbox. | #2 | 40 h |
| 54 | **Implémenter FactChecker systématique** — vérification post-génération. | #2 | 8 h |
| 55 | **Implémenter Learning Loop** — FeedbackCollector + StrategyOptimizer. | #2 | 40 h |
| 56 | **Mettre à jour ROADMAP.md** — reflète l'état V12/V14 réel. | #1 | 1 h |
| 57 | **ErrorRecovery + Verifier loop** — retry backoff, rollback si destructif. | #7 | 1 sem |
| 58 | **Caching modèle MLX + lazy loading** — cache persistant des poids, chargement différé. | #7 | 3 j |
| 59 | **Refonte Multiprocess (MVIC/Event-Driven)** — UI/backend/LLM en processus isolés. | #3 | 1-2 sem |
| 60 | **Chunking dynamique** — taille des chunks selon longueur du document. | #6 | 2 h |
| 61 | **Overlap 20% au chunking** — continuité sémantique. | #6 | 1 h |
| 62 | **Filtrer les secrets dans les logs** — masquer les clés API. | #4 | 2 h |
| 63 | **CI/CD minimal** — GitHub Actions tests hors-M1 à chaque push. | #1, #2 | 1 sem |
| 64 | **KV Cache Persistant** — conserver le cache d'attention entre sessions. | Expert DeepSeek | 1 sem |
| 65 | **Distillation domaine (LoRA NURU)** — dataset Q&A + fine-tuning LoRA 4-bit 50-100 Mo. | Expert DeepSeek | 2 sem |
| 66 | **FP8 / AWQ / QAT** — quantification différenciée (attention FP16, FFN 4-bit AWQ). ~700 Mo potentiels. | Expert DeepSeek | 1 sem |
| 67 | **Vérifier GQA sur le modèle actuel** — si Phi-4 n'a pas Grouped Query Attention, changer pour Qwen2/Gemma2 (cache KV 2-8x plus petit). | Expert DeepSeek | 2 j |
| 68 | **Plan de migration des données mémoire** — fusion des 4 bases existantes vers MemoryHub. | Expert DeepSeek | 3 j |
| 69 | **Speculative Dreaming** — pré-génération de réponses pendant idle (hit rate cible 30%). | Expert DeepSeek | 2 sem |
| 70 | **Distillation algorithmique (JSON natif au lieu de ReAct)** — fine-tune pour émettre directement des commandes JSON. -60% taille prompts système. | Expert DeepSeek | 1 sem |
| 71 | **Circuit Breaker Cloud** — max 5 appels cloud/h, cache 24h, fallback local. | Expert #6 | 2 h |
| 72 | **Batch Processing embeddings** — lots de 32 (+2-3x vitesse indexation). | Expert #6 | 1 h |
| 73 | **Pruning 30% des poids** — supprimer les poids < seuil de magnitude (-30% RAM). | Expert #6 | 1 sem |
| 74 | **Compression KV Cache style MLA (Multi-head Latent Attention)** — cache en format latent compressé (-50-75% RAM contexte). **Note : Qwen3.5-2B utilise déjà attention hybride** (1/4 couches pleine, reste linéaire) — aligné DeepSeek. | Expert #7 | 2 sem |

### 🟢 P3 — Long terme

| # | Proposition | Source | Effort |
|---|-------------|--------|--------|
| 75 | **UI immersive** — animations fluides, micro-interactions, présence ambiante. | #2 | 20 h |
| 76 | **PersonaEngine intégré** — personnalité cohérente dans le temps. | #2 | 8 h |
| 77 | **Multi-appareils (LiveKit)** — voix distante, mémoire synchronisée. | #2 | 30 h |
| 78 | **Tree of Thoughts** — après consolidation de l'agent loop. | #2 | 40 h |
| 79 | **Bandeau de Confiance dans l'UI** — Sources, Faits, Inférences, Confiance % sous chaque réponse. | #4 | 8 h |
| 80 | **Réévaluer ReAct/Reflexion/ToT avancé** — après mesures objectives du benchmark RAG. | #1 | — |
| 81 | **Refonte UI en Tauri (Rust/Web)** — remplacer PySide6, diviser RAM UI par 5 (<100 Mo), 60fps natif macOS. *Avis expert : P1 recommandé (Sprint 2-3) — 400 Mo RAM récupérée sur 8 Go = 5% significatif en tension permanente.* | #5, Expert | 2-3 mois |

---

## Architecture cible (consolidée)

```
COUCHE 7 — INTERFACE UTILISATEUR (DM-1 V2)
  Dashboard · Chat immersif · Floating Widget · Voice Overlay
  Présence ambiante · Animations · Micro-interactions

COUCHE 6 — AGENT ORCHESTRATOR (fusionné)
  StateManager · Planner · Executor · Verifier · Recovery
  ResumeManager · GoalManager · ProjectManager

COUCHE 5 — RAISONNEMENT AVANCÉ
  ReflexionEngine · SelfConsistency · ConfidenceCalibrator
  SpeculativeRAG · SpeculativeDreaming (idle)
  TreeOfThoughts (P3) · Multi-agent (P3)

COUCHE 4 — MÉMOIRE UNIFIÉE (6 types + Consolidation)
  EpisodicMemory · SemanticMemory · ProceduralMemory
  UserMemory · ErrorMemory · WorkingMemory
  ConsolidationWorker · MemoryRetriever · SleepCycleManager

COUCHE 3 — APPRENTISSAGE CONTINU
  FeedbackCollector · PerformanceTracker · StrategyOptimizer
  SelfEvaluator · AutoImprovement

COUCHE 2 — OUTILS & ACTION
  ToolRegistry · ShellExec · FileManipulator · CodeExecutor
  WebResearcher · Calendar · Notifications · Spotlight

COUCHE 1 — FONDATIONS (V12 existant — à consolider)
  RAG Hybride (sqlite-vec + FTS5 + RRF + HyDE)
  Router 6-niveaux · TokenJuice · LLM Local/Cloud
  Multi-Provider · PromptGuard · StrictRAGGuard · EventBus
  ─── Doublons à supprimer ───
  src/security/ → fusionné dans prompt_guard.py
  src/agent/orchestrator.py + src/tools/agent_orchestrator.py → fusionné
  sqlite_compat.py → supprimé
  nuru_core.py (legacy V4) → archivé
```

---

## Roadmap V15 (consolidée)

> **⚠️ Note expert :** La Phase 0 initiale (21 items en 24-48h) était irréaliste pour un seul développeur. Scindée ci-dessous.

### Phase 0A — Stabilité critique (48h) ✅ *Terminée*
*Objectif : l'application ne crash plus, les fuites mémoire sont colmatées.*

| # | Action | Effort | Source | Statut |
|---|--------|--------|--------|--------|
| 1 | pyproject.toml : PySide6 + dépendances de base | 1-2 h | #1, #2 | ✅ |
| 2 | Supprimer sqlite_compat.py (P0 #7) | 10 min | #1 | ✅ |
| 3 | Ajouter cachetools dans pyproject.toml (P0 #3) | 5 min | #2, Expert #7 | ✅ |
| 4 | Remplacer pysqlite3 → sqlite3 (P0 #25) | 30 min | #6 | ✅ |
| 5 | try/finally connexions SQLite (P0 #27) | 1 h | #6 | ✅ |
| 6 | add_done_callback pour async tasks (P0 #28) | 1 h | #6 | ✅ |
| 7 | Corriger URL OpenRouter (P0 #26) | 15 min | #6 | ✅ |
| 8 | Archiver fichiers _diag_*/_check_*/_test_* de la racine (P0 #10) | 1 h | #1 | ✅ |

### Phase 0B — Sécurité & Performance (1 sem) ✅ *Terminée*
*Objectif : le système fonctionne sans danger et sans bloquer l'UI.*

| # | Action | Effort | Source | Statut |
|---|--------|--------|--------|--------|
| 9 | Sécuriser RAG Injection & Path Traversal (P0 #15) | 4 h | #4 | ✅ |
| 10 | Rendre HyDE asynchrone (P0 #16) | 2 h | #4 | ✅ |
| 11 | Filtrer les secrets dans les logs (P2 #62) | 2 h | #4 | ✅ |
| 12 | Tokenizer réel de Phi-4 (P1 #42) | 4 h | #4 | ✅ |
| 13 | Réduire taille max chunks à 1000 car. (P0 #17) | 1 h | #5 | ✅ |
| 14 | Désactiver HyDE conditionnellement + activation dynamique (P0 #18) | 2 h | #5 | ✅ |
| 15 | Limiter Agent Loop à 3 itérations max (P0 #20) | 1 h | #5 | ✅ |
| 16 | Supprimer valeur par défaut HAUTE dans confidence_label (P0 #21) | 15 min | #6 | ✅ |
| 17 | Corriger normalisation RRF biaisée (P0 #22) | 1 h | #6 | ✅ |
| 18 | Nettoyer .gitignore | 15 min | #6 | ✅ |
| 19 | Fusionner src/security/ → prompt_guard.py (P0 #8) | 1-2 h | #1 | ✅ |
| 20 | KV cache 8-bit + prefill progressif + benchmark (P0 #31) | 3 j | Expert #7 | ✅ |

### Phase 1 — Dé-duplication & Semantic Router (1-2 sem) ✅ *Terminée*

| # | Action | Effort | Statut |
|---|--------|--------|--------|
| 21 | Fusionner les 2 AgentOrchestrator (P0 #1) | 1-2 sem | ✅ |
| 22 | Nettoyer nuru_core.py — archiver V4 legacy (P1 #38) | 2-3 j | ✅ |
| 23 | Semantic Router ultra-léger (P1 #43) | 1 sem | ✅ |
| 24 | Renommer/re-numéroter src/tools/agent_orchestrator.py | 1 j | ✅ |

### Phase 2 — Câblage Privacy & Streaming (1-2 sem) ✅ *Terminée*

| # | Action | Effort | Statut |
|---|--------|--------|--------|
| 25 | Brancher consent_layer sur voix, vision, MCP (P0 #2) | 1-2 sem | ✅ |
| 26 | Streaming tokens MLX callback (P0 #11) | 1 j | ✅ |
| 27 | Unload modèles après réponse (P0 #12) | 2 h | ✅ |

### Phase 3 — Mémoire & Unification (1-2 sem) ✅ *Terminée*

| # | Action | Effort | Statut |
|---|--------|--------|--------|
| 28 | Unifier les 4 modules mémoire → MemoryManager 6 couches (P0 #30) | 1 sem | ✅ |
| 29 | Implémenter WorkingMemory (P1 #32) | 8 h | ✅ |
| 30 | Implémenter ProceduralMemory (P1 #35) | 16 h | ✅ |
| 31 | Intégrer SleepCycleManager (P2 #51) | 8 h | ✅ |
| 32 | Plan migration données mémoire (P2 #68) | 3 j | ✅ |

### Phase 4 — Intelligence (1-2 sem)

| # | Action | Effort | Statut |
|---|--------|--------|--------|
| 33 | Implémenter ConfidenceCalibrator (P1 #33) | 8 h | ✅ |
| 34 | Implémenter ReflexionEngine 2 passes (P1 #34) | 24 h | ✅ |
| 35 | Self-Consistency (P0 #29) — BLOQUÉ (swap 90 %, nécessite RAM stable avant) | 16 h | 🔴 |
| 36 | Harnais de benchmark RAG (P1 #36) | 8 h | ✅ |
| 37 | Reranker systématique (P1 #37) | 4 h | ✅ |

### Phase 5 — Optimisations DeepSeek (2-3 sem)

| # | Action | Effort | Statut |
|---|--------|--------|--------|
| 38 | LoRA-MoE : 1 adaptateur RAG (scope réduit, P1 #49) | 2 sem | ✅ |
| 39 | Speculative RAG (P1 #48) | 1 sem | ✅ |
| 40 | RAMBudgetManager (P1 #50) | 1 sem | ✅ |
| 41 | KV Cache Persistant (P2 #64) | 1 sem | ✅ |
| 42 | Compression KV Cache style MLA (P2 #74) | 2 sem | ✅ |

### Phase 6 — CI & Documentation (1 sem)

| # | Action | Effort | Statut |
|---|--------|--------|--------|
| 43 | CI/CD GitHub Actions (P2 #63) | 1 sem | ✅ |
| 44 | ROADMAP.md à jour (P2 #56) | 1 h | ✅ |
| 45 | Test anti-collision de noms (P0 #13) | 2-3 h | ✅ |
| 46 | Dataset évaluation RAG étendu (P1 #47) | 4 h | ✅ |

### Phase 6b — UI Improvements (fusion 7 audits UX)

| # | Proposition | Source audit | Effort | Priorité | Statut |
|---|-------------|--------------|--------|----------|--------|
| 47 | **Navigation simplifiée** (sidebar 15→8 items, fusion V5/V9, hiérarchie claire) | #5 | 1 j | **P1** | Obsolète* |
| 48 | **Contrastes + tailles police** (accessibilité, lisibilité SF Pro, échelle cohérente) | #5, #3 | 4 h | **P1** | ✅ |
| 49 | **Indicateur « Analyse…→ Génération… »** dans les bulles chat pendant RAG | #2 | 2 h | **P1** | ✅ |
| 50 | **Sidebar repliable** (220 px ↔ 60 px icônes, gain d'espace) | #5 | 2 j | **P1** | Obsolète* |
| 51 | **Bandeau de Confiance** (sources/score % sous chaque réponse) | #6 | 4 h | **P1** | ✅ |
| 52 | **Command Palette Ctrl+K** (recherche globale, actions rapides, navigation) | #5 | 3 j | **P2** | ✅ |
| 53 | **Thème clair/sombre** (toggle utilisateur, persisté dans config) | #5 | 2 j | **P2** | ✅ |
| 54 | **Animations fluides + micro-interactions** (transitions, glassmorphism, hover, loading) | #1, #3, #6 | 3 j | **P3** | ✅ |
| 55 | **Widget flottant Raycast/Spotlight** (barre de commande ⌘+Espace légère, overlay) | #2, #3 | 1 sem | **P3** | ⏳ |

> *Obsolète — le redesign DM-1 de V12 a déjà supprimé la sidebar, rendant la simplification sans objet.

---

## Scores par domaine (consensus des 7 audits)

| Domaine | #1 | #2 | #3* | #4 | #5** | #6*** | #7^ | Moyenne | Cible V15 |
|---------|----|----|-----|----|------|-------|-----|---------|-----------|
| Intelligence | 55 | 45 | 15 | 55 | 10/15 (67) | 5/10 (50) | 4/10 (40) | 52 | 65 |
| Mémoire | 60 | 40 | 5 | 40 | 10/15 (67) | 3/10 (30) | 3/10 (30) | 46 | 70 |
| RAG | 65 | 70 | 35 | 80 | 9/15 (60) | 7/10 (70) | 7/10 (70) | 68 | 78 |
| Agentivité | 35 | 50 | 10 | 20 | 8/15 (53) | 2/10 (20) | 2/10 (20) | 36 | 60 |
| Performance | 50 | 65 | 30 | 70 | 4/15 (27) | 6/10 (60) | 6/10 (60) | 55 | 65 |
| UX | 55 | 55 | 25 | 50 | 11/15 (73) | 5/10 (50) | 5/10 (50) | 55 | 70 |
| Sécurité | 60 | 60 | 40 | 35 | 14/15 (93) | 2/10 (20) | 6/10 (60) | 58 | 75 |
| Maintenabilité | 45 | 45 | 45 | 45 | 11/15 (73) | 4/10 (40) | 5/10 (50) | 49 | 70 |
| Vision produit | 70 | 85 | 85 | 90 | 14/15 (93) | 8/10 (80) | 6/10 (60) | 81 | — |

> *Audit #3 (29/100) outlier. **Audit #5 noté /15. ***Audit #6 noté /10. ^Audit #7 noté /10.
> Mémoire (46), Agentivité (36) et Maintenabilité (49) sont les domaines les plus faibles.

**Score global consensus : 55-60/100**

---

## Problèmes communs aux audits (priorité absolue)

| Problème | #1 | #2 | #3* | #4 | #5 | #6 | #7 | Action |
|----------|----|----|-----|----|----|----|----|--------|
| Duplication AgentOrchestrator | ✅ | — | — | — | — | ✅ | ✅ | Fusion |
| Guerre des mémoires (4 modules) | — | — | — | ✅ | — | ✅ | ✅ | Unifier |
| Privacy Layer non câblé | ✅ | — | — | — | — | — | — | Brancher |
| pyproject.toml cassé (PyQt6) | ✅ | ✅ | — | — | — | — | — | Corriger |
| RAG Injection / Path Traversal | — | — | — | ✅ | — | ✅ | ✅ | Sécuriser |
| Budget RAM critique / swapping | — | — | — | — | ✅ | ✅ | ✅ | VRAM Paging + chunks |
| Lost-in-the-Middle / HyDE | — | — | — | — | ✅ | ✅ | — | Désactiver + dynamique |
| Normalisation RRF biaisée | — | — | — | — | — | ✅ | — | Corriger |
| confidence_label trompeur | — | — | — | — | — | ✅ | — | Supprimer défaut |
| Perte structure tableaux DOCX | — | — | — | — | — | ✅ | — | Extraire en-têtes |
| Métadonnées dans embeddings | — | — | — | — | — | ✅ | — | Séparer |
| pysqlite3 → sqlite3 | — | — | — | — | — | ✅ | — | Remplacer |
| SQLite / Async Task Leaks | — | ✅ | — | — | — | ✅ | ✅ | try/finally + callbacks |
| Pas de benchmark RAG | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | Créer + dataset étendu |
| Pas de WorkingMemory | — | ✅ | ✅ | ✅ | — | ✅ | ✅ | Implémenter |
| Pas de ConfidenceCalibrator | — | ✅ | — | — | — | — | ✅ | Implémenter |
| Pas de ReflexionEngine | — | ✅ | — | ✅ | — | ✅ | ✅ | Implémenter |
| Pas de streaming tokens | — | — | ✅ | — | — | — | ✅ | Implémenter |
| Pas d'unload modèles RAM | — | — | ✅ | — | ✅ | ✅ | ✅ | Dynamic VRAM Paging |
| HyDE synchrone / UI bloquée | — | — | ✅ | ✅ | — | ✅ | ✅ | Async + Multiprocess |
| Reranker conditionnel/absent | — | ✅ | ✅ | ✅ | ✅ | ✅ | — | Rendre systématique |
| Sandbox outils absente | — | — | ✅ | ✅ | — | ✅ | ✅ | Implémenter |
| Tests morts (env. Linux sans MLX) | — | ✅ | — | ✅ | — | — | ✅ | Documenter |
| Identité (déjà externalisée) | — | ✅ | — | — | — | — | ✅ | Déjà fait |
| pipeline_offline (dépendances) | — | ✅ | — | — | — | — | — | Ajouter cachetools |
| sqlite_compat.py dangereux | ✅ | — | — | — | — | — | — | Supprimer |
| src/security/ orphelin | ✅ | — | — | — | — | — | — | Fusionner |
| Doublons logging (halluciné) | — | ✅ | — | ✅ | — | — | ✅ | Rien (fichier inexistant) |
| Tokenizer FR approximatif | — | — | — | ✅ | — | — | — | Tokenizer réel |
| Secrets dans les logs | — | — | — | ✅ | — | ✅ | ✅ | Filtrer |
| CI/CD absent | ✅ | ✅ | — | — | — | — | — | Mettre en place |
| .gitignore à nettoyer | — | — | — | — | — | ✅ | — | Ajouter fichiers |

---

## Métriques de succès V15

| Métrique | Actuelle | Cible V15 | Comment |
|----------|----------|-----------|---------|
| Temps première réponse | >10 s (swap) | **<3 s** | Mesure utilisateur critique |
| Temps jusqu'au 1er token | >3 s | **<0.5 s** | Streaming visible rapidement |
| Swap disque | Permanent | **0 swap** | Signe que RAM suffit |
| Recall@5 RAG | ~92% (5 docs) | **>70% (50 docs)** | Dataset étendu |
| RAM totale utilisée | ~8 Go (swap) | **<6 Go** | Marge pour contexte RAG |
| Hallucinations / session | ~3-5 | **<1** | Auto-évaluation + expert |
| Taux d'échec outils | ~20% | **<5%** | Agent loop fiable |

*Document créé le 7 juillet 2026 — Dernière mise à jour : intégration des 7 audits experts + 7 expertises DeepSeek, vérifications code réel (Expert #7).*

**90 propositions uniques** (31 P0, 23 P1, 27 P2, 9 P3) — 4 infirmées/vérifiées, 2 nuancées.
