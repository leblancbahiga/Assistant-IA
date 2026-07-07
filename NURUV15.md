# NURU V15 — Plan de consolidation

**Compilation des propositions retenues issues des audits experts**
Document évolutif — mis à jour à chaque nouveau rapport.

---

## Source : Audit #1 — Claude (Anthropic), 7 juillet 2026
*Fichier : `NURU_Audit_V15_2026-07-07.docx`*

## Source : Audit #2 — Cabinet d'architecture logicielle (rapport 1/2), juillet 2026
*Fichier : `AuditV15_1.md`*

## Source : Audit #3 — Cabinet d'architecture logicielle (rapport 2/2), juillet 2026
*Fichier : `AuditV15_2.md`*

> ⚠️ **Note sur ce rapport :** Score 29/100 significativement plus bas que les autres (54-58/100). Plusieurs critiques sont caduques (RRF, Query Rewriting, Hierarchical Chunker, MLX existent déjà dans le code V12). Ce rapport semble basé sur des patterns génériques plutôt qu'une lecture réelle du dépôt. Les propositions réellement nouvelles sont retenues ci-dessous.

## Source : Audit #4 — Cabinet d'architecture logicielle (rapport 3/3), juillet 2026
*Fichier : `AuditV15_3.md`*

> ✅ **Note sur ce rapport :** Score 54/100, cohérent avec le consensus. Lecture réelle du code. Apporte de nouveaux diagnostics précis (RAG Injection, guerre des 4 mémoires, HyDE synchrone, tokenizer approximatif).

## Source : Audit #5 — Rapport complémentaire, juillet 2026
*Fichier : `AuditV15_4.md`*

> ✅ **Note :** Score 71/100 (échelle différente /15). Le plus optimiste sur la vision produit (14/15), le plus sévère sur la performance (4/15). Apporte des diagnostics précis sur la RAM (breakdown chiffré), le *Lost-in-the-Middle*, la sur-utilisation de HyDE, et le chunking trop large. Propositions radicales : désactiver HyDE, réduire les chunks à 1000 car., Tauri.

## Source : Audit #6 — Audit global de maturité, juillet 2026
*Fichier : `AuditV15_5.md`*

> ✅ **Note :** Rapport le plus long (589 lignes), score 4.8/10 → 8.8/10 cible. Beaucoup de recoupements mais apporte des **bugs précis et actionnables** (confidence_label hardcodé, normalisation RRF biaisée, perte structure tableaux DOCX, métadonnées dans embeddings, pysqlite3, URL OpenRouter, async leaks).

## Source : Audit #7 — Rapport senior architectural complet, juillet 2026
*Fichier : `AuditV15_6.md`*

