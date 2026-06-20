# NURU V9/V10 — Architecture & Transformation
*De l'assistant conversationnel à l'IA personnelle agentique*

**Date** : 2026-06-11 | **Cible** : MacBook Pro M1 (8 Go RAM unifiée) | **Auteur** : Leblanc BAHIGA Mudarhi

> **Document de référence** compilant trois analyses d'experts pour la transformation
> complète de NURU V8+ en système agentique, mémoire unifiée, et auto-amélioration continue.

---

## Table des matières

1. [Diagnostic des limites actuelles](#1-diagnostic-des-limites-actuelles)
2. [Benchmark des architectures modernes](#2-benchmark-des-architectures-modernes)
3. [Architecture cible](#3-architecture-cible)
4. [Modules à créer](#4-modules-à-créer)
5. [Modules à refondre](#5-modules-à-refondre)
6. [Architecture mémoire détaillée](#6-architecture-mémoire-détaillée)
7. [Architecture agentique](#7-architecture-agentique)
8. [Architecture d'apprentissage continu](#8-architecture-dapprentissage-continu)
9. [Architecture d'auto-amélioration](#9-architecture-dauto-amélioration)
10. [Architecture des outils](#10-architecture-des-outils)
11. [Recommandations UI/UX](#11-recommandations-uiux)
12. [Plan d'implémentation](#12-plan-dimplémentation)
13. [Priorisation](#13-priorisation)
14. [Risques et atténuations](#14-risques-et-atténuations)
15. [Synthèse exécutive](#15-synthèse-exécutive)

---

## 1. Diagnostic des limites actuelles

### 1.1 Ce qui fonctionne bien dans NURU V8+

| Composant | Maturité | Commentaire |
|---|---|---|
| Pipeline RAG hybride (sqlite-vec + FTS5 + RRF) | ✅ **Avancé** | Multi-stratégie, HyDE, Query Rewriting, Early Stopping |
| Routage sémantique multi-niveaux | ✅ **Solide** | 5 niveaux avec regex `\b`, fallback offline |
| Compression TokenJuice | ✅ **Production** | -40–60 % tokens, 2 points d'injection |
| Multi-Provider LLM (Cloud) | ✅ **Robuste** | Circuit breaker, fallback Groq → OpenRouter → DeepSeek → Phi-4-mini |
| Vérification de faits | ✅ **Basique** | Post-génération, 1 retry max |
| Interface PySide6 | ✅ **Fonctionnelle** | 3 colonnes, thème cyberpunk, CoT visible |
| Dual-Write Nuru_Brain | ✅ **Opérationnel** | Export Markdown, Watchdog bidirectionnel |
| Sécurité macOS Keychain | ✅ **Correcte** | Stockage sécurisé des clés API |

### 1.2 Les sept lacunes structurelles

**L1 — Apprentissage factice**
`TraceCollector` enregistre les traces mais `MiningWorker` se limite à analyser les patterns d'échec textuels. Aucun mécanisme de rétroaction sur les stratégies de routage, les seuils RAG, ou les prompts. NURU accumule des données mais n'apprend pas.

**L2 — Mémoire documentaire uniquement**
`Nuru_Brain` est un dépôt de chunks exportés en Markdown. Il n'y a aucune distinction entre :
- Ce que NURU **sait** (mémoire sémantique)
- Ce que NURU **a fait** avec toi (mémoire épisodique)
- Comment NURU **doit faire** certaines tâches (mémoire procédurale)

**L3 — Absence d'agentivité**
Le pipeline est linéaire : `query → router → RAG → LLM → response`. Pas de planification, pas de décomposition de tâches, pas de boucle de vérification/correction autonome. L'état d'exécution n'est pas persisté.

**L4 — Interface inaccessible**
Le dashboard PySide6 documente 10+ pages mais beaucoup de métriques sont non fonctionnelles ou affichent des données placeholder. L'utilisateur ne voit pas ce que fait NURU en temps réel.

**L5 — Hallucinations non mesurées**
`EvidenceVerifier` et `StrictRAGGuard` existent mais aucun taux d'hallucination n'est mesuré, aucun confidence score n'est exposé à l'utilisateur, aucune distinction explicite fait/hypothèse/estimation dans les réponses.

**L6 — Absence d'outils**
NURU ne peut pas créer de fichiers, modifier des documents, exécuter des scripts, ou interagir avec le système de fichiers au-delà de l'indexation. C'est le verrou principal de l'agentivité.

**L7 — Raisonnement linéaire**
Le modèle génère une réponse en un seul passage. Aucune vérification intermédiaire, aucune exploration d'alternatives, aucune reformulation si la première tentative est insatisfaisante.

### 1.3 Métriques de performance actuelles (estimées)

| Métrique | Valeur actuelle | Cible V9 | Cible V12 |
|---|---|---|---|
| Recall@5 RAG | ~92 % | 95 % | 98 % |
| Taux d'hallucination | ~15–20 % | < 5 % | < 1 % |
| Taux de « je ne sais pas » correct | ~30 % | > 80 % | > 95 % |
| Temps de réponse moyen | 3–8 s | 2–5 s | 1–3 s |
| RAM au repos | ~3.5 Go | ~3.0 Go | ~2.5 Go |
| Taux de résolution tâches complexes | ~10 % | > 50 % | > 85 % |

---

## 2. Benchmark des architectures modernes

### 2.1 Tableau comparatif

| Système | Mémoire | Agentique | Auto-amélioration | Outils | RAM | Licence |
|---|---|---|---|---|---|---|
| **Letta / MemGPT** | ✅ 6 types (Core, Recall, Archival, Episodic, Semantic, Procedural) | ✅ Agent loop inner/outer monologue | ⚠️ Self-editing memory | ✅ Tools | ~2 Go | Apache 2.0 |
| **OpenHands (OpenDevin)** | ⚠️ EventLog append-only | ✅ Multi-step planning, sandbox | ❌ | ✅ Shell, browser, editor | ~4 Go | MIT |
| **Mem0** | ✅ Extraction + consolidation dynamique | ❌ (mémoire seule) | ✅ Consolidation auto | ❌ | ~1 Go | Apache 2.0 |
| **MIRIX** | ✅ 6 composants modulaires | ✅ Multi-agent | ⚠️ | ✅ | ~3 Go | Research |
| **BabyAGI** | ⚠️ Task list | ✅ Task-driven | ❌ | ✅ | ~1 Go | MIT |
| **AutoGPT** | ⚠️ Planification multi-étapes | ✅ Persistance d'objectifs | ❌ | ✅ | ~4 Go | MIT |
| **LangGraph** | ✅ State persistant (graphe) | ✅ Cycles conditionnels | ❌ | ✅ Tools | ~2 Go | MIT |
| **CrewAI** | ❌ Fenêtre glissante | ✅ Coordination multi-agents | ❌ | ✅ Tools | ~3 Go | MIT |
| **Reflexion (Shinn et al.)** | ✅ Mémoire épisodique d'échecs | ✅ Auto-critique + correction | ❌ | ❌ | ~1 Go | Research |
| **NURU V8+** | ⚠️ Nuru_Brain (Markdown) | ❌ Pipeline linéaire | ⚠️ Traces sans action | ❌ | ~3.5 Go | MIT |

### 2.2 Enseignements clés pour NURU

| Enseignement | Source | Application NURU |
|---|---|---|
| **Mémoire OS-like** (main ↔ archival avec paging) | Letta / MemGPT | `MemoryManager` avec 6 types, paging automatique |
| **Extraction dynamique de faits** depuis conversations | Mem0 | `ConsolidationWorker` extrait les faits récurrents |
| **Agent → Action → Observation** en boucle | OpenHands | `AgentOrchestrator` avec planification et vérification |
| **Self-editing memory** : l'agent modifie ses instructions | Letta | Mémoire procédurale éditable par l'utilisateur |
| **Reflexion** : auto-critique + révision | Reflexion | `ReflexionEngine` (max 2 passes sur M1) |
| **StateGraph** : état centralisé persistant | LangGraph | `StateManager` comme noyau de l'orchestrateur |
| **6 types mémoire séparés** | MIRIX | Architecture mémoire en couches strictes |

### 2.3 Avantages compétitifs de NURU à préserver

- **Privacy-first** : tout est local, pas de dépendance cloud obligatoire
- **Apple Silicon natif** : MLX, Metal, mémoire unifiée
- **RAG multi-stratégie mature** : RRF, HyDE, Query Rewriting déjà opérationnels
- **Interface desktop complète** : PySide6, pas besoin de repartir de zéro
- **Dual-Write Nuru_Brain** : transparence totale, ouvrable dans Obsidian

---

## 3. Architecture cible

### 3.1 Architecture en 7 couches (V9)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    COUCHE 7 — INTERFACE UTILISATEUR                  │
│  Dashboard V9 · Supervision Agents · Chat Enrichi · Artefacts       │
├─────────────────────────────────────────────────────────────────────┤
│                    COUCHE 6 — AGENT ORCHESTRATOR                     │
│  StateManager · Planner · TaskExecutor · Verifier · ErrorRecovery   │
│  ResumeManager · ReAct Loop                                         │
├─────────────────────────────────────────────────────────────────────┤
│                    COUCHE 5 — RAISONNEMENT AVANCÉ                    │
│  ReflexionEngine · SelfConsistency · TreeOfThoughts (P2)            │
│  ConfidenceCalibrator                                                │
├─────────────────────────────────────────────────────────────────────┤
│                    COUCHE 4 — MÉMOIRE UNIFIÉE                        │
│  EpisodicMemory · SemanticMemory · ProceduralMemory · UserMemory    │
│  ErrorMemory · WorkingMemory · ConsolidationWorker · MemoryRetriever│
├─────────────────────────────────────────────────────────────────────┤
│                    COUCHE 3 — APPRENTISSAGE CONTINU                  │
│  FeedbackCollector · PerformanceTracker · StrategyOptimizer         │
│  SelfEvaluator (RAGAS-like)                                          │
├─────────────────────────────────────────────────────────────────────┤
│                    COUCHE 2 — OUTILS & ACTION                        │
│  ToolRegistry · DocumentGenerator · CodeExecutor · WebResearcher    │
│  FileManipulator · DiagramBuilder                                    │
├─────────────────────────────────────────────────────────────────────┤
│                    COUCHE 1 — FONDATIONS (V8+ existant)              │
│  RAG Hybride · SemanticRouter · TokenJuice · LLM Local/Cloud        │
│  Multi-Provider · Nuru_Brain · TraceCollector                        │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Principes architecturaux

1. **Modularité stricte** : chaque couche est indépendante, communicante via EventBus
2. **Async-first** : tout est asynchrone, jamais de blocage UI
3. **RAM-budget** : chaque module a un budget mémoire, monitoré en temps réel
4. **Offline-first** : tout fonctionne sans cloud ; le cloud est un accélérateur optionnel
5. **Transparence totale** : chaque décision est traçable, explicable, auditable
6. **Graceful degradation** : si un module échoue, le système continue avec moins de capacités
7. **Self-bounding** : l'auto-amélioration est sandboxée, validée, réversible

### 3.3 Flux de traitement V9

```
REQUÊTE UTILISATEUR
        │
        ▼
[Cache Sémantique] ← hit → Réponse immédiate
        │ (miss)
        ▼
[TokenJuice] → compression
        │
        ▼
[IntentClassifier V9] ← nouveau, plus fin que SemanticRouter V6
        │
        ├── SIMPLE → [Phi-4-mini] → Réponse immédiate
        │
        ├── QUESTION → [RAG Pipeline V8+ amélioré] → Réponse avec sources
        │
        ├── TÂCHE COMPLEXE → [AgentOrchestrator]
        │       │
        │       ├── [Planner] → décompose en sous-tâches (≤ 5)
        │       ├── [TaskExecutor] → exécute chaque étape
        │       │       ├── Outil A (read_file, search_rag, search_web, etc.)
        │       │       ├── Outil B (generate_doc, execute_code, etc.)
        │       │       └── Outil C (create_diagram, query_db, etc.)
        │       ├── [Verifier] → vérifie chaque résultat intermédiaire
        │       ├── [ErrorRecovery] → retry / alternative / escalation
        │       └── [Synthesizer] → agrège les résultats → réponse finale
        │
        ├── APPRENTISSAGE → [Learning Loop V9]
        │       ├── [FeedbackCollector] → thumbs up/down + correction manuelle
        │       ├── [PerformanceTracker] → métriques par type de requête
        │       ├── [StrategyOptimizer] → ajuste seuils / prompts / routage
        │       └── [ConsolidationWorker] → consolide souvenirs
        │
        └── AUTO-AMÉLIORATION → [SelfImprovementEngine]
                ├── [PerformanceAnalyzer] → identifie points faibles
                ├── [PatchGenerator] → propose patches (diff)
                ├── [TestRunner] → exécute tests
                └── [SandboxedDeployer] → applique changements validés
        │
        ▼
[Réponse + Diagnostic + Sources + Confiance Score]
        │
        ▼
[TraceCollector V9] → enregistre TOUT (actions, outils, erreurs, feedback, temps)
```

---

## 4. Modules à créer

### 4.1 Couche Mémoire (P0 — Fondamental)

| Module | Fichier | Rôle | RAM | Inspiration |
|---|---|---|---|---|
| **EpisodicMemory** | `src/memory/episodic.py` | Stocke les événements vécus (conversations, actions, résultats) avec timestamp et contexte | ~50 Mo | Letta, MIRIX |
| **SemanticMemory** | `src/memory/semantic.py` | Connaissances consolidées (faits, concepts, relations) extraites des épisodes | ~80 Mo | Mem0 |
| **ProceduralMemory** | `src/memory/procedural.py` | Workflows appris (comment faire X), stockés en JSON avec schéma | ~30 Mo | MIRIX |
| **UserMemory** | `src/memory/user.py` | Modèle utilisateur évolutif (préférences, habitudes, contexte personnel) | ~20 Mo | Mem0 |
| **ErrorMemory** | `src/memory/errors.py` | Base des erreurs passées, leurs causes et leurs corrections | ~20 Mo | Reflexion |
| **WorkingMemory** | `src/memory/working.py` | Contexte de session courant (TTL, auto-expiration) | ~10 Mo | Letta |
| **ConsolidationWorker** | `src/memory/consolidation.py` | Daemon qui résume, fusionne, archive les souvenirs anciens (toutes les 6h) | ~100 Mo (pic) | Letta |
| **MemoryRetriever** | `src/memory/retriever.py` | Recherche multi-critères dans toutes les mémoires, fusion par pertinence | ~50 Mo | Mem0 |

**Signature unifiée :**

```python
class MemoryManager:
    """
    Gestion hiérarchique inspirée de MemGPT/Letta.
    Point d'entrée unique pour toutes les opérations mémoire.
    """
    working_memory: WorkingMemory    # Contexte actuel, ≤ 2000 tokens, volatile
    episodic_store: EpisodicStore    # SQLite, avec decay temporel
    semantic_store: SemanticMemory   # sqlite-vec, avec confidence score
    procedural_store: ProceduralMemory  # JSON, éditable par l'utilisateur
    user_store: UserMemory           # Profil utilisateur persistant
    error_store: ErrorMemory         # Évite de répéter les mêmes erreurs

    async def recall(self, query, memory_types=["episodic", "semantic", "procedural", "user"],
                     top_k=5, time_range=None, min_importance=0.0) -> dict:
        """Recherche multi-mémoire avec fusion par pertinence."""
```

**Clés de conception :**
- Chaque entrée a un `confidence_score` (0–1) et un `last_accessed`
- La mémoire épisodique décroît avec le temps (configurable)
- L'utilisateur peut annoter / corriger n'importe quelle entrée
- Sync bidirectionnel avec Nuru_Brain existant

### 4.2 Couche Agentique (P0)

| Module | Fichier | Rôle | RAM | Inspiration |
|---|---|---|---|---|
| **AgentOrchestrator** | `src/agent/orchestrator.py` | Boucle agentique principale : plan → exécuter → vérifier → synthétiser | ~100 Mo | OpenHands, Letta |
| **TaskPlanner** | `src/agent/planner.py` | Décompose un objectif en sous-tâches ordonnées avec dépendances | ~50 Mo | OpenHands |
| **TaskExecutor** | `src/agent/executor.py` | Exécute une tâche en appelant les outils appropriés via ToolRegistry | ~80 Mo | OpenHands |
| **TaskVerifier** | `src/agent/verifier.py` | Vérifie le résultat d'une tâche, détecte les erreurs et incohérences | ~50 Mo | Reflexion |
| **ErrorRecovery** | `src/agent/recovery.py` | Stratégies : retry (max 2), alternative, simplification, escalation | ~30 Mo | — |
| **ResumeManager** | `src/agent/resume.py` | Sauvegarde / restauration de l'état d'une tâche interrompue | ~20 Mo | — |
| **StateManager** | `src/agent/state.py` | Maintient le graphe d'état persistant de la session courante | ~30 Mo | LangGraph |

```python
class NuruPlanner:
    """Planificateur ReAct adapté M1 8 Go. Maximum 5 étapes par tâche, 3 retries par étape."""

    def plan(self, goal: str) -> TaskPlan:
        # 1. Décomposer le goal en sous-tâches
        # 2. Identifier les outils nécessaires
        # 3. Estimer la RAM nécessaire
        # 4. Ordonner les étapes avec dépendances
        pass

    def execute_step(self, step: TaskStep) -> StepResult:
        # ReAct : Thought → Action → Observation → Thought...
        pass

    def verify_result(self, result: StepResult) -> bool:
        # Reflexion : le résultat correspond-il à l'objectif ?
        pass
```

### 4.3 Couche Raisonnement (P1)

| Architecture | Pertinence NURU | Justification |
|---|---|---|
| **Reflexion** (Shinn et al.) | ✅ **Haute — P1** | Meilleur rapport qualité/coût. Auto-évaluation et correction sans infrastructure lourde. |
| **Self-Consistency** | ✅ **Haute — P1** | Simple (N appels LLM + vote majoritaire). Réduit significativement les hallucinations. |
| **Tree of Thoughts** (ToT) | ⚠️ **Moyenne — P2** | Utile pour planification, mais coûteux en tokens. Réserver aux tâches vraiment complexes. |
| **Graph of Thoughts** | ❌ **Pas pour V9/V10** | Trop complexe pour un assistant personnel. Overkill. |
| **Multi-Agent Debate** | ❌ **P3 uniquement** | Double/triple la consommation. Pas justifié sur M1 8 Go. |

**Modules à créer :**

| Module | Fichier | Rôle | RAM |
|---|---|---|---|
| **ReflexionEngine** | `src/reasoning/reflexion.py` | Boucle : génère → évalue → réfléchit → améliore (max 2 passes local, 3 si Groq) | ~100 Mo |
| **SelfConsistency** | `src/reasoning/self_consistency.py` | Génère 3 réponses indépendantes, vote majoritaire | ~80 Mo |
| **TreeOfThoughts** | `src/reasoning/tot.py` | Exploration arborescente avec pruning heuristique (P2) | ~150 Mo |
| **ConfidenceCalibrator** | `src/reasoning/calibrator.py` | Estime la probabilité de correction, calibre le seuil de « je ne sais pas » | ~30 Mo |

```python
class ReliabilityScorer:
    """Mesure et expose la fiabilité de chaque réponse. Objectif : taux d'hallucination < 1 %."""

    def classify_claims(self, response: str) -> List[Claim]:
        """Catégoriser chaque affirmation :
        FACT (citée dans sources) | INFERENCE (déductible) |
        HYPOTHESIS (spéculative) | UNKNOWN (non vérifiable)"""
        pass

    def compute_confidence(self, response: str, sources: List[Source]) -> float:
        """Score 0–1 basé sur : couverture sources, cohérence interne,
        présence de qualificateurs d'incertitude."""
        pass

    def format_with_tags(self, response: str, claims: List[Claim]) -> str:
        """Ajouter des marqueurs visuels dans l'UI :
        [FAIT] [INFÉRENCE] [HYPOTHÈSE] [SOURCE: doc.pdf p.12]"""
        pass
```

### 4.4 Couche Apprentissage (P0)

| Module | Fichier | Rôle | RAM |
|---|---|---|---|
| **FeedbackCollector** | `src/learning/feedback.py` | Collecte feedback utilisateur (👍👎, correction, « c'est faux ») | ~20 Mo |
| **PerformanceTracker** | `src/learning/tracker.py` | Mesure les performances par type de requête, outil, stratégie | ~30 Mo |
| **StrategyOptimizer** | `src/learning/optimizer.py` | Ajuste automatiquement seuils RAG (±0.05/semaine max), prompts, routage | ~50 Mo |
| **SelfEvaluator** | `src/learning/self_eval.py` | Évalue la qualité des réponses (faithfulness, relevance, precision, recall) | ~80 Mo |

### 4.5 Couche Outils (P1)

| Module | Fichier | Rôle | RAM |
|---|---|---|---|
| **ToolRegistry** | `src/tools/registry.py` | Registre central de tous les outils, descriptions format LLM | ~10 Mo |
| **DocumentGenerator** | `src/tools/docgen.py` | Crée Word, PDF, PowerPoint, Excel (python-docx, reportlab, python-pptx, openpyxl) | ~200 Mo |
| **CodeExecutor** | `src/tools/code_exec.py` | Exécute Python sandboxé (whitelist, timeout 30s, max 500 Mo) | ~100 Mo |
| **WebResearcher** | `src/tools/web_research.py` | Recherche web multi-sources, comparaison, détection contradictions | ~100 Mo |
| **FileManipulator** | `src/tools/file_manip.py` | Lecture/écriture/renommage/déplacement de fichiers | ~20 Mo |
| **DiagramBuilder** | `src/tools/diagram.py` | Génère diagrammes (Mermaid, graphviz, matplotlib) | ~80 Mo |

### 4.6 Couche Auto-Amélioration (P2)

| Module | Fichier | Rôle | RAM |
|---|---|---|---|
| **PerformanceAnalyzer** | `src/self_improve/analyzer.py` | Analyse les performances sur 7 jours, identifie les points faibles | ~50 Mo |
| **PatchGenerator** | `src/self_improve/patch_gen.py` | Génère des patches candidats avec tests associés | ~100 Mo |
| **TestRunner** | `src/self_improve/test_runner.py` | Exécute tous les tests (existants + générés) | ~80 Mo |
| **SandboxedDeployer** | `src/self_improve/deployer.py` | Applique les patches dans un clone, rollback si échec | ~50 Mo |

---

## 5. Modules à refondre

### 5.1 Refontes majeures

| Module actuel | Problème | Refonte nécessaire |
|---|---|---|
| `src/learning/trace_collector.py` | Collecte des traces sans boucle fermée | **TraceCollector V9** : enrichir chaque trace avec outcome, feedback, métriques |
| `src/learning/miner.py` | Détecte des patterns sans proposer d'actions | **StrategyOptimizer** : prend les patterns en entrée, produit des ajustements concrets |
| `src/nuru_brain.py` | Export Markdown, pas de mémoire structurée | **Nuru_Brain V2** : interface de visualisation de la mémoire unifiée (pas le stockage principal) |
| `src/core/router.py` (SemanticRouter) | 5 niveaux basés sur regex, pas assez fin | **IntentClassifier V9** : classification multi-niveaux avec LLM local pour les cas ambigus |
| `src/rag/fact_checker.py` | Simple post-check, 1 retry | **VerificationEngine** : vérification multi-couches (source, cohérence, calibration) |
| `src/core/orchestrator.py` | Pipeline linéaire, pas agentique | **AgentOrchestrator V9** : boucle agentique avec planification et vérification |
| `src/memory_store.py` | STM + cache sémantique, pas de mémoire long terme | **MemoryHub** : point d'entrée unique vers toutes les mémoires |
| `src/ui/dashboard.py` | Métriques non fonctionnelles, menus vides | **Dashboard V9** : supervision temps réel des agents, mémoire, apprentissage |

### 5.2 Modules à conserver tels quels

| Module | Raison |
|---|---|
| `src/token_juice.py` | Fonctionne parfaitement, -40–60 % tokens |
| `src/rag/multi_search.py` | Multi-stratégie mature : RRF, HyDE, décomposition |
| `src/rag/query_rewriter.py` | Query rewriting opérationnel |
| `src/rag/hyde.py` | HyDE bien implémenté |
| `src/rag/decomposer.py` | Circuit breaker, MAX=3 |
| `src/llm_local.py` | MLX Phi-4-mini, to_thread, apply_chat_template |
| `src/llm_cloud.py` | Multi-provider, circuit breaker, fallback |
| `~~src/profile_boost.py~~` | ~~Boost ×2.5 docs personnels~~ **SUPPRIMÉ** (V10.1 — tous fichiers égaux) |
| `src/auto_fetch.py` | Scan périodique, détection MD5 |

---

## 6. Architecture mémoire détaillée

### 6.1 Modèle conceptuel — 6 types de mémoire

```
┌──────────────────────────────────────────────────────────────┐
│                   MEMORY HUB (MemoryRetriever)                │
│   Point d'entrée unique pour toutes les opérations mémoire    │
│   API : recall(query, memory_types, top_k, time_range)        │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│   │   EPISODIC  │  │   SEMANTIC  │  │  PROCEDURAL │        │
│   │   MEMORY    │  │   MEMORY    │  │   MEMORY    │        │
│   │             │  │             │  │             │        │
│   │ Événements  │  │ Faits       │  │ Workflows   │        │
│   │ vécus avec  │  │ consolidés  │  │ appris      │        │
│   │ contexte    │  │ (concepts,  │  │ « comment   │        │
│   │ temporel    │  │  relations) │  │  faire X »  │        │
│   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│          │                │                 │                │
│   ┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐        │
│   │    USER     │  │    ERROR    │  │   WORKING   │        │
│   │   MEMORY    │  │   MEMORY    │  │   MEMORY    │        │
│   │             │  │             │  │  (Session)  │        │
│   │ Préférences │  │ Erreurs     │  │ Contexte    │        │
│   │ habitudes   │  │ passées +   │  │ courant     │        │
│   │ contexte    │  │ corrections │  │ (TTL)       │        │
│   └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                               │
├──────────────────────────────────────────────────────────────┤
│              CONSOLIDATION WORKER (daemon 6h)                 │
│  • Résume les épisodes anciens (> 30 jours)                  │
│  • Extrait les faits récurrents (≥ 3 mentions) → Semantic     │
│  • Détecte les workflows répétés → Procedural                │
│  • Fusionne les souvenirs redondants (cos > 0.90)            │
│  • Archive les erreurs corrigées                             │
└──────────────────────────────────────────────────────────────┘
```

### 6.2 Implémentation SQLite

**Stockage** : `~/.nuru/memory.db` — SQLite unique avec tables séparées par type de mémoire.

```sql
-- Mémoire épisodique
CREATE TABLE episodic_memory (
    id TEXT PRIMARY KEY,
    timestamp REAL,
    event_type TEXT,           -- 'conversation', 'action', 'tool_use', 'error', 'success'
    summary TEXT,              -- Résumé de l'événement
    context TEXT,              -- JSON : query, response, tools used, outcome
    embedding BLOB,            -- Embedding 768d pour recherche similaire
    importance REAL,           -- Score d'importance (0–1)
    access_count INTEGER,      -- Nombre de fois rappelée
    last_accessed REAL,        -- Dernier accès
    consolidated BOOLEAN       -- Déjà résumé par ConsolidationWorker
);

-- Mémoire sémantique
CREATE TABLE semantic_memory (
    id TEXT PRIMARY KEY,
    fact TEXT,                 -- Le fait : « Leblanc travaille pour YARID »
    category TEXT,             -- 'personal', 'professional', 'technical', 'general'
    confidence REAL,           -- Confiance dans le fait (0–1)
    source_episodes TEXT,      -- IDs des épisodes sources (JSON array)
    embedding BLOB,
    created_at REAL,
    updated_at REAL,
    access_count INTEGER
);

-- Mémoire procédurale
CREATE TABLE procedural_memory (
    id TEXT PRIMARY KEY,
    task_type TEXT,            -- Type de tâche : 'generate_report', 'analyze_document'
    steps TEXT,                -- JSON : liste des étapes
    tools_required TEXT,       -- JSON : outils nécessaires
    success_rate REAL,         -- Taux de succès historique
    avg_duration_ms REAL,
    last_used REAL,
    embedding BLOB
);

-- Mémoire utilisateur
CREATE TABLE user_memory (
    key TEXT PRIMARY KEY,
    value TEXT,
    category TEXT,             -- 'preference', 'habit', 'context', 'identity'
    confidence REAL,
    updated_at REAL,
    source TEXT                -- Comment cette info a été apprise
);

-- Mémoire des erreurs
CREATE TABLE error_memory (
    id TEXT PRIMARY KEY,
    timestamp REAL,
    error_type TEXT,           -- 'hallucination', 'wrong_routing', 'tool_failure'
    description TEXT,
    root_cause TEXT,
    correction TEXT,           -- Ce qui a été fait pour corriger
    related_query TEXT,
    embedding BLOB,
    resolved BOOLEAN
);

-- Working Memory (session courante)
CREATE TABLE working_memory (
    key TEXT PRIMARY KEY,
    value TEXT,
    ttl REAL,                  -- Time-to-live en secondes
    created_at REAL
);
```

### 6.3 Flux de consolidation

```python
async def consolidate():
    """Exécuté toutes les 6 heures par ConsolidationWorker."""

    # 1. Épisodes > 30 jours + importance < 0.3
    #    → Résumer en 1 épisode synthétique
    #    → Marquer anciens comme consolidated=True

    # 2. Patterns récurrents détectés (≥ 3 épisodes similaires)
    #    → Extraire fait → SemanticMemory.add()
    #    → Ex: 3 conversations sur YARID → « Leblanc travaille pour YARID »

    # 3. Workflows répétés (≥ 2 exécutions similaires)
    #    → Extraire procédure → ProceduralMemory.add()
    #    → Ex: 2 rapports générés de la même façon → workflow "generate_report"

    # 4. Erreurs corrigées
    #    → Stocker dans ErrorMemory avec correction
    #    → Prochaine fois : vérifier si pattern similaire avant d'agir

    # 5. Informations utilisateur nouvelles
    #    → Mettre à jour UserMemory
    #    → Ex: « Je préfère le français » → UserMemory.set('language', 'fr')
```

### 6.4 Budget RAM mémoire

| Composant | RAM usage | RAM idle |
|---|---|---|
| SQLite memory.db (fichier) | 0 (disk) | 0 |
| Index embeddings en mémoire (FAISS-like, ~10K souvenirs) | ~100 Mo | ~30 Mo |
| ConsolidationWorker (pic) | ~100 Mo | 0 |
| Cache working memory | ~10 Mo | ~10 Mo |
| **Total mémoire** | **~210 Mo** | **~40 Mo** |

---

## 7. Architecture agentique

### 7.1 Principe : ReAct minimal, pas d'orchestration multi-LLM

Le multi-agent (CrewAI, AutoGPT) est éliminé pour NURU V9 : trop de RAM, trop de latence, trop complexe à déboguer. NURU utilise un **agent unique ReAct** avec une boucle de réflexion optionnelle, exécutant les étapes de manière séquentielle (*single active model instance*).

### 7.2 Boucle principale

```
OBJECTIF UTILISATEUR
        │
        ▼
[IntentClassifier V9]
        │
        ├── SIMPLE / QUESTION → Pipeline RAG standard (V8+)
        │
        └── TÂCHE COMPLEXE → AgentOrchestrator
                │
                ▼
        ───────────────────────────────────────
         AGENT LOOP (ReAct + Reflexion)
        ───────────────────────────────────────

         1. [Planner]
            ├── Analyse l'objectif
            ├── Décompose en sous-tâches (≤ 5)
            ├── Identifie dépendances et outils nécessaires
            └── Produit un plan ordonné
                    │
                    ▼

         2. [TaskExecutor] (pour chaque tâche)
            ├── Sélectionne l'outil via ToolRegistry
            ├── Construit les paramètres
            ├── Exécute l'outil
            ├── Capture le résultat
            └── Stocke dans WorkingMemory
                    │
                    ▼

         3. [TaskVerifier]
            ├── Vérifie le résultat
            ├── Compare avec l'attendu
            ├── Détecte erreurs / incohérences
            └── Score de confiance
                    │
                ┌───┴───┐
                │  OK ?  │
                └───┬───┘
                 OUI│   NON
                    │      │
                    │      ▼
                    │   [ErrorRecovery]
                    │     ├── Retry (max 2)
                    │     ├── Alternative / Simplification
                    │     └── Escalation utilisateur
                    │      │
                    ▼      ▼
         4. Toutes les tâches terminées ?
            ├── NON → Retour à 2
            └── OUI → [Synthesizer]
                    │
                    ▼
         5. [Synthesizer]
            ├── Agrège tous les résultats
            ├── Vérifie cohérence globale
            ├── Génère la réponse finale
            └── Stocke dans EpisodicMemory
```

### 7.3 Exemple concret

> **Utilisateur** : « Analyse le dossier Walikale, rédige un rapport de 5 pages, crée un PowerPoint de 10 slides, génère une liste d'actions prioritaires. »

```
[Planner]
├── Tâche 1 : Analyser le dossier Walikale
│   ├── Outils : RAG(search), read_file
│   └── Dépendances : aucune

├── Tâche 2 : Rédiger rapport 5 pages
│   ├── Outils : DocumentGenerator(docx)
│   └── Dépendances : tâche 1

├── Tâche 3 : PowerPoint 10 slides
│   ├── Outils : DocumentGenerator(pptx)
│   └── Dépendances : tâche 1

└── Tâche 4 : Liste d'actions prioritaires
    ├── Outils : LLM(synthèse)
    └── Dépendances : tâche 1

[TaskExecutor] Tâche 1
├── RAG search "Walikale" → 12 chunks (score 0.78)
├── read_file("rapport_walikale_2025.pdf") → 8000 chars
├── Synthèse locale (Phi-4-mini) → résumé structuré
└── ✅ Stocké en working memory

[TaskVerifier] Tâche 1 → Score 0.85 → ✅ OK

[TaskExecutor] Tâches 2, 3, 4 (en parallèle si RAM disponible, sinon séquentiel)
├── DocumentGenerator(docx) → rapport.docx ✅
├── DocumentGenerator(pptx) → presentation.pptx ✅
└── LLM synthèse → actions.md ✅

[TaskVerifier] → Score 0.92 → ✅ OK

[Synthesizer]
├→ « Voici l'analyse du dossier Walikale... »
├→ Fichiers créés : rapport.docx, presentation.pptx, actions.md
└→ Stocké dans EpisodicMemory
```

### 7.4 Limites de sécurité

```python
AGENT_LIMITS = {
    "max_steps": 5,              # Pas de boucles infinies
    "max_retries_per_step": 3,
    "max_wall_time_seconds": 300,  # 5 minutes max par tâche
    "max_tool_calls_per_step": 3,
    "require_confirmation": ["edit_file", "execute_python", "run_git_commit"],
    "sandbox_only": ["execute_python"],
}
```

### 7.5 ErrorRecovery — Stratégies par type d'erreur

```python
class ErrorRecovery:
    STRATEGIES = {
        "tool_failure": ["retry", "alternative_tool", "simplify", "ask_user"],
        "timeout": ["retry_shorter", "partial_result"],
        "hallucination_detected": ["regenerate_strict_prompt", "fallback_to_rag"],
        "low_confidence": ["search_more_sources", "ask_user_clarification"],
        "ram_exceeded": ["reduce_batch_size", "unload_unused_models"],
        "network_error": ["retry_with_backoff", "offline_fallback"],
    }

    async def recover(self, task, error, attempt):
        if attempt >= task.max_retries:
            return RecoveryAction(action="escalate_to_user", message=str(error))
        strategy = self.STRATEGIES.get(error.type, ["retry"])
        chosen = strategy[min(attempt, len(strategy) - 1)]
        return RecoveryAction(action=chosen, params=self._build_params(...))
```

### 7.6 ResumeManager — Reprise de tâche interrompue

```python
class ResumeManager:
    async def save_state(self, task_id: str, state: dict):
        """Sauvegarde l'état courant dans SQLite."""
        await self.db.execute(
            "INSERT OR REPLACE INTO task_states VALUES (?, ?, ?)",
            (task_id, json.dumps(state), time.time())
        )

    async def resume(self, task_id: str) -> Optional[dict]:
        """Restaure l'état d'une tâche interrompue."""
        row = await self.db.execute(
            "SELECT state FROM task_states WHERE task_id = ?", (task_id,)
        )
        return json.loads(row[0]) if row else None

    async def list_interrupted(self) -> list[dict]:
        """Liste les tâches interrompues récentes."""
        rows = await self.db.execute(
            "SELECT task_id, state, timestamp FROM task_states ORDER BY timestamp DESC LIMIT 10"
        )
        return [{"task_id": r[0], "state": json.loads(r[1]), "interrupted_at": r[2]} for r in rows]
```

---

## 8. Architecture d'apprentissage continu

### 8.1 Trois boucles d'apprentissage

**Boucle 1 — Feedback immédiat (après chaque réponse)**

```python
# Données collectées : thumbs up/down, reformulation, temps de lecture
# Effet immédiat : ajustement du GoldMemory si correction explicite
# Effet différé : incrémentation du score d'erreur pour le pattern concerné
```

**Boucle 2 — Ajustement hebdomadaire (tâche de fond)**

```python
# Analyse des 7 derniers jours de traces
# Ajustements automatiques (plafonnés pour sécurité) :
#   - rag_score_threshold : ±0.05 max
#   - routing_confidence : ±0.03 max
#   - prompt_template : suggestions, validation manuelle
# Rapport : « Cette semaine NURU a ajusté 3 paramètres, appris 7 corrections »
```

**Boucle 3 — Consolidation mémoire mensuelle**

```python
# Épisodique → Sémantique : faits récurrents extraits et consolidés
# Épisodique → Procédurale : patterns de tâches identifiés
# Purge des mémoires obsolètes (score < seuil + ancienneté > N jours)
```

### 8.2 Ce qui n'est PAS fait (et pourquoi)

- **Pas de fine-tuning** : incompatible 8 Go RAM, instable, pas réversible
- **Pas de LoRA** : même contrainte + complexité disproportionnée
- **Pas de reward model entraîné** : RLHF nécessite un dataset de 10k+ exemples
- **Pas d'auto-modification des prompts sans validation** : risque de dérive

### 8.3 Métriques de performance trackées

```python
class PerformanceTracker:
    METRICS = {
        # RAG
        "rag_recall_at_5": float,         # % réponses avec score > 0.40
        "rag_avg_score": float,
        "rag_empty_rate": float,          # % requêtes sans résultat RAG
        "rag_hyde_trigger_rate": float,
        # Réponse
        "avg_response_time_ms": float,
        "hallucination_rate": float,       # % flaggé hallucination
        "citation_rate": float,            # % réponses avec citations
        "confidence_calibration": float,   # Corrélation confiance vs réalité
        # Agent
        "task_success_rate": float,
        "avg_steps_per_task": float,
        "error_recovery_success_rate": float,
        # Feedback
        "thumbs_up_rate": float,
        "thumbs_down_rate": float,
        "correction_rate": float,
        # Mémoire
        "memory_hit_rate": float,
        "error_memory_prevention_rate": float,
    }
```

### 8.4 StrategyOptimizer — Ajustement automatique

```python
class StrategyOptimizer:
    async def optimize(self, metrics: dict, history: list[dict]):
        adjustments = []

        # 1. Ajustement seuil RAG
        if metrics["rag_empty_rate"] > 0.30:
            new_threshold = max(0.25, config.rag_score_threshold - 0.05)
            adjustments.append(Adjustment(
                param="rag_score_threshold",
                current=config.rag_score_threshold,
                proposed=new_threshold,
                reason=f"rag_empty_rate={metrics['rag_empty_rate']:.2%} > 30%"
            ))

        # 2. Ajustement routage (hallucinations)
        if metrics["hallucination_rate"] > 0.10:
            adjustments.append(Adjustment(
                param="cloud_only_threshold",
                current=config.cloud_only_threshold,
                proposed=config.cloud_only_threshold * 0.8,
                reason=f"hallucination_rate={metrics['hallucination_rate']:.2%} > 10%"
            ))

        # 3. Ajustement prompt depuis ErrorMemory
        error_patterns = await self.error_memory.get_top_patterns(n=5)
        if error_patterns:
            adjustments.append(Adjustment(
                param="system_prompt_addition",
                current="",
                proposed=self._build_prompt_addition(error_patterns),
                reason=f"Top patterns: {[p['type'] for p in error_patterns]}"
            ))

        # 4. Appliquer avec validation
        for adj in adjustments:
            if await self._validate_adjustment(adj):
                await self._apply_adjustment(adj)
                await self._log_adjustment(adj)

    async def _validate_adjustment(self, adj) -> bool:
        """Simule l'impact sur un échantillon de traces historiques."""
        simulated = await self._simulate(adj)
        return all(simulated[k] >= self.CURRENT[k] * 0.95 for k in self.CRITICAL_METRICS)
```

### 8.5 SelfEvaluator — Évaluation RAGAS-like

```python
class SelfEvaluator:
    async def evaluate(self, query, response, sources, context) -> EvalResult:
        return EvalResult(
            faithfulness=await self._check_faithfulness(response, sources),
            answer_relevance=await self._check_relevance(query, response),
            context_precision=await self._check_precision(context, query),
            context_recall=await self._check_recall(context, sources),
            hallucination_score=await self._check_hallucination(response, sources),
        )

    async def _check_faithfulness(self, response, sources) -> float:
        claims = await self._extract_claims(response)
        supported = 0
        for claim in claims:
            if await self._verify_against_sources(claim, sources):
                supported += 1
        return supported / len(claims) if claims else 1.0
```

---

## 9. Architecture d'auto-amélioration

### 9.1 Principe : humain dans la boucle obligatoire

NURU peut **analyser** et **proposer**, jamais **déployer** sans approbation humaine.

```
┌────────────────────────────────────────────────────────────────────┐
│                SELF-IMPROVEMENT ENGINE (sandboxé)                  │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ⚠️ Ne modifie JAMAIS le code en production directement           │
│                                                                    │
│  1. [PerformanceAnalyzer] — J7                                      │
│     ├── Analyse les métriques des 7 derniers jours                │
│     ├── Identifie les modules sous-performants                    │
│     └── Produit un rapport circonstancié                          │
│                                                                    │
│  2. [PatchGenerator]                                                │
│     ├── Pour chaque problème → patch candidat (diff)              │
│     ├── Vérifie la syntaxe (AST parsing)                          │
│     └── Produit : {module, patch, expected_improvement, risk}      │
│                                                                    │
│  3. [TestRunner]                                                    │
│     ├── Exécute la suite de tests existante                       │
│     ├── Génère des tests spécifiques pour le patch                │
│     └── Si tous passent → patch validé                            │
│                                                                    │
│  4. [SandboxedDeployer]                                             │
│     ├── Applique le patch dans un clone du code                   │
│     ├── Exécute 10 requêtes de test (régression)                  │
│     ├── Compare métriques avant/après                             │
│     └── Si amélioration → propose à l'utilisateur                  │
│                                                                    │
│  5. [HumanApproval]                                                 │
│     ├── Présente le patch dans le dashboard                       │
│     ├── Affiche : problème, solution, tests, impact                │
│     ├── Accepté → git branch → apply → merge                      │
│     └── Refusé → enregistre dans ErrorMemory                       │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### 9.2 Sécurité — Contraintes strictes

```python
class SelfImprovementSafety:
    # Modules auto-améliorables (liste blanche)
    ALLOWED_MODULES = {
        "src/learning/optimizer.py",
        "src/reasoning/calibrator.py",
        "src/tools/docgen.py",
        "src/memory/consolidation.py",
    }

    # Modules INTERDITS
    FORBIDDEN_MODULES = {
        "src/core/orchestrator.py",
        "src/llm_local.py",
        "src/llm_cloud.py",
        "src/rag_engine.py",
        "src/memory/episodic.py",
        "src/agent/orchestrator.py",
    }

    # Contraintes sur les patches
    MAX_LINES_CHANGED = 50
    MAX_FILES_CHANGED = 3
    REQUIRE_TESTS_PASS = True
    REQUIRE_NO_NEW_IMPORTS = True
    MAX_EXECUTION_TIME_INCREASE = 1.2  # Pas plus de 20% plus lent
```

### 9.3 Périmètre autorisé

| Zone | Autorisé | Interdit |
|---|---|---|
| Prompts système | Suggestions seulement | Auto-modification |
| Seuils RAG | Ajustement ±0.05 auto | Dépassement des bornes |
| Code Python | PR avec tests | Déploiement sans validation |
| Mémoire | Consolidation auto | Suppression sans confirmation |
| Modèle LLM | Jamais | Jamais |

### 9.4 Sandbox — Implémentation

```python
class SelfImprovementSandbox:
    async def safe_execute_patch(self, patch: Patch) -> PatchResult:
        # 1. Clone le code dans un répertoire temporaire
        clone_dir = tempfile.mkdtemp(prefix="nuru_sandbox_")
        await self._clone_codebase(clone_dir)

        # 2. Applique le patch
        await self._apply_patch(clone_dir, patch)

        # 3. Exécute TOUS les tests
        test_result = await self._run_tests(clone_dir)
        if not test_result.passed:
            return PatchResult(success=False, reason="Tests échoués")

        # 4. Benchmark performance (10 requêtes de test)
        benchmark = await self._benchmark(clone_dir)
        if benchmark.regression_detected:
            return PatchResult(success=False, reason="Régression performance")

        # 5. Si tout passe → propose à l'utilisateur
        return PatchResult(
            success=True, patch=patch,
            test_result=test_result, benchmark=benchmark,
            requires_human_approval=True
        )
```

---

## 10. Architecture des outils

### 10.1 ToolRegistry — Registre central

```python
@dataclass
class Tool:
    name: str
    description: str               # Pour le LLM (function calling)
    parameters: dict               # JSON Schema
    tier: int                      # 1=readonly, 2=create, 3=modify
    estimated_ram_mb: float
    timeout_seconds: int
    requires_confirmation: bool
    sandbox: bool
    handler: Callable
```

### 10.2 Outils V9 (Phase 1 — 3 mois)

**Tier 1 — Lecture / Recherche (lecture seule, sans risque)**

| Outil | Description | RAM |
|---|---|---|
| `read_file` | Lecture PDF, DOCX, XLSX, TXT, Markdown | ~10 Mo |
| `list_directory` | Navigation `~/Documents`, `~/Nuru_Workspace` | ~5 Mo |
| `search_rag` | Recherche RAG existante (multi-stratégie) | ~50 Mo |
| `search_web` | DuckDuckGo + web_fetch (pas de clé API) | ~50 Mo |
| `search_memory` | RAG + mémoire épisodique/sémantique | ~30 Mo |
| `query_database` | SQL lecture seule sur SQLite locale | ~30 Mo |

**Tier 2 — Création (avec confirmation)**

| Outil | Description | RAM |
|---|---|---|
| `write_markdown` | Fichiers `.md` dans `~/Nuru_Workspace/` | ~10 Mo |
| `generate_document` | Word, PDF, PowerPoint, Excel (python-docx, reportlab, etc.) | ~200 Mo |
| `execute_python` | Sandbox subprocess, timeout 30s, modules whitelistés | ~100 Mo |
| `generate_diagram` | SVG/PNG via Mermaid, graphviz, matplotlib | ~80 Mo |

**Tier 3 — Modification (confirmation explicite)**

| Outil | Description | RAM |
|---|---|---|
| `edit_file` | Modification fichier existant | ~20 Mo |
| `run_git_commit` | Auto-PR pour self-improvement | ~30 Mo |

### 10.3 DocumentGenerator — Détail d'implémentation

```python
class DocumentGenerator:
    """Génère des documents Word, PDF, PowerPoint, Excel."""

    FORMATS = {"docx", "pdf", "pptx", "xlsx"}

    async def generate(self, format: str, content: dict, output_path: str):
        generators = {
            "docx": self._generate_word,
            "pdf": self._generate_pdf,
            "pptx": self._generate_powerpoint,
            "xlsx": self._generate_excel,
        }
        generator = generators.get(format)
        if not generator:
            raise ValueError(f"Format non supporté: {format}")
        await asyncio.to_thread(generator, content, output_path)

    def _generate_word(self, content, output_path):
        from docx import Document
        doc = Document()
        doc.add_heading(content.get("title", "Document"), 0)
        for section in content.get("sections", []):
            doc.add_heading(section["heading"], 1)
            for para in section.get("paragraphs", []):
                doc.add_paragraph(para)
            if "table" in section:
                table = doc.add_table(rows=len(section["table"]), cols=len(section["table"][0]))
                for i, row in enumerate(section["table"]):
                    for j, cell in enumerate(row):
                        table.rows[i].cells[j].text = str(cell)
        doc.save(output_path)

    def _generate_powerpoint(self, content, output_path):
        from pptx import Presentation
        prs = Presentation()
        for slide_data in content.get("slides", []):
            slide = prs.slides.add_slide(prs.slide_layouts[1])
            slide.shapes.title.text = slide_data.get("title", "")
            body = slide.placeholders[1]
            for point in slide_data.get("bullets", []):
                p = body.text_frame.add_paragraph()
                p.text = point
        prs.save(output_path)

    def _generate_excel(self, content, output_path):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = content.get("sheet_name", "Data")
        for row_idx, row in enumerate(content.get("data", []), 1):
            for col_idx, value in enumerate(row, 1):
                ws.cell(row=row_idx, column=col_idx, value=value)
        wb.save(output_path)

    def _generate_pdf(self, content, output_path):
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
        from reportlab.lib.styles import getSampleStyleSheet
        doc = SimpleDocTemplate(output_path, pagesize=A4)
        styles = getSampleStyleSheet()
        story = [Paragraph(content.get("title", "Document"), styles["Title"]), Spacer(1, 12)]
        for section in content.get("sections", []):
            story.append(Paragraph(section["heading"], styles["Heading1"]))
            for para in section.get("paragraphs", []):
                story.append(Paragraph(para, styles["Normal"]))
            story.append(Spacer(1, 12))
        doc.build(story)
```

### 10.4 CodeExecutor — Sandbox sécurisé

```python
class CodeExecutor:
    ALLOWED_MODULES = {
        "json", "csv", "math", "statistics", "datetime", "re",
        "collections", "itertools", "functools", "operator",
        "numpy", "pandas", "matplotlib", "seaborn",
    }
    MAX_EXECUTION_TIME = 30
    MAX_MEMORY_MB = 500
    MAX_OUTPUT_CHARS = 10000

    async def execute(self, code: str, timeout_s: int = None) -> ExecutionResult:
        timeout = timeout_s or self.MAX_EXECUTION_TIME
        if not self._check_imports(code):
            return ExecutionResult(success=False,
                error=f"Import non autorisé. Modules: {self.ALLOWED_MODULES}")

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._execute_in_sandbox, code), timeout=timeout)
            return result
        except asyncio.TimeoutError:
            return ExecutionResult(success=False, error=f"Timeout après {timeout}s")

    def _execute_in_sandbox(self, code: str) -> ExecutionResult:
        import subprocess, sys, tempfile, os
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code); temp_path = f.name
        try:
            result = subprocess.run([sys.executable, temp_path],
                capture_output=True, text=True, timeout=self.MAX_EXECUTION_TIME,
                env={**os.environ, "PYTHONUNBUFFERED": "1"})
            return ExecutionResult(
                success=result.returncode == 0,
                stdout=result.stdout[:self.MAX_OUTPUT_CHARS],
                stderr=result.stderr[:self.MAX_OUTPUT_CHARS],
                returncode=result.returncode)
        finally:
            os.unlink(temp_path)
```

### 10.5 Workspace isolé

```
~/Nuru_Workspace/
├── drafts/          # Fichiers en cours de création
├── exports/         # Fichiers finalisés
├── scripts/         # Scripts Python générés
├── sandbox/         # Exécution Python isolée
└── archive/         # Fichiers > 30 jours
```

---

## 11. Recommandations UI/UX

### 11.1 Problèmes actuels du dashboard

1. Métriques placeholder (RAM/LLM/RAG affichées mais non connectées)
2. Pages accessibles dans le menu mais vides ou non fonctionnelles
3. Aucune visibilité sur les tâches en cours (agentivité)
4. Aucun indicateur de fiabilité dans les réponses

### 11.2 Dashboard V9 — Maquette

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          NURU V9 — CyberDashboard                        │
├───────────┬──────────────────────────────────────┬───────────────────────┤
│           │                                      │                       │
│  SIDEBAR  │       ZONE CENTRALE                  │   PANNEAU DROIT      │
│  (200px)  │       (flexible)                     │   (280px)            │
│           │                                      │                       │
│ 🧠 NURU  │ ┌──────────────────────────────┐     │ ┌─────────────────┐  │
│    V9    │ │  CHAT                          │     │ │ MÉTRIQUES       │  │
│           │ │                                │     │ │ RÉELLES         │  │
│ 💬 Chat  │ │ [Conversation enrichie]        │     │ │                 │  │
│ 📋 Tâches│ │ [Bandeau fiabilité sous        │     │ │ RAM    3.2/8.0  │  │
│ 🧠 Mémoire│ │  chaque réponse]               │     │ │ Modèle   Phi-4  │  │
│ 🔧 Outils│ │ [Indicateur tâche active]      │     │ │ Mode       RAG  │  │
│ 📊 Stats │ │ [Zone de saisie]               │     │ │ Latence   1.2s  │  │
│ ⚙️ Config│ └──────────────────────────────┘     │ ├─────────────────┤  │
│           │                                      │ │ MÉMOIRE         │  │
│ ─────────│ ┌──────────────────────────────┐     │ │ Épisodique  142  │  │
│ 🔄 Tâches│ │  AGENT STATUS (si actif)      │     │ │ Sémantique   38  │  │
│ en cours │ │                                │     │ │ Procédurale  12  │  │
│           │ │ 📋 Plan: 4 étapes            │     │ ├─────────────────┤  │
│ ✅ Terminé│ │ ✅ Étape 1: Analyse dossier  │     │ │ FIABILITÉ 7j    │  │
│           │ │ 🔄 Étape 2: Rédaction        │     │ │ Confiance   83%  │  │
│           │ │ ⏳ Étape 3: PowerPoint       │     │ │ Correct.     7   │  │
│           │ │ ⏳ Étape 4: Actions          │     │ │ Agent   ○ Idle  │  │
│           │ │                                │     │ ├─────────────────┤  │
│           │ │ Progression: ████████░░ 50%   │     │ │ COÛT SESSION    │  │
│           │ └──────────────────────────────┘     │ │ Cloud: 1240 tok │  │
│           │                                      │ │ Local: 8500 tok │  │
│           │ ┌──────────────────────────────┐     │ └─────────────────┘  │
│           │ │  RAISONNEMENT (CoT enrichi)   │     │                       │
│           │ │                                │     │                       │
│           │ │ [Arbre de décision visible]   │     │                       │
│           │ │ [Étapes de vérification]      │     │                       │
│           │ │ [Sources consultées]          │     │                       │
│           │ └──────────────────────────────┘     │                       │
├───────────┴──────────────────────────────────────┴───────────────────────┤
│  STATUS: 🟢 Online | 🧠 42 souvenirs | 📊 15 tâches/mois | 💰 $0.12/mois │
└──────────────────────────────────────────────────────────────────────────┘
```

### 11.3 Nouvelles pages du dashboard

| Page | Contenu | Priorité |
|---|---|---|
| **Chat** (améliorée) | Conversation + Agent Status + Raisonnement + Bandeau fiabilité | P0 |
| **Tâches** | Liste des tâches en cours, terminées, interrompues. Reprise possible. | P0 |
| **Mémoire** | Visualisation des 6 types. Recherche. Édition manuelle. Suppression. | P0 |
| **Outils** | Liste des outils disponibles. Test manuel. Logs d'exécution. | P1 |
| **Statistiques** | Graphiques : RAG, hallucinations, feedback, coût, RAM | P1 |
| **Configuration** | Tous les paramètres : seuils, modèles, providers, mémoire, agent | P1 |
| **Fichiers créés** | Documents générés avec aperçu et téléchargement | P1 |
| **Auto-amélioration** | Patchs proposés, tests, validation, historique | P2 |

### 11.4 Bandeau de fiabilité sous chaque réponse

Sous chaque message de NURU, afficher :

```
[CONFIANCE: 87%] [SOURCES: 3] [MODE: RAG] [FAITS: 4 | INFÉRENCES: 2 | HYPOTHÈSES: 0]
```

Et si une tâche est en cours :

```
⚙ Étape 2/4 : création du rapport... [Annuler]  ████████░░ 50%
```

### 11.5 Règle d'or

> **Si une métrique n'est pas connectée à une vraie source de données, elle n'apparaît pas.**
> Mieux vaut 5 métriques vraies que 20 métriques placeholder.

### 11.6 Composants UI à créer

| Composant | Rôle | Fichier |
|---|---|---|
| **AgentStatusWidget** | État de l'agent (plan, progression) | `src/ui/components/agent_status.py` |
| **MemoryExplorer** | Explore et recherche dans les mémoires | `src/ui/components/memory_explorer.py` |
| **TaskListWidget** | Liste des tâches avec reprise | `src/ui/components/task_list.py` |
| **ReasoningTreeWidget** | Arbre de raisonnement visible | `src/ui/components/reasoning_tree.py` |
| **FeedbackBar** | Barre de feedback (👍👎✏️) sous chaque réponse | `src/ui/components/feedback_bar.py` |
| **MetricCard V2** | Carte métrique avec sparkline | `src/ui/components/metric_card_v2.py` |
| **ToolTesterWidget** | Test manuel d'un outil | `src/ui/components/tool_tester.py` |
| **CostTrackerWidget** | Suivi du coût cloud | `src/ui/components/cost_tracker.py` |

---

## 12. Plan d'implémentation

### 12.1 Feuille de route V9 → V12

#### V9 — Fondations Agentiques (Semaines 1–4)

| Semaine | Sprint | Livrables | RAM ajoutée |
|---|---|---|---|
| S1 | Mémoire | EpisodicMemory, SemanticMemory, UserMemory, MemoryRetriever, ConsolidationWorker, ErrorMemory | +210 Mo |
| S2 | Agent Loop | AgentOrchestrator, TaskPlanner, TaskExecutor, TaskVerifier, ErrorRecovery, ResumeManager | +300 Mo |
| S3 | Feedback | FeedbackCollector, PerformanceTracker, StrategyOptimizer, SelfEvaluator | +150 Mo |
| S4 | Dashboard V9 | AgentStatusWidget, MemoryExplorer, FeedbackBar, TaskListWidget, métriques réelles | +100 Mo |

**📊 Avancement V9 (11 juin 2026) :**

| Sprint | Statut | Modules créés | Tests |
|---|---|---|---|
| **S1 — Mémoire** | ✅ **Terminé** | schema, episodic, semantic, user, errors, retriever, manager, consolidation | **178 ✅** |
| **S2 — Agent Loop** | ✅ **Terminé** | types, planner, executor, verifier, recovery, resume, orchestrator | **88 ✅** |
| **S3 — Feedback** | ✅ **Terminé** | feedback, tracker, optimizer, self_eval | **67 ✅** |
| **S4 — Dashboard V9** | ✅ **Terminé** | agent_status, memory_explorer, feedback_bar, task_list + intégration dashboard.py | **86 ✅** |
| **S5 — Raisonnement** | ✅ **Terminé** | reflexion, consistency, confidence | **26 ✅** |
| **S6 — Outils** | ✅ **Terminé** | tool_registry, tool_executor, document_generator (Word/PDF/PPTX/XLSX) | **35 ✅** |
| **S7 — Web Research** | ✅ **Terminé** | web_researcher, search_optimizer | **24 ✅** |
| **S8 — Intégration** | ✅ **Terminé** | tests end-to-end (19) + benchmark (16) | **35 ✅** |
| **S9 — Dashboard V10** | ✅ **Terminé** | stats_page, tool_tester + intégration dashboard.py | **45 ✅** |
| **Total V9+V10** | **584 tests ✅** | **33 modules** | **0 échec** |

**✅ V9 — TERMINÉ (11 juin 2026)**

**Critères de succès V9 :**
- NURU exécute une tâche en 3 étapes (chercher → résumer → exporter)
- NURU se souvient des préférences d'une session à l'autre
- NURU apprend de ses erreurs (ErrorMemory empêche les mêmes erreurs)
- Le dashboard montre l'état de l'agent en temps réel
- RAM totale < 5.5 Go

#### V10 — Raisonnement & Outils (Semaines 5–10)

| Semaine | Sprint | Livrables | RAM ajoutée |
|---|---|---|---|
| S5 | Raisonnement | ReflexionEngine, SelfConsistency, ConfidenceCalibrator | +200 Mo |
| S6 | Outils docs | DocumentGenerator (Word, PDF, PPT, Excel), DiagramBuilder | +300 Mo |
| S7 | Web Research | WebResearcher multi-sources, comparaison, détection contradictions | +150 Mo |
| S8 | Intégration | CodeExecutor sandboxé, ToolRegistry complet, FileManipulator | +200 Mo |
| S9 | Dashboard | Stats, cost tracker, MemoryExplorer, ToolTester | +50 Mo |
| S10 | Polish & Tests | Tests intégration, benchmark RAM, documentation | 0 |

**Critères de succès V10 :**
- NURU crée un rapport Word + PowerPoint à partir de données locales
- NURU fait une recherche web et compare 3 sources
- Taux d'hallucination < 5 %
- NURU dit « je ne sais pas » correctement dans > 80 % des cas
- RAM totale < 6.5 Go

#### V11 — Auto-Amélioration (Semaines 11–14)

| Semaine | Sprint | Livrables | RAM ajoutée |
|---|---|---|---|
| S11 | Self-Improve | PerformanceAnalyzer, PatchGenerator, TestRunner, SandboxedDeployer | +300 Mo |
| S12 | Procédural | ProceduralMemory, workflows appris, ResumeManager avancé | +100 Mo |
| S13 | Dashboard | Auto-amélioration UI (diff view, approval), notifications | +50 Mo |
| S14 | Tests & Polish | Tests unitaires auto-générés, benchmark final | 0 |

**Critères de succès V11 :**
- NURU propose au moins 1 amélioration par semaine
- NURU apprend des workflows récurrents
- NURU reprend une tâche interrompue
- RAM totale < 7.0 Go

#### V12 — Maturité (Semaines 15–20)

| Semaine | Sprint | Livrables | RAM ajoutée |
|---|---|---|---|
| S15 | Multi-Agent | MultiAgentDebate (2 agents max) — optionnel | +500 Mo |
| S16 | Knowledge Graph | KnowledgeGraph basique — optionnel | +500 Mo |
| S17–18 | Production | Stress tests, optimisation RAM, profiling | 0 |
| S19–20 | Release | V12 stable, benchmark final, documentation complète | 0 |

**Critères de succès V12 :**
- Taux d'hallucination < 1 %
- Taux de résolution tâches complexes > 85 %
- RAM totale < 7.5 Go
- 100 % des fonctionnalités documentées et testées

### 12.2 Détail Sprint 1 — Mémoire (Semaine 1)

| Jour | Tâche | Fichier | Durée |
|---|---|---|---|
| J1 | Créer memory.db + schéma SQL | `src/memory/schema.py` | 2h |
| J1 | EpisodicMemory.add() + recall() | `src/memory/episodic.py` | 3h |
| J2 | SemanticMemory.add() + recall() | `src/memory/semantic.py` | 3h |
| J2 | UserMemory.get() + set() + update() | `src/memory/user.py` | 2h |
| J3 | MemoryRetriever.recall() multi-type | `src/memory/retriever.py` | 3h |
| J3 | Intégration dans orchestrator | `src/core/orchestrator.py` | 2h |
| J4 | ConsolidationWorker (daemon 6h) | `src/memory/consolidation.py` | 4h |
| J4 | ErrorMemory.add() + check_similar() | `src/memory/errors.py` | 2h |
| J5 | Tests unitaires + intégration | `tests/test_memory.py` | 4h |
| J5 | Documentation + commit | `docs/MEMORY.md` | 1h |

---

## 13. Priorisation

### 13.1 Matrice valeur / coût

```
                    IMPACT UTILISATEUR
                    ▲
                    │
          HAUTE     │  ★ Mémoire unifiée     ★ Agent loop basique
                    │  ★ Feedback loop        ★ Dashboard V9
                    │
                    │  ☆ Reflexion           ☆ Outils document
                    │  ☆ Recherche web        ☆ Auto-amélioration
                    │
          BASSE     │  ○ Multi-agent debate   ○ Knowledge graph
                    │
                    └──────────────────────────────────────►
                         BASSE              HAUTE
                              COÛT (RAM + Complexité)

Légende : ★ P0  ☆ P1  ○ P2–P3
```

### 13.2 Classement final

| Rang | Fonctionnalité | Impact | Coût RAM | Complexité | ROI |
|---|---|---|---|---|---|
| 1 | Mémoire unifiée (6 types) | ⭐⭐⭐⭐⭐ | +210 Mo | Moyenne | 🏆 **Exceptionnel** |
| 2 | Feedback Loop fermé | ⭐⭐⭐⭐⭐ | +150 Mo | Moyenne | 🏆 **Exceptionnel** |
| 3 | Agent loop basique (plan → exécuter → vérifier) | ⭐⭐⭐⭐⭐ | +300 Mo | Haute | **Excellent** |
| 4 | Dashboard V9 (métriques réelles) | ⭐⭐⭐⭐ | +100 Mo | Moyenne | **Excellent** |
| 5 | Reflexion + Self-Consistency | ⭐⭐⭐⭐ | +180 Mo | Moyenne | **Très bon** |
| 6 | DocumentGenerator (Word, PDF, PPT, Excel) | ⭐⭐⭐⭐ | +200 Mo | Moyenne | **Très bon** |
| 7 | ConfidenceCalibrator + « je ne sais pas » | ⭐⭐⭐⭐ | +30 Mo | Faible | **Très bon** |
| 8 | WebResearcher | ⭐⭐⭐ | +150 Mo | Moyenne | Bon |
| 9 | CodeExecutor sandboxé | ⭐⭐⭐ | +100 Mo | Moyenne | Bon |
| 10 | SelfImprovementEngine | ⭐⭐⭐ | +300 Mo | Haute | Bon (long terme) |
| 11 | ProceduralMemory | ⭐⭐⭐ | +50 Mo | Moyenne | Bon |
| 12 | Multi-Agent Debate | ⭐⭐ | +500 Mo | Haute | Faible |
| 13 | Knowledge Graph | ⭐⭐ | +300 Mo | Haute | Faible |

### 13.3 Recommandation d'implémentation

1. **Mémoire unifiée** — Socle de tout. Sans mémoire, pas d'apprentissage, pas d'agent, pas d'amélioration.
2. **Feedback Loop** — NURU apprend immédiatement des corrections utilisateur.
3. **Agent loop basique** — Transforme NURU d'un moteur de réponses en exécuteur de tâches.
4. **Dashboard V9** — Rend visible ce que fait NURU, essentiel pour la confiance.
5. **Reflexion** — Améliore la qualité sans infrastructure lourde.
6. **DocumentGenerator** — Fort impact utilisateur, fonctionnalité très demandée.
7. **Le reste** — Selon le temps disponible et les retours utilisateur.

Ces quatre premiers modules (1–4) représentent **80 % de la valeur perçue** de NURU V9, pour **~30 % de la complexité totale** du plan.

---

**➡️ Prochaine étape : Sprint 10 — Polish & Tests (intégration finale)**

---

## ⚠️ PROBLÈMES CONNUS — RAG & Documents (11 juin 2026)

### Statut : 🔴 NON RÉSOLU

**Problème principal :** NURU n'accède pas correctement au contenu des documents utilisateur.

### Symptômes observés

1. **Question "Parle-moi de BEACCOM"** → NURU répond avec des connaissances generiques (pas les documents)
2. **Spotlight trouve les fichiers** mais le LLM ignore le contexte
3. **Escalade Cloud** quand RAM basse → le contexte Spotlight n'est pas envoyé au LLM
4. **Prompt trop long** quand le contexte est inclus → context_length_exceeded

### Ce qui a été essayé (sans succès complet)

| Tentative | Résultat |
|---|---|
| Ajout de mots-clés RAG (beaccom, rikolto, etc.) | ✅ Le routeur classe maintenant LOCAL_RAG |
| SpotlightSearch avec lecture de contenu | ✅ Spotlight trouve et lit les fichiers |
| Filtrage fichiers du projet | ✅ Spotlight ne retourne plus les .py du projet |
| Extraction termes clés | ✅ "parle-moi de BEACCOM" → recherche "beaccom" |
| Contexte Spotlight dans le prompt | ✅ 9,430 chars de contexte injectés |
| Spotlight contourne escalade RAM | ✅ Pas d'escalade Cloud pour Spotlight |
| Troncation contexte à 3000 chars | ✅ Évite les prompts trop longs |

### Ce qui ne fonctionne toujours pas

1. **Le LLM ignore le contexte Spotlight** — malgré 9,430 chars de contexte, le Cloud répond avec ses connaissances
2. **Le RAG index est insuffisant** — seulement 1,024 chunks pour 977 fichiers
3. **La réindexation n'a pas abouti** — le script timeout après 300s
4. **Le pipeline n'est pas cohérent** — le routeur retourne LOCAL_RAG mais l'orchestrateur passe en Cloud

### Pistes de solution à explorer

1. **Forcer l'utilisation du contexte** — modifier le prompt pour que le LLM DOIVE utiliser le contexte fourni
2. **Réindexation complète** — relancer la réindexation des 977 fichiers avec un timeout plus long
3. **Bypasser le Cloud quand le contexte Spotlight existe** — ne jamais passer en Cloud si Spotlight a trouvé du contenu
4. **Utiliser le modèle local** quand le contexte est disponible (pas besoin de Cloud)
5. **Vérifier l'envoi du contexte** — s'assurer que rag_context contient bien le Spotlight context quand il arrive au LLM

### Fichiers concernés

- `src/rag/spotlight.py` — SpotlightSearch
- `src/rag/smart_search.py` — SmartSearch
- `src/semantic_router.py` — Routeur Always-RAG
- `src/core/router.py` — Escalade RAM
- `src/core/orchestrator.py` — Pipeline de génération
- `scripts/reindex_all.py` — Script de réindexation (n'a pas abouti)

---

## 14. Risques et atténuations

### 14.1 Matrice des risques

| Risque | Probabilité | Impact | Atténuation |
|---|---|---|---|
| **Dépassement RAM (> 8 Go)** | 🔴 Haute | 🔴 Critique | Budget RAM strict par module. Monitoring temps réel avec kill switches. Fallback offline si > 7.5 Go. |
| **Boucle agentique infinie** | 🟠 Moyenne | 🟠 Élevé | Max 10 étapes, timeout 5 min, circuit breaker par outil, détection pattern répété. |
| **Auto-amélioration casse le système** | 🟠 Moyenne | 🔴 Critique | Sandbox obligatoire. Tests avant déploiement. Rollback auto. Whitelist de modules. Review humaine. |
| **Mémoire divergente (contradictions)** | 🟡 Faible | 🟠 Élevé | ConsolidationWorker détecte contradictions. Confidence score par souvenir. |
| **LLM local trop faible** | 🟠 Moyenne | 🟠 Élevé | Fallback cloud systématique pour tâches complexes. Phi-4-mini : trivial uniquement. |
| **Latence excessive (> 30 s)** | 🟠 Moyenne | 🟡 Moyen | Streaming étapes intermédiaires. Timeout par étape. Annulation possible. |
| **Fuite mémoire (embeddings, caches)** | 🟠 Moyenne | 🟡 Moyen | GC explicite après usage. TTL sur tous les caches. Monitoring RSS. |
| **SQLite lock (concurrence)** | 🟡 Faible | 🟡 Moyen | Mode WAL activé. Connexions courtes. Retry with backoff. |
| **Hallucination du PatchGenerator** | 🟠 Moyenne | 🔴 Critique | Tests obligatoires. Validation AST. Pas de nouveaux imports. Review humaine. |
| **Feedback utilisateur biaisé** | 🟡 Faible | 🟡 Moyen | Pondération des feedbacks. Détection de patterns abusifs. |

### 14.2 RAMGuard — Monitoring temps réel

```python
class RAMGuard:
    THRESHOLDS = {
        "warning": 6.0,     # Go — Alerte dashboard
        "critical": 7.0,    # Go — Décharge modules non essentiels
        "emergency": 7.5,   # Go — Force offline, tue daemons
    }

    async def monitor(self):
        while True:
            ram_used = psutil.virtual_memory().used / (1024**3)
            if ram_used > self.THRESHOLDS["emergency"]:
                await self._emergency_mode()
            elif ram_used > self.THRESHOLDS["critical"]:
                await self._unload_non_essential()
            elif ram_used > self.THRESHOLDS["warning"]:
                self.dashboard.show_warning(f"RAM: {ram_used:.1f}/8.0 Go")
            await asyncio.sleep(5)

    async def _unload_non_essential(self):
        if self.reranker.is_loaded():
            await self.reranker.unload()
        self.memory_store.clear_cache()
        self.working_memory.truncate(max_items=5)
```

### 14.3 Plan de contingence global

| Scénario | Action automatique |
|---|---|
| RAM > 7.5 Go | Mode offline forcé, déchargement reranker, vidage cache |
| Agent loop > 5 min | Annulation + résumé + proposition de reprise |
| 3 erreurs consécutives sur un outil | Désactivation temporaire + notification utilisateur |
| Auto-amélioration échoue 3 fois | Désactivation du module SelfImprovement pour 24h |
| LLM cloud indisponible > 1 min | Bascule automatique en mode local_only |
| Mémoire corrompue | Restauration depuis dernier backup (daily) |
| Dashboard crash | Redémarrage auto du processus UI (le backend continue) |

### 14.4 R1 — Saturation RAM (risque élevé)

**Atténuation :**
- Budget RAM strict par module (Section 6.4)
- Circuit breaker RAM : si > 6.5 Go → désactiver Reflexion + router vers Groq
- Profiling RAM à chaque PR avec benchmark
- Offloading auto de l'index sémantique si non utilisé

### 14.5 R2 — Régression qualité RAG (risque moyen)

**Atténuation :**
- Ajustements plafonnés (±0.05 par semaine)
- A/B test automatique sur 50 requêtes avant application
- Rollback possible en un clic depuis le dashboard

### 14.6 R3 — Sécurité du sandbox Python (risque élevé)

**Atténuation :**
- subprocess avec `os.setuid` (utilisateur restreint) — si possible
- Whitelist des imports autorisés
- Pas d'accès réseau depuis le sandbox
- Workspace isolé (`~/Nuru_Workspace/sandbox/`)
- Timeout strict 30s
- Log de chaque exécution

### 14.7 R4 — Dérive de l'auto-amélioration (risque moyen)

**Atténuation :**
- Humain dans la boucle obligatoire
- Tests unitaires générés avec le code proposé
- Branche Git dédiée, jamais merge direct sur `main`
- Revue manuelle obligatoire avant PR

### 14.8 R5 — Latence accrue (risque moyen)

**Atténuation :**
- Timer de progression dans l'UI (l'utilisateur voit ce qui se passe)
- Streaming partiel : résultats intermédiaires affichés
- Budget temps configurable par tâche (défaut : 60s)
- Désactivation optionnelle du Planner pour questions simples

### 14.9 R6 — Complexité de maintenance (risque bas→moyen)

**Atténuation :**
- Architecture modulaire stricte (un fichier = une responsabilité)
- Tests d'intégration automatisés à chaque PR
- Documentation technique maintenue dans le repo (`NURU_V9.md`)
- Principe : un module = un fichier = une interface claire

---

## 15. Synthèse exécutive

**NURU V8+ est une fondation solide** — le pipeline RAG est bien conçu, l'architecture est modulaire, les garde-fous de sécurité sont en place. Le problème n'est pas la qualité du code existant mais l'absence de trois capacités structurelles : **mémoire réelle, outils, et boucle d'apprentissage.**

### Les quatre actions à valeur maximale

| Rang | Action | Impact | Coût RAM | Pourquoi |
|---|---|---|---|---|
| 1 | **Mémoire hiérarchique (6 types)** | 🔟/🔟 | +210 Mo | Transformation immédiate de l'expérience |
| 2 | **Reliability Scorer + Feedback** | 9/10 | +180 Mo | Fiabilité mesurable, condition préalable à la confiance |
| 3 | **Agent loop basique** | 9/10 | +300 Mo | Premier vrai pouvoir agentique |
| 4 | **Dashboard réel** | 8/10 | +100 Mo | Visibilité sur ce que fait NURU |

Ces quatre modules seuls représentent **80 % de la valeur perçue** pour **~30 % de la complexité totale**.

### La règle de fer

> **Ne jamais activer l'agentivité complète avant que le taux d'hallucination soit mesuré et documenté sous 1 %.**
> Un agent qui hallucine peut créer des fichiers erronés, exécuter du code incorrect, et modifier des documents importants.
> **La fiabilité précède l'autonomie.**

### Roadmap résumée

```
Semaine 1-4   ── V9 : Mémoire unifiée + Agent loop + Feedback + Dashboard
Semaine 5-10  ── V10 : Raisonnement + Outils docs + Web Research + Code sandbox
Semaine 11-14 ── V11 : Auto-amélioration + Mémoire procédurale
Semaine 15-20 ── V12 : Maturité, tests, optimisation, release
```

### Ce que NURU deviendra

**V9 (1 mois)** — NURU se souvient et agit
- ✅ Apprend de chaque interaction
- ✅ Se souvient de vous (préférences, contexte, habitudes)
- ✅ Exécute des tâches multi-étapes
- ✅ Évite les erreurs déjà commises
- ✅ Vous voyez ce qu'il fait en temps réel

**V10 (2 mois)** — NURU raisonne et crée
- ✅ Réfléchit avant de répondre (Reflexion)
- ✅ Crée des documents professionnels (Word, PDF, PPT, Excel)
- ✅ Recherche sur le web et compare les sources
- ✅ Dit « je ne sais pas » quand c'est approprié
- ✅ Cite systématiquement ses sources

**V11 (3 mois)** — NURU s'améliore seul
- ✅ Identifie ses points faibles
- ✅ Propose des améliorations de son code
- ✅ Apprend des workflows récurrents
- ✅ Reprend les tâches interrompues

**V12 (4 mois)** — NURU est mature
- ✅ IA personnelle complète
- ✅ Taux d'hallucination < 1 %
- ✅ Résolution tâches complexes > 85 %
- ✅ Fonctionne entièrement hors ligne si nécessaire
- ✅ Prêt pour un usage professionnel quotidien

---

*Document compilé le 11 juin 2026 à partir de trois analyses d'experts*
*Leblanc BAHIGA Mudarhi — NURU Project*


## Sprint Log

### V10.1 — 2026-06-12 "Nettoyage & Navigation"

**Suppressions :**
- `src/profile_boost.py` supprime — tous les fichiers ont la meme importance
- Code Profile Boost retire de `rag_engine.py` — plus de get_boost_score ni x2.5

**Corrections :**
- Navigation V10 reparee dans `dashboard.py:_on_page_changed` — les pages Stats V10 et Outils V10
  pointaient vers un `PlaceholderPage` car le handler `_v10_pages` manquait
- Cablage des dependances via `_wire_page_dependencies()` — connecte les pages aux sources du core

**Etat :**
- ✅ `rag_engine.py` importe sans erreur
- ✅ Dashboard instancie et navigation V10 fonctionnelle
- ✅ Pages sessions, documents, memory, diagnostics = vraies classes, pas des placeholders

### V10.1c — 2026-06-12 « Liens morts »

**Corrections :**
- MemoryExplorer: #8B949E fuyait dans le texte du label (TEXT_SECONDARY injecte via f-string)
- SessionsPage: showEvent recharge les sessions a la navigation
- DocumentsPage: showEvent recharge les documents a la navigation
- AgentStatusWidget: Inactif -> Pret - en attente de tache

**Commits :** 48c038c

### V10.2 — 2026-06-14 « Correctifs Audit P0+P1 (consensus 7 experts) »

**Corrections bloquantes (Phase 1 — < 1h) :**
- `import logging` ajouté dans `config.py` — tous les toggles Settings (TokenJuice, Learning, Nuru_Brain, Auto-Fetch, Hybrid mode) marchaient silencieusement
- URL OpenRouter corrigée (`api.openrouter.ai` → `openrouter.ai`) dans `llm_cloud.py`
- Fuite mémoire MLX : `self.unload()` dans le bloc `except` de `generate_stream()` (prévention fuite GPU)
- `pysqlite3` → `pysqlite3-binary` dans `pyproject.toml` + import protégé (try/except) dans `rag_engine.py`
- PromptGuard implémenté : `sanitize_rag_query()` + `sanitize_chunk_content()` dans `rag_engine.py`

**Corrections mineures (Phase 2 — 30 min) :**
- `confidence_label = "ABSENT"` forcé sur retour RAG vide (plus de HAUTE déclarée par défaut)
- `rag_score_threshold` abaissé de 0.40 à 0.30 dans `settings.yaml` (réduit faux négatifs RAG)

**Constatations (audits partiellement obsolètes) :**
- `audio_tts.py`, `sqlite_compat.py` déjà supprimés du codebase
- `process_query()` déjà un wrapper mince (334 lignes, pas 679)
- Modules V8 (MultiSearchOrchestrator, FactChecker, HyDE, decomposer) — tous actifs/instanciés en prod

**Commits :** 1fe237e

### V10.2c — 2026-06-14 « Phase 3 — Architecture & Mémoire »

**Fenêtre contextuelle 32K :**
- `ContextBudget(max_prompt_tokens=8192, reserved_response=2048)` — prompt jusqu'à 6144 tokens
- Changé dans `src/nuru_core.py` et `src/context_manager.py` (défauts)

**Hiérarchie d'exceptions :**
- `src/core/exceptions.py` créé : `OrchestratorError` → `RAGError | LLMError | MemoryError | RouterError | ConfigError | GuardError`
- 6 `except Exception` remplacés par `except (LLMError, RAGError)` etc. dans `orchestrator.py`

**Race conditions cache :**
- `asyncio.Lock()` ajouté sur `get_cache()` et `set_cache()` dans `memory_store.py`

**Constats :**
- `_memory_context = {}` défini mais jamais utilisé (code mort inoffensif)
- Orchestrator (831 lignes) est coordinateur bien structuré, pas God Object bloquant
- Découplage complet = ~4h, à planifier séparément

**Commits :** 331f467

### V10.2d — 2026-06-14 « Unification seuils RAG dupliqués »

**Changements :**
- `rag_min_usable_score=0.20` ajouté à `config.py` (ex `RAG_MIN_USABLE_SCORE` hardcodé dans `rag_engine.py`)
- `rag_router_min_score=0.15` ajouté à `config.py` (ex `RAG_SCORE_THRESHOLD` hardcodé dans `semantic_router.py`)
- Les 4 seuils RAG sont maintenant centralisés dans `Config` :
  1. `rag_score_threshold` (0.30) — Acceptation
  2. `rag_score_fallback` (0.25) — Moyenne confiance
  3. `rag_min_usable_score` (0.20) — Vidage contexte
  4. `rag_router_min_score` (0.15) — Routeur

**Commits :** 1cd9e03

### V10.2e — 2026-06-14 « Cache LLM multi-niveau (L1 RAM + L2 SQLite) »

**Architecture :** `src/cache/llm_cache.py`
- **L1 (RAM)** : `OrderedDict` + hash MD5 (O(1)) + TTL 300s + LRU 256 max
- **L2 (Disque)** : Wrapper vers `memory_store.semantic_cache` (SQLite vec0, cos ≥ 0.92)
- Promotion automatique L2→L1 sur hit
- Stats exposées : hit/miss/expired/size

**Intégration orchestrator :**
- `self.llm_cache = LLMCache(self.memory_store)` dans le constructeur
- `get_cache()` → `llm_cache.get()` (L1→L2→miss)
- `set_cache()` → `llm_cache.set()` (L1+L2 atomique)

**Tests :** 7/7 — miss, L2→L1 promotion, L1 hit, purge, TTL, stats, set/get

**Commits :** 80dcee8

### V10.2f — 2025-06-14 « Tests unitaires (25 tests, tous verts) »

**Nouveaux tests :**
- `test_llm_cache.py` — 11 tests (L1/L2/promotion/TTL/LRU/stats/concurrence)
- `test_rag_scoring.py` — 7 tests (labels HAUTE/MOYENNE/FAIBLE/ABSENT, seuils config, ContextBudget 32K)
- `test_orchestrator_pipeline.py` — 7 tests (cache hit/miss, erreur LLM, events, mémoire, offline)

**Commits :** cc75d01

### V10.2g — 2025-06-14 « Découplage Orchestrator (RAGOrchestrator + LLMGenerator) »

**Architecture :** `src/orchestration/`
- `RAGOrchestrator` (~380 l.) : pipeline RAG (retrieve, décomposition, Spotlight, FallbackGuard, vérif citations, FactChecker)
- `LLMGenerator` (~195 l.) : génération cloud/local, Archon, connectivity, température
- `NuruOrchestrator` allégé : -135 lignes net (835→700). Coordinateur conservant cache, prompt, finalisation, mémoire, réflexion

**Sections déléguées :**
1. `_check_connectivity()` → `self.llm_gen.check_connectivity()`
2. Section 2 (retrieve) → `self.rag_pipeline.retrieve_primary()`
3. Section 4 (décomposition RAG) → `self.rag_pipeline.retrieve_multi()`
4. Section 4.5 (Spotlight) → `self.rag_pipeline.integrate_spotlight()`
5. Section 4.6 (nettoyage FAIBLE) → `self.rag_pipeline.clear_low_confidence_context()`
6. Section 5 (Web fallback) → `self.rag_pipeline.maybe_web_fallback()`
7. Sections 5.5-5.6 (FallbackGuard + Strict RAG) → `self.rag_pipeline.check_strict_blocks()`
8. Section 7 (génération) → `self.llm_gen.generate()`
9. Section 7.5 (vérif citations) → `self.rag_pipeline.verify_citations()`
10. Section 7.6 (FactChecker) → `self.rag_pipeline.fact_check_and_retry()` + régénération orchestrateur

**Tests :** 25/25 passent (inchangés)

### V10.3a — 2026-06-14 « Dashboard V10 : métriques cache LLM + file watcher »

**Fichiers modifiés :**
- `src/ui/dashboard.py` — QFileSystemWatcher + badge notification rechargement
- `src/ui/components/stats_page.py` — Section Cache LLM multi-niveau (L1 RAM, L2 SQLite)

### V10.3b — 2026-06-14 « Spotlight Search V2 : plein texte, 5 termes, scoring »

**Fichier :** `src/rag/spotlight.py` (réécriture 278 lignes)
- Recherche plein texte (kMDItemTextContent)
- 5 termes vs 3 avant
- Scoring pondéré (nom 0.4 > chemin 0.2 > contenu 0.1)
- API rétrocompatible vérifiée sur `semantic_router.py`

### V10.3c — 2026-06-14 « Tests d'intégration Orchestrator découplé (13 tests) »

**Fichier :** `tests/test_integration.py` (13 tests, 327 lignes)
- RAGOrchestrator : retrieve_multi (RAG + COMPLEX), integrate_spotlight, check_strict_blocks, verify_citations
- LLMGenerator : generate streaming + offline, check_connectivity
- Pipeline : NuruOrchestrator.process_query (cache + régénération)
- **38 tests verts** (25 unitaires + 13 intégration)

### V10.3d — 2026-06-14 « Dashboard : 0 placeholders — FeedbackPage + ArchitecturePage »

**Nouveaux fichiers :**
- `src/ui/components/feedback_page.py` — Widget FeedbackCollector (statistiques + historique retours)
- `src/ui/components/architecture_page.py` — Aperçu composants NURU (modules, config, test count)

**Modifié :** `src/ui/dashboard.py` — plus de placeholders ; `nuru_brain` → ArchitecturePage, `feedback` → FeedbackPage

### V10.3e — 2026-06-14 « Guardrails : mode FREE opérationnel + audit »

**Modifié :**
- `src/core/response_guard.py` — épuré, docstrings
- `src/core/orchestrator.py` — mode FREE contourne RAG + web search, routing SIMPLE

**Audit :** PromptGuard OK (limité requêtes RAG), StrictRAGGuard (`is_free` intégré), FallbackGuard OK, EvidenceVerifier OK

### V10.3f — 2026-06-14 « Sessions conversationnelles persistantes »

**Nouveaux fichiers :**
- `src/session/store.py` — SessionStore (CRUD sessions + messages SQLite)
- `tests/test_session.py` — 12 tests unitaires

**Modifié :** `src/core/orchestrator.py`
- Enregistre user query + assistant response dans la session
- Injecte `build_context()` dans le prompt système (derniers N messages)
- Nouveau paramètre `session_id=` dans `_build_prompt`

**Tests :** 50 verts (25 unitaires + 13 intégration + 12 session)

### V10.3g — 2026-06-14 « SessionsPage reliée à SessionStore + auto-titrage »

**Modifié :**
- `src/ui/components/sessions_page.py` — `load_sessions()` utilise SessionStore en priorité (fallback memory_store), `session_selected` passe en `str`, nouvelle `_session_to_dict()` statique
- `src/core/orchestrator.py` — auto-titrage : premier message utilisateur devient titre de session

**Tests :** 50 verts (25 unitaires + 13 intégration + 12 session)

### V10.3h — 2026-06-14 « ArchonRefiner : auto‑correction post‑génération »

**Nouveau :**
- `src/ai/archon_refiner.py` — agent LLM dédié qui vérifie les réponses contre le contexte RAG et les corrige si besoin

**Modifié :**
- `src/core/orchestrator.py` — intégré après génération, avant enregistrement session. Marqueur 🔮 si corrigé

**Tests :** 10 tests unitaires. 60 verts total.

### V10.3i — 2026-06-14 « CLI interactif + delete/rename SessionStore »

**Nouveau :**
- `cli.py` — CLI interactif NURU : `ask`, `chat`, `list`, `show`, `delete`
  - `ask <question>` : one‑shot streaming
  - `chat` : mode multi‑tour avec sessions persistantes
  - `list` : sessions depuis SessionStore (formaté)
  - `show <id>` : historique complet d'une session
  - `delete <id>` : suppression d'une session
  - Commandes : `/help`, `/clear`, `/new`, `/exit`

**Modifié :**
- `src/ui/components/sessions_page.py` — `_on_row_delete()` et `_on_row_rename()` persistent via SessionStore (delete_session / update_title)

**Tests :** 60 verts (inchangés)

### V10.4 — 2026-06-15 « Correction des 9 bugs du dashboard »

**Bugfix sprint — aucune fonctionnalité nouvelle, uniquement des correctifs**

**Problèmes corrigés :**

1. **🔁 Doublage du prompt** — `console_page.py`, `dashboard.py`
   - Suppression du `show_typing()` en double dans le mode démo
   - `Qt.UniqueConnection` pour prévenir le double-wiring du signal

2. **🕐 Sessions vides** — `sessions_page.py`, `dashboard.py`
   - Fallback `memory_store.get_recent_history()` débloqué (return précoce supprimé)
   - Sauvegarde automatique des messages utilisateur/assistant dans SessionStore

3. **🧠 Mémoire inaccessible** — `memory_page.py` (rewrite 218→460 lignes)
   - États fallback : store None (panneau explicatif), DB vide (chemin+taille+guidance)
   - Auto-rafraîchissement toutes les 15s, gestion d'erreurs robuste

4. **💬 Feedback vide** — `feedback_page.py`
   - Création auto de `~/.nuru/` au constructeur
   - Messages d'état vide + erreur explicites

5. **🎛️ État V10 inactif** — `v6_system_page.py`
   - Mapping des noms de modules V10 vers les vrais attributs Config
   - `config=None` → affiche "N/A", cases désactivées

6. **📋 Logs figés (09/06)** — `logs_page.py`
   - Détection de vétusté : `⚠️ 09/06 13:16 (vieux de 6j)` en orange
   - Rechargement complet depuis le début

7. **📊 Stats non fonctionnelles** — `stats_page.py`
   - Bannière orange quand PerformanceTracker indisponible
   - `⏳ En attente...` au lieu de cartes vides, RAM toujours affichée

8. **🔧 Outils V10** — `tool_tester.py`
   - Badges 🟢/🔴 pour chaque backend
   - Erreurs différentiées : jaune (module manquant) vs rouge (runtime)

9. **📄 Documents récents** — `dashboard.py`
   - `DOC_MOCK` (4 entrées factices) remplacé par scan réel de 3 dossiers
   - 54 documents trouvés, 12 plus récents affichés

**Fichiers modifiés :** 9 fichiers, +1175/−236 lignes
**Tests :** 381 passés, 0 régression

### V10.4b — 2026-06-15 « Pipeline PerformanceTracker opérationnel (métriques NURU → dashboard) »

**Correctif :** les métriques du dashboard (Stats V10) restaient figées sur « En attente de données » même après utilisation de NURU, car `PerformanceTracker` n'était jamais appelé.

**Modifié :**
- `src/core/inference_worker.py` — instrumentation : enregistre `rag_recall@5`, `avg_score`, réponse tokens après chaque génération dans `~/.nuru/performance.db`
- `src/ui/dashboard.py` — nouveaux handlers `_on_feedback_positive`/`_on_feedback_negative` qui sauvent dans FeedbackCollector + PerformanceTracker

**Pipeline complet :**
```
Utilisateur → conversation → InferenceWorker → performance.db
Utilisateur → 👍/👎 → FeedbackCollector → performance.db
StatsPage (timer 5s) → lit performance.db → affiche métriques
```

**Fichiers modifiés :** 2, +84/−2
**Tests :** 381 passés, 0 régression

### V11.1 — 2026-06-15 « Dashboard P0 — Quick Wins + Architecture agentique »

**Sprint V11.1 : corriger les 4 P0 des audits experts + unifier le dashboard.**

| Jour | Commit | Livrable | Tests |
|------|--------|----------|-------|
| **J1** | `62376a6` | Quick Wins P0 : 4 audits experts → `NURU_AUDIT_SYNTHESE.md`, hooks dashboard P0-C+I+P0-J+P0-H | — |
| **J2** | `c7b1175` | ConversationList sidebar (8 tests), P0-C+I collapsibles, spec experts dashboard (519 lignes) | ✅ 8/8 ConversationList |
| **J3** | `d4e38db` | `ConsolePage.load_session()` + `set_session_store()`, bugfix permanent `MessagesArea` signaux regenerate/edit | ✅ 6/6 load_session + 8/8 ConversationList |
|| **J4** | `360619b+8bce46b+dd0d39f+70f9541` | **P0-N** Routeur footer bulle · **P0-E** Model switcher header · **P0-G** StatCard unifié (`stat_card.py`) + **memory_page** migré + **22 tests validations** (9 originaux + 13 supplémentaires) | ✅ 22/22 P0-N/E/G |
| **P0-F** | `6724018` | **Suppression code mort** — 1063 lignes (111 live + 952 archivées) | ✅ 30/30 verts |
| **Redesign** | `d256481` | **Thème "Midnight Indigo"** — refonte complète design system (palette indigo, arrondis 6-12px, QSS 378 lignes) | ✅ 30/30 verts |

| **P0-O** | `06ea71a` | **FactChecker status badge** — indicateur vert/orange/rouge dans bulle assistant (verified/issues/error) | ✅ 41/41 (11 nouveaux P0-O/P0-M) |
| **P0-M** | `06ea71a` | **Citations [N] cliquables inline** — [1][2] convertis en hyperliens, menu contextuel au clic | ✅ 41/41 |

**Tags :** `V11.1-J1`, `V11.1-J2`, `V11.1-J3`, `V11.1-J4`, `V11.1-P0F`, `V11.1-REDESIGN`, `V11.1-P0O-P0M`

**✅ V11.1 sprint complet — 63/63 tests verts.**

### V11.2 J3 — 2026-06-20 « Dashboard UX — 9 Sprints complétés »

**Sprint V11.2 (J1→J3) : amélioration UX du dashboard NURU basée sur 7 audits experts.**

| Sprint | Commit | Livrable | Lignes |
|--------|--------|----------|--------|
| **S1** | `7efb656` | Navigation simplifiée + Sidebar repliable + Raccourcis Ctrl+1..7 | +? |
| **S2** | `8a1ceb6` | Accessibilité + Toggle thème clair/sombre | +? |
| **Fix** | `99f2310` | Fix régressions Sprint 1 causées par Sprint 2 | — |
| **Fix** | `3c47f32` | Fix sidebar bloquée en mode mini — ne se dépliait plus | — |
| **S3** | `83471b2` | Focus Mode (Cmd+F plein écran) + Toasts + Routing + ThinkingBlock | +? |
| **S4** | `d5afddd` | Quick actions chips + Streaming cursor + @mentions + TimelineRouting | +748 |
| **S5** | `4d53017` | Cmd+K palette recherche + Fusion Memory V8+V9 + Fusion Stats+Diagnostics | +2 050 |
| **S6** | `60add02` | Markdown rendering riche (code blocks, tables) + SourcePreview citations | +? |
| **S7** | `bca24f4` | KPIs Dashboard Accueil (P1-J) | +? |
| **S8** | `946ac0d` | Fusion AgentStatus + TaskList (P1-F) | +? |
| **S9** | `e5d5688` | Thinking block animé (QPropertyAnimation) + Fact-checker badges enrichis (4 statuts) | +231 |

#### ✅ Terminé (V11.2)

- P1-H Quick action chips (Résumer, Traduire, Chercher, Aider)
- P1-I Streaming cursor + TypingIndicator enrichi (9 états)
- P1-L @mentions popup (auto-complétion, navigation clavier)
- P1-P TimelineRouting barre horizontale (panel droit)
- P1-A Cmd+K palette universelle
- P1-D Fusion Memory V8+V9 (PerformanceMemoryPage, 6 onglets)
- P1-E Fusion Stats+Diagnostics (PerformancePage)
- P1-K Markdown rendering riche (code blocks, tableaux, listes)
- P1-N SourcePreview hover (snippet 200 chars)
- P1-J KPIs Dashboard Accueil
- P1-F Fusion AgentStatus + TaskList (Agent Live)
- P1-M Thinking block animé (dépliable QPropertyAnimation 300ms)
- P1-O Fact-checker badges enrichis (✅⚠️❌⏳ + compteur sources)

#### ⏳ Reste à faire

| Priorité | ID | Description | Effort |
|----------|----|-------------|--------|
| 🔷 | **P1-C** | Design system tokens — palette 13 tokens, grille 4px, spacing, typographie | ~2j |
| ♿ | **ACC-1..8** | Accessibilité transverse — police mini 12px, contraste 4.5:1, focus indicators, setAccessibleName, boutons 32px | ~1j |
| 🔶 | **P2** | Polish — skeleton loaders, empty states, animations restantes, historique prompts ↑/↓, numérotation messages | ~2j |
| 📝 | **Docs** | Mettre à jour ROADMAP.md (date, scope, état V11.2) | ~30min |

**Tags :** `V11.2-J3`, `V11.2-S1-2`, `V11.2-S3`, `V11.2-S4`, `V11.2-S5`, `V11.2-S6`, `V11.2-S7`, `V11.2-S8`, `V11.2-S9`
**HEAD :** `e5d5688`
**Prochaine version :** V11.3 (Polish + Accessibilité + Design tokens)

---

## V12 — Plan de Transformation JARVIS
*Vers un assistant personnel proactif, multimodal, et contextuel — pas un chatbot avec outils*

**Date** : 2026-06-20 | **Basé sur** : Synthèse de 6 audits experts | **Auteur** : Leblanc BAHIGA Mudarhi

> ⚠️ **Vision** : NURU devient un système intelligent, proactif, multimodal, contextuel — capable d'assister son utilisateur dans sa vie numérique quotidienne, d'apprendre de ses habitudes, d'agir de manière autonome sous supervision, et de devenir progressivement une extension cognitive de son utilisateur.
>
> Un JARVIS, pas un chatbot augmenté.

### Table des matières V12

1. [V12 Vision — Le vrai gap](#v12-vision)
2. [Interface V12 — Z.ai Design System](#interface-v12-zai--design-system--presence-numerique)
3. [Phase 0 — Consolidation (2 semaines)](#phase-0--consolidation)
4. [Phase 1 — Action (6 semaines)](#phase-1--action)
5. [Phase 2 — Multimodal (8 semaines)](#phase-2--multimodal)
6. [Phase 3 — Proactivité (4 semaines)](#phase-3--proactivite)
7. [Phase 4 — Écosystème (4 semaines)](#phase-4--ecosysteme)
8. [TokenJuice — Stratégie de compression](#tokenjuice--strategie-de-compression)
9. [Budget RAM — Contrainte M1 8 Go](#budget-ram)
10. [Synthèse — Les 3 actions immédiates](#synthese--les-3-actions-immediates)

---

### V12 Vision — Le vrai gap

La majorité des projets « JARVIS » open-source échouent parce qu'ils **ajoutent des outils à un chatbot**, espérant que la somme des outils fera un assistant. Ça ne marche pas. La différence entre un copilote et un assistant n'est pas quantitative — elle est **architecturale**.

**Un assistant personnel (JARVIS) a 3 piliers :**

| Pilier | Chatbot + outils | Assistant (JARVIS) | Statut NURU |
|--------|------------------|-------------------|-------------|
| **Action** | Répond à des questions, produit du texte | **Agit** sur l'environnement : shell, navigateur, OS, fichiers | ❌ Aucune |
| **Multimodalité** | Texte uniquement | Voix (entrée + sortie), Vision (écran + images), Texte | ❌ Texte seul |
| **Proactivité** | Attend qu'on lui parle | **Initie** : rappels, suggestions, surveillance, routines | ❌ Réactif pur |

**NURU est bloqué au niveau « Copilote Intelligent Avancé »** (Z.ai scorecard : ⭐⭐⭐⭐☆ RAG 5/5, 💀 Contrôle 1/5, 💀 Voix 1/5, 💀 Proactivité 0/5). La transition vers JARVIS nécessite de construire ces 3 piliers **en parallèle** sur la fondation existante.

**Nos avantages cachés (0/6 audits les ont identifiés) :**

| Actif | Valeur | Pourquoi personne ne l'a vu |
|-------|--------|---------------------------|
| **TokenJuice** (-40% tokens) | Compense la RAM limitée, permet plus de contexte | Les audits regardent l'architecture, pas le pipeline de tokens |
| **EventBus** (pub/sub existant) | Backbone tout fait pour la proactivité et la supervision parallèle | Les audits comparent aux standards (MCP), pas ce qui existe déjà |

**Stratégie V12** : Exploiter ces 2 actifs uniques que **personne** dans les 6 rapports n'a vus, pour construire une architecture qui respecte la contrainte M1 8 Go.

---

### Interface V12 — Z.ai : Design System & Présence Numérique
*Refonte de l'interface : du cockpit 3 colonnes à la présence numérique animée*

**Design system fourni par Z.ai** | **PySide6 / Qt / QPainter** | **Cible : macOS M1 8 Go**

> La V12 opère un changement radical de paradigme : NURU n'est plus un outil que l'on consulte, mais une présence que l'on ressent. L'interface passe d'un modèle d'affichage de données à un modèle de présence ambiante. (Z.ai, Spec Design V12)

#### Paradigme : 3 colonnes → Présence « Ambient »

| Avant (V10.3/V11) | Après (V12 — Z.ai) |
|--------------------|--------------------|
| Dashboard 3 colonnes technique (cockpit) | Écran minimal centré sur l'interaction |
| Sidebar navigation + panneau métriques | **Menu contextuel** + mode debug Ctrl+D |
| Métriques CPU/RAM/tokens visibles en permanence | **Tooltip inline**, panneau coulissant optionnel |
| Barre d'outils horizontale | **Actions contextuelles** inline dans la conversation |
| Onglets sessions multiples visibles | **Switcher Cmd+T**, un seul chat visible |

#### Design System DM-1 Deep Cyan

**Palette :**

| Token | HEX | Rôle |
|-------|-----|------|
| `bg-deep` | `#070A10` | Fond principal |
| `bg-card` | `#0D1117` | Cartes et surfaces |
| `bg-surface` | `#151B26` | Surfaces surélevées |
| `accent-cyan` | `#00D4FF` | Indicateurs d'état, focus, liens |
| `accent-cyan-glow` | `rgba(0,212,255,0.15)` | Halo / glow d'animation |
| `accent-warm` | `#E8A87C` | Notifications proactives, alertes douces |
| `text-primary` | `#E8ECF1` | Texte principal |
| `text-secondary` | `#8B95A5` | Légendes, métadonnées |
| `accent-green` | `#00E599` | Confirmations, succès |
| `accent-amber` | `#FFB800` | Attention, suggestions |
| `accent-rose` | `#FF4D6A` | Erreurs, danger |

**Typographie :**
- **SF Pro / Inter** (300–700) : textes, conversations, titres
- **JetBrains Mono** (400–500) : code, données techniques, métriques
- Taille body : 13 pt, caption : 11 pt, titres : 18 pt, overlay prompt : 28 pt

#### Architecture des composants

**Nouveaux composants V12 :**

| Composant | Taille | Rôle | État |
|-----------|--------|------|------|
| **NuruPresenceOrb** | 120/200/80 px | Cercle animé central — indicateur d'état | 🆕 |
| **ConversationSurface** | fluide | Zone de chat avec bulles alignées (user droite, NURU gauche) | 🆕 |
| **VoiceOverlay** | 60%×40% écran | Fenêtre frameless semi-transparente pour le mode vocal | 🆕 |
| **NuruFloatingWidget** | 160×160 px | Widget always-on-top, drag-and-drop, auto-dim opacité | 🆕 |
| **NuruMenuBarIcon** | 22×22 px | QSystemTrayIcon, icône change selon état | 🆕 |
| **ContextStrip** | barre horizontale | Infos contextuelles (app active, fichier sélectionné) | 🆕 |
| **ProactiveToast** | notification glissante | 400px déplacement, 300ms ease-out, 4s visibilité | 🆕 |

**Supprimés :**
- ❌ Sidebar complète → remplacée par menu contextuel
- ❌ Panneau métriques permanent → Ctrl+D debug mode
- ❌ Barre d'outils horizontale → actions contextuelles inline
- ❌ Indicateurs CPU/RAM visibles → mode debug dédié

#### NuruPresenceOrb : Le cœur visuel — 7 états animés (Z.ai, v2)

```python
class NuruPresenceOrb(QWidget):
    """Présence animée de NURU. 7 états avec QPropertyAnimation.
    
    Tailles : 120px (fenêtre), 200px (VoiceOverlay), 80px (FloatingWidget)
    Rendu : QPainter custom (pas de 3D, pas de GPU)
    M1 8 Go : CPU < 5% par animation, single-level shadows only
    """
    
    # État mise à jour : action.state remplace le simple pulse_warm
    STATES = {
        "idle":      {"anim": "pulse 4s",        "desc": "Respiration lente, opacité 0.8↔1.0"},
        "listening": {"anim": "sound_waves",     "desc": "3 cercles concentriques qui s'expandent", "signal": "voice.wake_detected"},
        "thinking":  {"anim": "halo_spin 3s",    "desc": "Arc 270° rotatif, dégradé radial cyan", "signal": "voice.thinking_start"},
        "speaking":  {"anim": "particles_tight", "desc": "Particules calibrées au volume TTS", "signal": "voice.response_start"},
        "acting":    {"anim": "arc_progress",    "desc": "Orb scale 0.85 + anneau arc QPainter clockwise. Progress signal 0→1.0", "signal": "action.started → action.completed"},
        "respond":   {"anim": "pulse_accel 1.5s","desc": "Pulsing accéléré (idle rendu plus rapide)", "signal": "voice.response_start"},
        "error":     {"anim": "blink_red 2s",    "desc": "Clignotant #FF4D6A, alterné avec opacité réduite"},
    }
```

**Décisions Z.ai (v2) :**
- `acting` 🆕 = état dédié pour les actions longues (NURU exécute une commande). L'Orb se contracte à 85% avec un anneau de progression (`QPainter::drawArc`). Le `ProactiveToast` accompagne mais ne remplace pas.
- `respond` 🆕 = séparé de `speaking` pour distinguer la parole TTS de l'attente de la réponse (thinking→respond→speaking)
- L'actuel `action` / `pulse_warm` disparaît (fusionné dans `acting`)
- Cycle voix corrigé : `listening → thinking → respond → speaking → idle`

#### Cycle EventBus — Voix + Action

**Voix :**
```
voice.wake_detected           → overlay apparition (scale 0.8→1.0, opacity 0→1, 250ms), Orb → listening
voice.transcript_update       → transcription temps réel
voice.thinking_start          → Orb → thinking (halo rotatif 3s/tr, cyan blanchi)
voice.response_start          → Orb → respond (pulse accéléré 1.5s)
voice.speaking                → Orb → speaking (particules TTS)
voice.session_end / timeout 8s → overlay disparition (scale 1.0→0.8, opacity 1→0), Orb → idle
```

**Action (nouveau) :**
```
action.started                → Orb → acting (scale 0.85, anneau progression 0°/360°)
action.progress(pct: 0→1.0)  → arc_angle = int(360 * pct) (QPainter::drawArc)
action.completed              → Orb → idle, toast optionnel 3s
```

#### Intégration macOS

| Élément | Implémentation | Comportement |
|---------|---------------|--------------|
| **Menu Bar** | `QSystemTrayIcon` 22×22px | Icône gris (idle), cyan pulsant (écoute), orange (alerte proactive) |
| **Floating Widget** | `Qt.Tool \| FramelessWindowHint \| WindowStaysOnTopHint` | 160×160px, drag-and-drop, opacité → 0.4 après 30s inactivité, revient à 1.0 au hover |
| **Raccourcis** | `QShortcut` | ⌥␣ vocal, ⌘⇧N floating widget, ⌘N new chat, ⌘T switcher, ⎋ fermer overlay |

#### Spécifications techniques PySide6

```python
class NuruWindow(QMainWindow):
    """Conteneur principal V12. Routeur d'événements."""
    def __init__(self, event_bus: EventBus):
        self.current_mode = "chat"  # chat | voice | action
        self.presence_orb = NuruPresenceOrb(self)        # 120px
        self.conversation = ConversationSurface(self)
        self.input_bar = NuruInputBar(self)
        self.voice_overlay = VoiceOverlay()              # frameless
        self.floating_widget = NuruFloatingWidget()       # 160×160px
        self.context_strip = ContextStrip(self)
        self._bind_events()                               # EventBus → UI

class VoiceOverlay(QWidget):
    """Fenêtre frameless pour le mode vocal.
    
    Flags : Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    Fond : rgba(13,17,23,0.92)
    Rayon : 16px (sans QGraphicsBlurEffect = pas de coût GPU)
    """
    def show_overlay(self):
        # Animation : scale 0.8→1.0, opacity 0→1, 250ms, OutCubic
        ...
    def hide_overlay(self):
        # Animation : scale 1.0→0.8, opacity 1→0, 250ms, InCubic
        # Timeout : 8s sans détection vocale
        ...
```

#### Roadmap implémentation interface (Z.ai, 9 semaines — parallélisable)

| Phase | Semaines | Livrables | Critères validation |
|-------|----------|-----------|-------------------|
| **P1 — Socle visuel** | 1-3 | NuruWindow sombre + coins arrondis, Orb idle/thinking (QPainter), ConversationSurface bulles, Design tokens (palette, typo, espacement) | Chat fonctionnel avec identité V12 |
| **P1.5 — Widget flottant** 🔀 | 2-3 | FloatingWidget layout + Tray menu (dépend uniquement de NuruWindow, pas de l'Orb) | Widget apparaît dans menu bar |
| **P2 — Expérience vocale** | 4-6 | VoiceOverlay frameless complet, Orb listening/speaking (ondes, halo), Menu bar QSystemTrayIcon, Raccourcis clavier | Activation vocale + overlay fonctionnel |
| **P3 — Présence & polish** | 7-9 | Orb acting (anneau progression), ProactiveToasts glissants, ContextStrip (NSWorkspace), Mode debug Ctrl+D, Light mode, Micro-interactions | Tous modes actifs, micro-interactions fluides |

> **Parallélisme** : P1.5 (FloatingWidget) peut démarrer dès la semaine 2, en parallèle de P1. Il ne dépend que de `NuruWindow` et `QSystemTrayIcon` — pas de l'Orb. Si le widget est fonctionnel avant l'Orb, un cercle gris statique sert de placeholder.

#### Redimensionnement — Fluide, pas de paliers

L'Orb = **`min(largeur, hauteur) * 0.25`**. Pas de breakpoints, pas de paliers — un simple ratio.

| Taille écran | Diamètre Orb | Adaptation |
|-------------|-------------|------------|
| 1920×1080 | 270 px | Pleine expérience |
| 1440×900 | 225 px | Shadow retiré sous 1440px (économie GPU M1) |
| 1280×800 | 200 px | Transcription 18→16px, WaveformRings réduit |
| 1024×600 | 150 px | FloatingWidget 140×120px |

```python
def resizeEvent(self, event):
    size = min(self.width(), self.height())
    self.orb_radius = size * 0.125          # diamètre = 25%
    self.orb_center = QPointF(self.width()/2, self.height()/2)
    self.update()                            # → paintEvent
```

#### Thème clair — Mode basculable (pas un thème égal)

NURU V12 reste **nocturne par défaut** — c'est son identité et l'Orb perd 80% de son impact sur fond clair. Mais un mode clair est disponible comme **profil basculable**.

**Approche : transformation algébrique, pas de palette parallèle**

| Élément | Dark (défaut) | Light (optionnel) |
|---------|--------------|-------------------|
| Background | `#0A0E17` | `#F4F6F9` |
| Surface 1 | `#151B26` | `#FFFFFF` |
| Accent | `#00D4FF` | `#0099BB` cyan assombri ~15% |
| Text | `#E8ECF1` | `#1A2332` |
| Orb glow | Radial cyan 40% opacity | Radial cyan 12% opacity |

**Pas de duplication** — un `QPalette` swap + `opacity_multiplier` sur l'Orb suffit :
- Activation : `Cmd+Shift+L` ou détection macOS (`NSAppearanceObserver`)
- Le glow de l'Orb passe de 40% à 12% d'opacité
- Même composant, deux jeux de tokens

> **Décision Z.ai** : ne pas créer un « thème clair » séparé. Une transformation algébrique sur les tokens existants (inversion de lightness + réduction opacité glow). En PySide6 : `QPalette` swap + une `opacity_multiplier` property sur l'Orb.

> **Contrainte M1 8 Go** : Toutes les animations sont implémentées via `QPropertyAnimation` et `QPainter` — pas de 3D, pas de `QGraphicsBlurEffect`, pas de canvas lourd. Budget : < 5% CPU par animation. Vérifiable via Instruments macOS.

---

### Phase 0 — Consolidation : Tuer le legacy V4 (2 semaines)

**Objectif** : Avant d'ajouter QUOI QUE CE SOIT, consolider la dette technique. **Z.ai, Kimi, Mavis, Alex — tous les 4 audits valides sont unanimes : la dualité V4/V8+ est le blocage #1.**

| Semaine | Sprint | Actions | Lignes affectées |
|---------|--------|---------|-----------------|
| S1 | **Nettoyage V4** | Supprimer tous les imports conditionnels V4. Normaliser les docstrings. Uniformiser les naming conventions. Supprimer `PluginSystem` (stub vide), `ReflectionEngine` (stub vide). Remplacer les 3 routeurs (`semantic_router.py`, `core/router.py`, `nuru_core.py`) par un routeur unique. | ~500 lignes |
| S1 | **Prompt unique** | Fusionner les 4 builds de prompt système en un seul `DynamicPromptBuilder` qui lit la UserMemory et construit le prompt à la volée. Fin du hardcoding. | ~200 lignes |
| S2 | **Tests critiques** | Ajouter des tests unitaires sur : routeur (20 tests), RAG pipeline (15 tests), mémoire (15 tests), sécurité PromptGuard (10 tests). Cible : 60 tests nouveaux, 100% verts. | — |
| S2 | **pyproject.toml** | Mettre `version = "12.0.0"`, aligner avec la réalité. Supprimer les badges faux du README. | 3 fichiers |

**Critères de succès Phase 0** :
- ✅ Plus aucun import conditionnel V4 dans le code
- ✅ Un seul routeur, un seul build de prompt
- ✅ 60 nouveaux tests verts
- ✅ pyproject.toml aligné sur la réalité
- ✅ RAM libérée : ~200 Mo (suppression stubs + routeurs dupliqués)

---

### Phase 1 — Action : Contrôle de l'environnement (6 semaines)

**Objectif** : NURU passe de « répond à des questions » à « agit sur le monde ». C'est le **différenciateur #1** identifié par Z.ai. Sans action, NURU reste un chatbot.

#### Architecture — Security-first

```python
# Principe : 5 couches de défense (inspiré de Jarvis-OS)
EXECUTION_MODEL = {
    0: "manual_only",     # NURU propose, humain exécute
    1: "safe_confirm",    # Actions non-destructives, auto-confirmées
    2: "confirm_all",     # Toute action nécessite approbation
    3: "trusted_patterns",# Patterns appris = auto, nouveaux = confirm
    4: "semi_autonomous", # Supervision passive, intervention si anomalie
    5: "full_autonomous", # Supervision a posteriori (journal)
}
```

| Semaine | Sprint | Module | Description | RAM ajoutée | Dépend de |
|---------|--------|--------|-------------|-------------|-----------|
| S3 | **Shell sécurisé** | `src/tools/shell_exec.py` | Exécution de commandes terminal avec sandbox, blocklist, allowlist, et approbation humaine. 5 couches de défense. Limité à `~/Nuru_Workspace/` par défaut. | ~50 Mo | Phase 0 |
| S4 | **Contrôle OS** | `src/tools/os_control.py` | PyAutoGUI + AppleScript : ouvrir/fermer apps, lancer scripts, gérer fenêtres, volume, luminosité. Découverte automatique des apps installées. | ~80 Mo | Shell sécurisé |
| S5 | **Contrôle navigateur** | `src/tools/browser_ctrl.py` | Playwright : navigation web, formulaires, scraping. Pas de contrôle financier sans approbation explicite. | ~150 Mo | Contrôle OS |
| S6 | **Gestion fichiers CRUD** | `src/tools/file_ops.py` | Créer, modifier, déplacer, supprimer fichiers. Restreint à `~/Nuru_Workspace/` + dossiers explicitement autorisés. | ~30 Mo | Shell sécurisé |
| S7 | **Intégration ToolRegistry** | Connecter les 4 outils au ToolRegistry existant + Exposition des outils via MCP. | ~20 Mo | Tous |
| S8 | **Tests + Sécurité** | Tests d'intégration des 4 outils (min 40 tests). Audit de sécurité. Hardening du sandbox. | 0 | Tous |

**Critères de succès Phase 1** :
- ✅ « NURU, ouvre VS Code » → VS Code s'ouvre
- ✅ « NURU, cherche le prix du iPhone 16 sur Amazon » → Playwright navigue et rapporte
- ✅ « NURU, crée un dossier 'projet_investissement' dans Workspace » → dossier créé
- ✅ « NURU, exécute pip install pandas » → shell sandboxé
- ✅ Toute action destructive nécessite approbation humaine
- ✅ RAM totale < 5.5 Go

---

### Phase 2 — Multimodal : Voix + Vision (8 semaines)

**Objectif** : NURU acquiert la parole, l'écoute et la vue. Le **différenciateur #2** identifié par tous les audits : un assistant qui ne parle pas n'est pas JARVIS.

#### Architecture Voix — Local-first

```python
# Pipeline vocal local (M1 8 Go optimisé)
# STT : mlx-whisper tiny (100ms, ~500 Mo RAM)
# LLM : Phi-4-mini local (réponses courtes)
# TTS : Kokoro (local, <200ms latence)
# VAD : Silero VAD (détection activité vocale)
# Wake word : OpenWakeWord (1-2% CPU)
```

| Semaine | Sprint | Module | Description | RAM ajoutée | Dépend de |
|---------|--------|--------|-------------|-------------|-----------|
| S9 | **Pipeline STT** | `src/voice/stt.py` | mlx-whisper tiny, streaming local, buffering intelligent. Détection fin de phrase pour découpage. | ~500 Mo | Phase 0 |
| S10 | **Pipeline TTS** | `src/voice/tts.py` | Kokoro TTS local, streaming sentence-by-sentence. Fallback macOS `say` si RAM insuffisante. | ~300 Mo | Phase 0 |
| S11 | **Wake word** | `src/voice/wake_word.py` | « Hey NURU » via OpenWakeWord. Bascule automatique en mode écoute. Faible CPU (<5%). | ~50 Mo | STT + TTS |
|| S12 | **VAD + Barge-in** | `src/voice/vad.py` | Silero VAD pour interruption naturelle. Priorité à la voix utilisateur sur la réponse en cours. | ~50 Mo | Pipeline voix |
|| S12b | **VoiceOverlay UI** 🆕 | `src/ui/voice_overlay.py` | NuruPresenceOrb modes listening/speaking (ondes QPainter), fenêtre frameless 60%×40%, menu bar QSystemTrayIcon, raccourcis ⌥␣. Spécifications Z.ai. | ~100 Mo | S10 + S11 ||
| S13 | **Vision écran** | `src/vision/screen.py` | Capture d'écran périodique (mss, 2-5s). Analyse par LLM cloud (GPT-4o Vision). Pas de vision locale (trop RAM). Détection des changements d'interface. | ~100 Mo | Phase 1 |
| S14 | **Vision documents** | `src/vision/doc_vision.py` | OCR amélioré (pytesseract). Analyse d'images et screenshots via LLM cloud. Détection de tableaux dans les images. | ~80 Mo | Vision écran |

**Contrainte RAM critique Phase 2** :
- Le pipeline vocal complet ne peut PAS tourner en permanence
- **Stratégie** : Modules déchargeables. Wav2Vec + Kokoro chargés uniquement en mode conversation vocale. En idle : juste le wake word (50 Mo).
- Mode dégradé : si RAM > 6.5 Go → désactiver la vision, basculer TTS sur `say` (0 Mo supplémentaire)

**Critères de succès Phase 2** :
- ✅ « Hey NURU, quelle heure est-il ? » → réponse vocale + VoiceOverlay visible en < 3s
- ✅ VoiceOverlay s'affiche avec animation (scale 0.8→1.0, 250ms) et disparaît après 8s silence
- ✅ NuruPresenceOrb change d'état visuellement : écoute (ondes), réflexion (halo), parole (particules)
- ✅ NURU parle avec une voix naturelle (Kokoro)
- ✅ L'utilisateur peut interrompre NURU en parlant (barge-in)
- ✅ NURU analyse une capture d'écran et décrit ce qu'il voit
- ✅ NURU extrait le texte d'une photo de document
- ✅ RAM conversation vocale < 2.0 Go additionnels
- ✅ Idle (wake word seul) : +50 Mo seulement

---

### Phase 3 — Proactivité : EventBus Engine + Mémoire dynamique (4 semaines)

**Objectif** : NURU passe de réactif à **proactif**. C'est le **différenciateur #3** — l'élément qui transforme un chatbot en compagnon numérique.

#### Architecture — EventBus comme backbone proactif

L'EventBus existant est **le secret de NURU que tous les audits ont raté**. C'est le système nerveux parfait pour la proactivité :

```python
class ProactiveEngine:
    """
    Tourne en background. Collecte des signaux, évalue la pertinence,
    et déclenche des initiatives sans requête utilisateur explicite.
    
    Fréquence : toutes les 15-30 minutes en idle.
    RAM idle : ~30 Mo (signal collectors uniquement).
    RAM active : ~200 Mo (LLM pour génération d'initiative).
    """
    
    SIGNALS = {
        "time": TimeSignal(),           # Heure, jour, mois, saison
        "calendar": CalendarSignal(),   # Événements à venir
        "filesystem": FSSignal(),       # Fichiers modifiés, nouveaux
        "session": SessionSignal(),     # Dernière conversation
        "memory": MemorySignal(),       # Échéances, rappels en mémoire
        "system": SystemSignal(),       # CPU, RAM, batterie, réseau
    }
    
    # Mode d'exécution des initiatives
    MODE = {
        "auto": ["time_signals", "system_alerts"],  # Pas besoin d'approbation
        "notify": ["calendar_reminders", "file_changes"],  # Notification + approbation
        "validate": ["action_suggestions", "workflow_proposals"],  # Demande explicite
    }
```

| Semaine | Sprint | Module | Description | RAM ajoutée | Dépend de |
|---------|--------|--------|-------------|-------------|-----------|
| S15 | **ProactiveEngine** | `src/proactive/engine.py` | Moteur de signaux + évaluation LLM. Scheduler 15-30 min. Détection contextuelle (heure, apps ouvertes, calendrier). | ~200 Mo (actif), ~30 Mo (idle) | Phase 0 |
| S15 | **Signal Collectors** | `src/proactive/signals/` | TimeSignal, CalendarSignal, FSSignal, MemorySignal, SystemSignal. Chacun = un fichier, remplaçable. | ~20 Mo | S15 |
| S16 | **Prompt dynamique** | `src/memory/dynamic_prompt.py` | Le prompt système n'est plus hardcodé. Il est construit dynamiquement depuis UserMemory + contexte courant. **Fin du hardcoding identifié par Z.ai.** | ~20 Mo | Phase 0 |
| S16 | **Consolidation mémoire** | `src/memory/consolidation.py` | Curator (inspiré de Jarvis-OS) : decay temporel, fusion d'épisodes, détection contradictions. Tourne en période d'inactivité. | ~100 Mo (pic) | Phase 0 |
| S17 | **Routines & presets** | `src/proactive/routines.py` | « Mode travail », « Mode soirée » : presets configurables. Déclenchables par commande vocale, heure, ou contexte. | ~50 Mo | Phase 1 + 2 |
| S18 | **Apprentissage contextuel** | `src/proactive/learning.py` | Détection des patterns d'utilisation. « NURU remarque que tu ouvres toujours VS Code + terminal à 9h → proposition de preset 'Morning Dev'. » | ~80 Mo | S16 + S17 |

**Règle de fer de la proactivité** : NURU ne fait JAMAIS d'action destructive sans validation humaine. Les initiatives sont classées par mode (AUTO/NOTIFY/VALIDATE) et l'utilisateur voit TOUT.

**Critères de succès Phase 3** :
- ✅ NURU dit « Bonjour, ta réunion commence dans 10 min » sans qu'on lui demande
- ✅ NURU suggère « Je vois que tu travailles sur le projet X, veux-tu que j'ouvre les fichiers de la session précédente ? »
- ✅ Le prompt système change dynamiquement selon le contexte
- ✅ La mémoire se consolide automatiquement (décay + fusion)
- ✅ « Mode travail » est un preset fonctionnel
- ✅ RAM proactive idle < 50 Mo (hors pic consolidation)

---

### Phase 4 — Écosystème : MCP + Intégrations (4 semaines)

**Objectif** : NURU n'est plus une île. Il se branche à l'écosystème MCP. **Identifié par tous les audits comme un risque existentiel (Kimi : « obsolescence en 12 mois »).**

| Semaine | Sprint | Module | Description | RAM ajoutée | Dépend de |
|---------|--------|--------|-------------|-------------|-----------|
| S19 | **MCP Client** | `src/mcp/client.py` | Connexion aux serveurs MCP existants. Découverte d'outils. Cache de schémas. | ~50 Mo | Phase 0 |
| S19 | **MCP Server** | `src/mcp/server.py` | NURU expose ses propres outils (RAG, mémoire, outils Phase 1) comme serveur MCP. Interopérabilité avec Claude Desktop, Cursor, etc. | ~30 Mo | Phase 1 |
| S20 | **Intégrations clés** | `src/mcp/integrations/` | Connecteurs MCP vers : Notion, Google Calendar, Gmail, Slack, GitHub, Spotify. Priorité : les 4 premiers. | ~100 Mo | Phase 1 + 3 |
| S20 | **Security hardening final** | `src/security/` | Audit de sécurité complet. Sandbox des outils. Chiffrement de la base mémoire. Journal d'audit immuable. Validation des entrées. **5 catégories de vulnérabilités corrigées (Kimi audit).** | ~50 Mo | Toutes |

**Critères de succès Phase 4** :
- ✅ NURU lit/modiie un document Google Docs via MCP
- ✅ NURU consulte le calendrier Google et suggère des créneaux
- ✅ NURU expose son RAG comme serveur MCP → utilisable depuis Claude Desktop
- ✅ Aucune vulnérabilité critique restante (fuite d'identité, path traversal, connection leaks)
- ✅ RAM totale < 7.0 Go

---

### TokenJuice — Stratégie de compression JARVIS

TokenJuice (-40% tokens) est **l'avantage compétitif le plus sous-estimé de NURU** (0/6 audits l'ont identifié). Sur M1 8 Go, chaque token économisé est un token qui peut être utilisé pour le contexte proactif, la mémoire, ou la voix.

**Extension V12 de TokenJuice :**

```python
class TokenJuiceV12:
    """
    Compression adaptative selon le contexte.
    """
    
    # Objectifs V12
    TARGETS = {
        "chat_normal": 0.40,         # -40% (actuel)
        "voice_response": 0.50,      # -50% (voix = phrases courtes)
        "proactive_suggestion": 0.45,# -45% (suggestions concises)
        "memory_consolidation": 0.30,# -30% (préserver le sens critique)
        "mcp_integration": 0.35,     # -35% (interopérabilité)
        "emergency_ram": 0.60,       # -60% (si RAM < 1 Go libre)
    }
    
    # Économies estimées V12
    # Actuel : ~40% → 100 tokens → 60 tokens
    # Cible : ~50% moyen → 100 tokens → 50 tokens
    # Gain : +25% de contexte disponible pour proactivité
```

**Impact TokenJuice sur le plan V12 :**

| Ressource | Sans TokenJuice | Avec TokenJuice (50%) | Gain |
|-----------|-----------------|----------------------|------|
| Contexte par requête | 6,144 tokens | ~9,000 tokens | +46% |
| Mémoire consolidée par jour | ~500 épisodes | ~750 épisodes | +50% |
| Prompts proactifs | 10/jour max | 15/jour max | +50% |
| Coût cloud mensuel | ~$8 | ~$4 | -50% |

---

### Budget RAM — Contrainte M1 8 Go

La contrainte M1 8 Go est **la raison pour laquelle la majorité des projets JARVIS solo échouent** sur Apple Silicon. Chaque Mo compte.

| Composant | Actuel (V11.2) | V12 Cible | Delta |
|-----------|---------------|-----------|-------|
| Système (macOS + apps) | ~2.5 Go | ~2.5 Go | 0 |
| LLM local (Phi-4-mini) | ~3.0 Go | ~3.0 Go | 0 |
| RAG + Embeddings | ~1.0 Go | ~0.8 Go | -200 Mo (optimisation) |
| Dashboard PySide6 | ~0.5 Go | ~0.5 Go | 0 |
| **Sous-total système** | **~7.0 Go** | **~6.8 Go** | **-200 Mo** |
| | | | |
| **Disponible pour V12** | **~1.0 Go** | **~1.2 Go** | **+200 Mo** |
| | | | |
| Phase 1 — Outils | — | ~300 Mo | +300 Mo |
| Phase 2 — Voix (actif) | — | ~900 Mo | +900 Mo |
| Phase 2 — Voix (idle) | — | ~50 Mo | +50 Mo |
| Phase 2 — Vision | — | ~180 Mo | +180 Mo |
| Phase 3 — Proactif (actif) | — | ~200 Mo | +200 Mo |
| Phase 3 — Proactif (idle) | — | ~50 Mo | +50 Mo |
| Phase 4 — MCP | — | ~180 Mo | +180 Mo |

**🔥 Réalité : le pipeline vocal complet (STT + TTS + LLM + VAD) ne peut pas coexister avec le RAG + Dashboard + Outils.**

**Stratégie de survie RAM :**

```python
class RAMOrchestrator:
    """
    Gestionnaire de mémoire dynamique. 
    Les modules se chargent/déchargent selon le mode actif.
    """
    
    MODES = {
        "idle": {
            "active": ["wake_word", "proactive_idle"], 
            "inactive": ["stt", "tts", "vision", "outils_lourds"],
            "ram_used": 50  # Mo
        },
        "chat": {
            "active": ["rag", "llm_local", "dashboard"],
            "inactive": ["stt", "tts", "vision"],
            "ram_used": 300  # Mo
        },
        "voice_conversation": {
            "active": ["stt", "tts", "llm_local", "vad"],
            "inactive": ["rag", "vision", "outils_lourds"],
            "ram_used": 900  # Mo
        },
        "vision_analysis": {
            "active": ["vision", "llm_cloud"],
            "inactive": ["stt", "tts", "rag"],
            "ram_used": 300  # Mo
        },
        "task_execution": {
            "active": ["outils", "llm_local", "rag"],
            "inactive": ["stt", "tts", "vision"],
            "ram_used": 500  # Mo
        },
    }
    
    async def switch_mode(self, new_mode: str):
        # 1. Unload modules inactifs
        # 2. Load modules actifs
        # 3. Vérifier budget RAM
        # 4. Si > 7.5 Go → forcer mode dégradé
        pass
```

**Résultat** : NURU ne fait JAMAIS tout à la fois. Il est **contextuellement conscient de sa RAM** et s'adapte. L'utilisateur ne voit pas la complexité — il voit un assistant qui répond toujours, même si certaines capacités se dégradent en douceur.

---

### Synthèse — Les 3 actions immédiates (Z.ai, validé par consensus des audits)

Z.ai (le meilleur rapport, 8/10) a identifié 3 actions qui transforment NURU de « copilote » à « assistant » :

| # | Action | Pourquoi | Effort | Impact |
|---|--------|----------|--------|--------|
| 1 | **Contrôle shell sécurisé** | L'action est le différenciateur #1. Sans elle, NURU est un oracle. | 2 semaines (Phase 1) | 🔟/🔟 |
| 2 | **Prompt dynamique depuis la mémoire** | Le prompt hardcodé bloque toute personnalisation. Z.ai : « Plus grande faiblesse cachée ». | 1 semaine (Phase 3) | 9/10 |
| 3 | **Wake word + conversation vocale** | « Hey NURU » est le marqueur JARVIS #1 dans l'imaginaire collectif. | 4 semaines (Phase 2) | 10/10 |

**Ces 3 actions, livrées dans les 3 à 6 prochains mois, transforment NURU d'un copilote intelligent en un véritable assistant personnel. Chaque pièce du puzzle se connecte. (Z.ai, recommandation finale.)**

---

### Résumé V12 — Timeline

```text
Phase 0 ─ Consolidation (S1-S2) ── Nettoyage V4, routeur unique, prompt unique, pyproject
              ↓
Phase 1 ─ Action (S3-S8) ── Shell sécurisé → Contrôle OS → Navigateur → Fichiers → MCP
              ↓
Phase 2 ─ Multimodal (S9-S14) ── STT → TTS → Wake word → VAD → Vision écran → Vision doc
              ↓
Phase 3 ─ Proactivité (S15-S18) ── ProactiveEngine → Prompt dynamique → Consolidation → Routines
              ↓
Phase 4 ─ Écosystème (S19-S20) ── MCP Client/Server → Intégrations → Security hardening
```

**Durée totale estimée** : 20 semaines (~5 mois solo intensif)
**RAM cible finale** : < 7.0 Go (tous modes confondus)
**Investissement TokenJuice** : -40% à -50% tokens — le carburant qui rend tout ça possible sur M1.

---