> ✅ **Note :** Rapport le plus structuré (828 lignes), scores 5.2/10 → 7.8/10 cible. Recoupe massivement les autres rapports mais apporte des détails uniques : Self-Consistency (3-way voting), architecture MemoryHub 6 types, ErrorRecovery + Verifier loop, et une roadmap V15-V17 cohérente de 6 mois. Pas de bugs nouveaux (tous déjà dans #4, #6).

---

### Diagnostic central (consensus des 7 audits)

> **Score global : consensus 55-60/100** (audits #1: 58/100, #2: 58/100, #3: 29/100 outlier, #4: 54/100, #5: 71/100 échelle /15, #6: 48/100, #7: 52/100)
>
> **Problème n°1 : le mur des 8 Go RAM.** Breakdown chiffré par l'audit #5 : macOS 2.5 Go + UI PySide6 0.5 Go + LLM 4-bit 4.2 Go = quasi rien pour RAG/embeddings/STT/TTS. Résultat : swapping permanent, latence, freeze. La priorité V15 est d'abord une guerre de la RAM.
>
> **Problème n°2 : métriques RAG non fiables.** L'audit #6 révèle que le Recall@5 à 92% est basé sur seulement 5 documents, la normalisation RRF est biaisée, et le confidence_label est hardcodé "HAUTE" en permanence. On ne peut pas trust les métriques actuelles.
>
> **Problème n°3 : fragmentation par duplication.** Code en double : 4 modules mémoire concurrents, 2 AgentOrchestrator, 2 couches sécurité.
>
> **Problème n°4 : Lost-in-the-Middle & HyDE contre-productif.** Les petits modèles locaux (3B 4-bit) reçoivent trop de contexte RAG (HyDE + MultiSearch), ignorent le milieu du prompt et hallucinent.
>
> **Problème n°5 : bugs concrets non résolus.** confidence_label, normalisation RRF, tableaux DOCX, pysqlite3, URL OpenRouter, fuites SQLite/async.
>
> **Problème n°6 : sécurité résiduelle.** RAG Injection / Path Traversal non mitigé.

---

### Propositions retenues

#### 🔴 P0 — Critique (avant V15 — quick wins)

| # | Proposition | Source | Effort |
|---|-------------|--------|--------|
| 1 | **Fusionner les 2 AgentOrchestrator** — `src/agent/orchestrator.py` (Planner/Executor/Verifier/Recovery, meilleure conception) avec `src/tools/agent_orchestrator.py` (seul réellement appelé). Garder un seul module. | #1 | 1-2 sem |
| 2 | **Brancher Privacy & Consent Layer** — `src/privacy/consent_layer.py` appelé avant tout accès capteur : voix, vision écran, MCP calendar/gmail. | #1 | 1-2 sem |
| 3 | **Corriger pyproject.toml** — remplacer PyQt6 par PySide6 + ajouter `[project.dependencies]` | #1, #2 | 1-2 h |
| 4 | **Supprimer/réparer les tests morts** — ⚠️ INFIRMÉ par vérification code réel (Expert #7) : les 12 fichiers non collectés échouent sur `ModuleNotFoundError: mlx` ou `PySide6` — dépendances Apple Silicon qu'un sandbox Linux ne peut installer. 738/815 tests passent ; 51 échecs + 26 erreurs réels à investiguer sur Mac. | #2 | 1 h |
| 5 | **Réparer `Orchestrator.pipeline_offline`** — ⚠️ INFIRMÉ par vérification (Expert #7) : le test passe après `pip install cachetools`. Le vrai problème est l'absence de `cachetools` dans `pyproject.toml` (déjà P0 #1). Pas un pipeline cassé. | #2 | 2 h |
| 6 | **Externaliser l'identité utilisateur** — ⚠️ INFIRMÉ par vérification code (Expert #7) : `nuru_core.py` contient zéro occurrence du nom/employeur. Un `src/identity_manager.py` dédié existe déjà. Externalisation déjà faite. | #2 | 2 h |
| 7 | **Supprimer `sqlite_compat.py`** — lecture mémoire brute CPython via `id()+offset`, risque de segfault latent | #1 | 10 min |
| 8 | **Fusionner `src/security/` dans `prompt_guard.py`** — une seule couche de sécurité | #1 | 1-2 h |
| 9 | **Résoudre les doublons de logging** — ⚠️ INFIRMÉ par vérification (Expert #7) : `logging_config.py` n'existe pas dans le dépôt. Le doublon est une hallucination du modèle d'audit. | #2 | 1 h |
| 10 | **Nettoyer les fichiers `_diag_*.py`, `_check_*.py`, `_test_*.py`** de la racine vers `scripts/` ou `tests/` | #1 | 1 h |
| 11 | **Streaming des tokens** — utiliser le callback de génération MLX pour envoyer les tokens un par un à l'UI (effet wow immédiat) | #3 | 1 j |
| 12 | **Unload des modèles après réponse** — purger le LLM de la VRAM 5s après génération pour libérer la RAM | #3 | 2 h |
| 13 | **Ajouter un test d'intégrité anti-collision de noms de classes** | #1 | 2-3 h |
| 14 | **Indicateur UI d'état interne** — cercle animé "Analyse des documents..." → "Génération..." pendant le RAG | #3 | 4 h |
| 15 | **Sécuriser RAG Injection & Path Traversal** — implémenter `sanitize_path()` dans `ingestion.py`, `FileGuard` pour valider `base_dir`, regex strictes PromptGuard | #4 | 4 h |
| 16 | **Rendre HyDE asynchrone** — wrapper les appels HyDE dans `asyncio.to_thread` pour débloquer l'EventLoop et libérer le thread principal | #4 | 2 h |
| 17 | **Réduire la taille max des chunks à 1000 car.** — les chunks 4000 car. actuels noient les petits modèles 4-bit (Lost-in-the-Middle) | #5 | 1 h |
| 18 | **Désactiver HyDE sur les modèles <7B** + activation dynamique par diversité de scores : si écart top-1/top-5 > 0.3, la requête est ambiguë → activer HyDE ; sinon BM25/vectoriel direct | #5, Expert #6 | 2 h |
| 19 | **Dynamic VRAM Paging** — déchargement agressif de TOUS les modèles (LLM, Whisper, TTS) dès qu'inactifs, RAMMonitor impitoyable | #5 | 4 h |
| 20 | **Limiter l'Agent Loop à 3 itérations max** — éviter les boucles infinies d'erreur sur les petits modèles | #5 | 1 h |
| 21 | **Corriger `confidence_label` hardcodé HAUTE** — NUANCE (Expert #7) : le gating (rag_engine.py:701-708) calibre HAUTE/MOYENNE/FAIBLE selon le score RRF, et ABSENT sur recherche vide est déjà appliqué (l.683). Reste HAUTE par défaut (l.671) mais commente non utilise pour le gating. Action : supprimer la valeur par defaut. | #6 | 15 min |
| 22 | **Corriger la normalisation RRF biaisée** — utiliser un `max_possible` fixe pour que les scores soient comparables entre strategies | #6 | 1 h |
| 23 | **Extraire les tableaux DOCX avec en-têtes** — préserver la structure des données tabulaires lors de l'ingestion | #6 | 2 h |
| 24 | **Séparer contenu et métadonnées dans les embeddings** — supprimer les préfixes `[Doc - Section]` qui diluent le signal sémantique (10-17% du chunk) | #6 | 1 h |
| 25 | **Remplacer `pysqlite3` par `sqlite3` standard** — corriger l'import incompatible | #6 | 30 min |
| 26 | **Corriger l'URL OpenRouter** — vérifier et mettre à jour l'endpoint API | #6 | 15 min |
| 27 | **Ajouter `try/finally` pour les connexions SQLite** — `rag_engine.py` ne ferme pas sur exception (fuites mémoire) | #6 | 1 h |
| 28 | **Ajouter `add_done_callback` pour les `create_task` async** — 3 tâches sans await dans `orchestrator.py` et `nuru_core.py` | #6 | 1 h |
| 29 | **Self-Consistency (3-way voting)** — générer 3 réponses indépendantes, voter par similarité cosinus, ne retenir que la plus consensuelle (-40% hallucinations). **⚠️ Coût : x3 RAM et latence** — nécessite d'abord VRAM Paging (#6) ou MoE (#30) pour être viable sur M1 8Go | #7 | 1 sem |
| 30 | **MemoryHub : architecture mémoire unifiée 6 types** — Working, Episodic, Semantic, Procedural, User, Error Memory + ConsolidationWorker (daemon 6h) + **Memory Router** (gate classifieur qui n'interroge que la mémoire pertinente — ex: factuel→Semantic, personnel→Episodic — gain -60% requêtes mémoire) | #7, Expert | 2 sem |
| 31 | **Décodage spéculatif (Speculative Decoding)** — petit modèle (SmolLM2-360M) prédit 5 tokens, Phi-4-mini valide. Gain : +50 à +150% de vitesse de génération sur M1. | Expert DeepSeek | 1 sem |

#### 🟡 P1 — Majeur (Sprint V15)

| # | Proposition | Source | Effort |
|---|-------------|--------|--------|
| 12 | **Implémenter WorkingMemory** — contexte de session persisté avec TTL, évite la perte de contexte entre les tours | #2 | 8 h |
| 13 | **Implémenter ConfidenceCalibrator** — score de fiabilité par réponse, exposé à l'utilisateur (FAIT / INFÉRENCE / HYPOTHÈSE) | #2 | 8 h |
| 14 | **Implémenter ReflexionEngine** — auto-critique + correction en 2 passes max. **⚠️ Coût : 2x tokens et latence** — nécessite d'abord décodage spéculatif ou optimisation pipeline M1 | #2 | 24 h |
| 15 | **Implémenter ProceduralMemory** — workflows appris par l'usage, NURU sait « comment faire » | #2 | 16 h |
| 16 | **Construire un harnais de benchmark RAG** — 30-50 paires question/document connu, mesure Recall@5/10, MRR, NDCG | #1, #2 | 8 h |
| 17 | **Activer le reranker systématiquement** (pas conditionnel) — qualité RAG constante | #2 | 4 h |
| 18 | *← Self-Consistency déjà en P0 #29 (déplacé pour ⚠️ coût RAM)* | — | — |
| 19 | **Nettoyer `nuru_core.py`** — supprimer ou archiver le pipeline V4 legacy (`process_query()`) | #1 | 2-3 j |
| 20 | **Small-to-Big Retrieval** — améliorer le chunking : récupérer petits chunks pertinents, puis document parent complet | #3 | 8 h |
| 21 | **Sandbox pour outils** — liste blanche de répertoires autorisés, protection contre injection via documents PDF | #3 | 8 h |
| 22 | **Unifier les 4 modules mémoire en un MemoryManager 6 couches** — `memory_store`, `memory/`, `long_term_memory`, `memory_bridge` doivent fusionner en un point d'entrée unique avec Episodic, Semantic, Procedural, User, Error, Working | #4 | 1 sem |
| 23 | **Implémenter le tokenizer réel de Phi-4** — remplacer `len(text) // 4` par le tokenizer HuggingFace/MLX pour un comptage fiable (surtout en français) | #4 | 4 h |
| 24 | **Semantic Router ultra-léger** — remplacer le routing LLM par embeddings + cosine similarity pour les requêtes de contrôle simples (0 inference LLM, RAM quasi nulle) | #5 | 8 h |
| 25 | **Time-Weighted Retrieval** — pondération temporelle des souvenirs épisodiques (les souvenirs récents ont plus de poids) | #5 | 8 h |
| 26 | **Remplacer BM25 maison par `rank_bm25` standard** — le BM25 actuel n'a pas d'IDF ni de normalisation correcte | #6 | 2 h |
| 27 | **Ajouter HNSW à sqlite-vec** — passage en recherche vectorielle approchée pour accélérer les requêtes | #6 | 4 h |
| 29 | **Dataset d'évaluation RAG étendu** — 20+ questions agronomiques pour fiabiliser le Recall@5 (actuellement 92% sur 5 docs seulement) | #6 | 4 h |
| 30 | **MoE logiciel local (LoRA-MoE)** — garder UN modèle de base en RAM, charger/décharger dynamiquement des adaptateurs LoRA ultra-légers (<50 Mo) par domaine : LoRA RAG & Extraction, LoRA Python Coding, LoRA Conversation. Variante plus réaliste que 5 modèles entiers sur M1 8 Go : même gain d'expertise, empreinte RAM quasi constante. | Expert DeepSeek | 2 sem |
| 31 | **RAMBudgetManager** — arbitre dynamique entre LLM, RAG, STT, TTS, UI. Alloue la RAM selon la tâche : sacrifie STT/TTS si conversation, réduit LLM context si RAG intensif. Évite le swap en priorisant les composants critiques. | Expert DeepSeek | 1 sem |
| 32 | **Speculative RAG** — un petit modèle (TinyLlama 1.1B) génère une réponse rapide sans RAG ; le RAG tourne en parallèle. Si docs pertinents trouvés (score >0.7), re-génère avec contexte. Sinon, garde la réponse rapide. Latence perçue : <500ms pour 80% des requêtes. | Expert DeepSeek | 1 sem |

#### 🔵 P2 — Modéré (Sprint V15+)

| # | Proposition | Source | Effort |
|---|-------------|--------|--------|
| 20 | **Intégrer SleepCycleManager** — consolidation mémoire pendant l'inactivité | #1, #2 | 16 h |
| 21 | **Implémenter GoalMemory + ProjectMemory** — suivi d'objectifs long terme | #2 | 40 h |
| 22 | **Étendre ToolRegistry** — création/modification fichiers, exécution scripts sandboxée | #2 | 40 h |
| 23 | **Implémenter FactChecker systématique** — vérification post-génération sur chaque réponse | #2 | 8 h |
| 24 | **Implémenter Learning Loop** — FeedbackCollector + StrategyOptimizer + ConsolidationWorker | #2 | 40 h |
| 25 | **Mettre à jour ROADMAP.md** — reflète l'état V12/V14 réel | #1 | 1 h |
| 26 | **ErrorRecovery + Verifier loop** — retry avec backoff, stratégie alternative, vérification output vs goal, rollback si destructif | #7 | 1 sem |
| 27 | **Caching modèle MLX + lazy loading** — mise en cache persistante des poids MLX, chargement différé des modules RAG/STT/TTS | #7 | 3 j |
| 28 | **Refonte Multiprocess (MVIC/Event-Driven)** — séparer l'UI PySide6, le backend Python, et le worker LLM dans des processus isolés pour éviter le blocage GIL | #3 | 1-2 sem |
| 29 | **Chunking dynamique** — ajuster la taille des chunks selon la longueur du document (1000 car. pour les docs <2000 car.) | #6 | 2 h |
| 30 | **Ajouter overlap de 20% au chunking** — éviter la perte de continuité sémantique | #6 | 1 h |
| 31 | **Filtrer les secrets dans les logs** — ajouter un filtre global pour masquer les clés API en cas d'erreur | #4 | 2 h |
| 32 | **CI/CD minimal** — GitHub Actions exécutant la suite de tests hors-M1 à chaque push | #1, #2 | 1 sem |
| 33 | **KV Cache Persistant** — conserver le cache d'attention entre sessions sur les mêmes sujets pour réduire latence, tokens et RAM | Expert DeepSeek | 1 sem |
| 34 | **Distillation domaine (LoRA NURU)** — créer un dataset Q&A agronomie/gestion projets/réfugiés + fine-tuning Phi-4-mini ou Qwen3-4B pour spécialiser NURU sans modèle géant. **Dataset formaté :** instructions structurées (format sortie, appels d'outils natifs, indicateurs confiance, style NURU cohérent) — LoRA 4-bit ~50-100 Mo | Expert DeepSeek | 2 sem |
| 35 | **FP8 / AWQ / QAT** — quantification différenciée : attention en FP16, FFN en 4-bit AWQ. Économie 15-20% RAM (700 Mo potentiels sur Phi-4). Vérifier compatibilité MLX sur M1. | Expert DeepSeek | 1 sem |
| 36 | **Vérifier GQA sur le modèle actuel** — si Phi-4 n'a pas Grouped Query Attention, changer pour Qwen2/Gemma2 qui en ont (cache KV 2-8x plus petit). Impact direct sur RAM et latence. | Expert DeepSeek | 2 j |
| 37 | **Plan de migration des données mémoire** — script de migration pour fusionner les 4 bases existantes (memory_store, long_term_memory, memory_bridge, memory/) en MemoryHub unifié sans perte. | Expert DeepSeek | 3 j |
| 38 | **Speculative Dreaming** — pendant l'inactivité (idle >5 min), NURU prédit les questions probables via l'agenda/projets/conversations récentes, pré-génère les réponses en cache. Hit rate cible : 30%. | Expert DeepSeek | 2 sem |
| 39 | **Distillation algorithmique (JSON natif au lieu de ReAct)** — fine-tuner le modèle pour émettre directement des commandes JSON au lieu du prompting ReAct (Thought→Action→Observation). Réduit la taille des prompts système de 60% et élimine les erreurs de format. | Expert DeepSeek | 1 sem |
| 40 | **Circuit Breaker Cloud** — max 5 appels cloud/h, cache agressif des réponses cloud (TTL 24h), fallback local automatique | Expert #6 | 2 h |
| 41 | **Batch Processing embeddings** — traiter les embeddings par lots de 32 (+2-3x vitesse indexation) | Expert #6 | 1 h |
| 42 | **Pruning 30% des poids** — supprimer les poids < seuil de magnitude (-30% RAM, perte qualité à tester) | Expert #6 | 1 sem |
| 43 | **Compression KV Cache style MLA (Multi-head Latent Attention)** — compression du cache d'attention similaire à DeepSeek MLA. Stocker le KV cache en format latent compressé au lieu de full key/value. Objectif : diviser la RAM dédiée au contexte par 2-4x. Complémentaire à GQA (#36). **Note : Qwen3.5-2B utilise déjà un pattern hybride linear/full attention** (1 couche sur 4 en pleine, reste en linéaire) — choix déjà aligné DeepSeek. | Expert #7 | 2 sem |

#### 🟢 P3 — Long terme

| # | Proposition | Source | Effort |
|---|-------------|--------|--------|
| 28 | **UI immersive** — animations fluides, transitions, micro-interactions, présence ambiante continue | #2 | 20 h |
| 29 | **PersonaEngine intégré** — personnalité cohérente dans le temps | #2 | 8 h |
| 30 | **Multi-appareils (LiveKit)** — voix distante, mémoire synchronisée | #2 | 30 h |
| 31 | **Tree of Thoughts** — pour les tâches complexes (après consolidation de l'agent loop) | #2 | 40 h |
| 32 | **Bandeau de Confiance dans l'UI** — afficher Sources, Faits, Inférences, Confiance % sous chaque réponse | #4 | 8 h |
| 35 | **Réévaluer ReAct/Reflexion/ToT avancé** — après mesures objectives du benchmark RAG | #1 | — |
| 36 | **Refonte UI en Tauri (Rust/Web)** — remplacer PySide6 pour diviser l'empreinte RAM de l'UI par 5 (<100 Mo) et obtenir des animations 60fps natives macOS | #5 | 2-3 mois |
| | *→ Avis expert : recommande P1 (Sprint 2-3) — 400 Mo de RAM récupérée sur 8 Go = 5% du total, significatif en tension permanente* | Expert | |

---

### Architecture cible (consolidée — 2 audits)

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
  logging_config.py vs infra/logging_setup.py → unifié
```

---

### Roadmap V15 (consolidée)

> **⚠️ Note expert :** La Phase 0 initiale (21 items en 24-48h) était irréaliste pour un seul développeur. Scindée ci-dessous.

#### Phase 0A — Stabilité critique (48h)
*Objectif : l'application ne crash plus, les fuites mémoire sont colmatées.*
| # | Action | Effort | Source |
|---|--------|--------|--------|
| 1 | pyproject.toml : PySide6 + dépendances de base | 1-2 h | #1, #2 |
| 2 | Supprimer sqlite_compat.py | 10 min | #1 |
| 3 | Supprimer/réparer les tests morts (3 fichiers) | 1 h | #2, #4 |
| 4 | Réparer pipeline_offline | 2 h | #2 |
| 5 | Externaliser l'identité utilisateur | 2 h | #2 |
| 6 | **Corriger `pysqlite3` → `sqlite3`** | 30 min | #6 |
| 7 | **Ajouter `try/finally` connexions SQLite** — fuites mémoire | 1 h | #6 |
| 8 | **Ajouter `add_done_callback` pour async tasks** — 3 create_task sans await | 1 h | #6 |
| 9 | **Corriger URL OpenRouter** | 15 min | #6 |

#### Phase 0B — Sécurité & Performance (1 sem)
*Objectif : le système fonctionne sans danger et sans bloquer l'UI.*
| # | Action | Effort | Source |
|---|--------|--------|--------|
| 10 | **Sécuriser RAG Injection & Path Traversal** — `sanitize_path()`, `FileGuard` | 4 h | #4 |
| 11 | **Rendre HyDE asynchrone** — `asyncio.to_thread` | 2 h | #4 |
| 12 | **Filtrer les secrets dans les logs** | 2 h | #4 |
| 13 | **Tokenizer réel de Phi-4** (remplacer `len//4`) | 4 h | #4 |
| 14 | **Réduire taille max chunks à 1000 car.** | 1 h | #5 |
| 15 | **Désactiver HyDE conditionnellement (<7B)** | 2 h | #5 |
| 16 | **Limiter Agent Loop à 3 itérations max** | 1 h | #5 |
| 17 | **Corriger `confidence_label` hardcodé "HAUTE"** | 30 min | #6 |
| 18 | **Corriger normalisation RRF biaisée** | 1 h | #6 |
| 19 | **Nettoyer .gitignore** | 15 min | #6 |
| 20 | Fusionner les doublons de logging | 1 h | #2, #4 |
| 21 | Archiver les fichiers _diag_* de la racine | 1 h | #1 |

#### Phase 1 — Dé-duplication (1-2 sem)
| # | Action | Effort |
|---|--------|--------|
| 8 | Fusionner les 2 AgentOrchestrator (agent/ + tools/) | 1-2 sem |
| 9 | Fusionner src/security/ → prompt_guard.py | 1-2 h |
| 10 | Nettoyer nuru_core.py (archiver V4 legacy) | 2-3 j |
| 11 | Nettoyer/nettoyer src/tools/orchestrator.py | 1 j |

#### Phase 2 — Câblage Privacy (1-2 sem)
| # | Action | Effort |
|---|--------|--------|
| 12 | Brancher consent_layer sur voix, vision, MCP | 1-2 sem |

#### Phase 3 — Mémoire & Unification (1-2 sem)
| # | Action | Effort |
|---|--------|--------|
| 13 | **Unifier les 4 modules mémoire en MemoryManager 6 couches** | 1 sem |
| 14 | Implémenter WorkingMemory | 8 h |
| 15 | Implémenter ProceduralMemory | 16 h |
| 16 | Intégrer SleepCycleManager | 8 h |

#### Phase 4 — Intelligence (1-2 sem)
| # | Action | Effort |
|---|--------|--------|
| 16 | Implémenter ConfidenceCalibrator | 8 h |
| 17 | Implémenter ReflexionEngine (2 passes) | 24 h |
| 18 | Implémenter Self-Consistency (3 votes) | 16 h |

#### Phase 5 — RAG & Mesure (1 sem)
| # | Action | Effort |
|---|--------|--------|
| 19 | Harnais de benchmark RAG (Recall@5/10, MRR, NDCG) | 8 h |
| 20 | Reranker systématique | 4 h |
| 21 | FactChecker systématique | 8 h |

#### Phase 6 — CI & Documentation (1 sem)
| # | Action | Effort |
|---|--------|--------|
| 22 | CI/CD GitHub Actions | 1 sem |
| 23 | ROADMAP.md à jour | 1 h |
| 24 | Test anti-collision de noms | 2-3 h |

---

### Scores par domaine (consensus des 7 audits)

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

> *Audit #3 (29/100) outlier. **Audit #5 noté /15. ***Audit #6 noté /10. ^Audit #7 noté /10. Mémoire reste le score le plus bas (46). Agentivité et Mémoire sont les domaines les plus consensuellement faibles.

**Score global consensus : 55-60/100**

---

### Problèmes communs aux audits (priorité absolue)

| Problème | #1 | #2 | #3* | #4 | #5 | #6 | #7 | Action |
|----------|----|----|-----|----|----|----|----|--------|
| Duplication AgentOrchestrator | ✅ | — | — | — | — | ✅ | ✅ | Fusion |
| Guerre des mémoires (4 modules) | — | — | — | ✅ | — | ✅ | ✅ | Unifier |
| Privacy Layer non câblé | ✅ | — | — | — | — | — | — | Brancher |
| pyproject.toml cassé (PyQt6) | ✅ | ✅ | — | — | — | — | — | Corriger |
| RAG Injection / Path Traversal | — | — | — | ✅ | — | ✅ | ✅ | Sécuriser |
| Budget RAM critique / swapping | — | — | — | — | ✅ | ✅ | ✅ | VRAM Paging + chunks réduits |
| Lost-in-the-Middle / HyDE polluant | — | — | — | — | ✅ | ✅ | — | Désactiver HyDE sur petits modèles |
| Normalisation RRF biaisée | — | — | — | — | — | ✅ | — | Corriger `max_possible` |
| confidence_label hardcodé | — | — | — | — | — | ✅ | — | Corriger |
| Perte structure tableaux DOCX | — | — | — | — | — | ✅ | — | Extraire avec en-têtes |
| Métadonnées dans embeddings | — | — | — | — | — | ✅ | — | Séparer contenu/métadonnées |
| pysqlite3 → sqlite3 | — | — | — | — | — | ✅ | — | Remplacer |
| SQLite / Async Task Leaks | — | ✅ | — | — | — | ✅ | ✅ | try/finally + callbacks |
| Pas de benchmark RAG | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | Créer + dataset étendu |
| Pas de WorkingMemory | — | ✅ | ✅ | ✅ | — | ✅ | ✅ | Implémenter |
| Pas de ConfidenceCalibrator | — | ✅ | — | — | — | — | ✅ | Implémenter |
| Pas de ReflexionEngine | — | ✅ | — | ✅ | — | ✅ | ✅ | Implémenter |
| Pas de streaming tokens | — | — | ✅ | — | — | — | ✅ | Implémenter |
| Pas d'unload modèles RAM | — | — | ✅ | — | ✅ | ✅ | ✅ | Dynamic VRAM Paging |
| UI bloquée / HyDE synchrone | — | — | ✅ | ✅ | — | ✅ | ✅ | Async + Multiprocess |
| Reranker (conditionnel/absent) | — | ✅ | ✅ | ✅ | ✅ | ✅ | — | Rendre systématique |
| Sandbox outils absente | — | — | ✅ | ✅ | — | ✅ | ✅ | Implémenter |
| Tests morts/imports cassés | — | ✅ | — | ✅ | — | — | ✅ | Réparer |
| Identité hardcodée | — | ✅ | — | — | — | — | ✅ | Externaliser |
| pipeline_offline cassé | — | ✅ | — | — | — | — | — | Réparer |
| sqlite_compat.py dangereux | ✅ | — | — | — | — | — | — | Supprimer |
| src/security/ orphelin | ✅ | — | — | — | — | — | — | Fusionner |
| Doublons logging | — | ✅ | — | ✅ | — | — | ✅ | Unifier |
| Tokenizer FR approximatif | — | — | — | ✅ | — | — | — | Tokenizer réel |
| Secrets dans les logs | — | — | — | ✅ | — | ✅ | ✅ | Filtrer |
| CI/CD absent | ✅ | ✅ | — | — | — | — | — | Mettre en place |
| .gitignore à nettoyer | — | — | — | — | — | ✅ | — | Ajouter .idea/ __pycache__/ .DS_Store |

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

*Document créé le 7 juillet 2026 — Mis à jour avec les 7 audits experts et 3 expertises DeepSeek.*
