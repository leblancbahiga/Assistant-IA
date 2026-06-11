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
| `src/profile_boost.py` | Boost ×2.5 docs personnels |
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
| **Total V9** | **419 tests ✅** | **23 modules** | **0 échec** |

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

**➡️ Prochaine étape : V10 — Sprint 5 : Raisonnement**
Prochains modules à implémenter :
- `ReflexionEngine` — boucle d'auto-critique et correction (2 passes max)
- `SelfConsistency` — vote majoritaire sur 3 réponses
- `ConfidenceCalibrator` — calibration du score de confiance et seuil « je ne sais pas »

Soit **Sprint 6 — Outils** si préférence :
- `ToolRegistry` — registre central des outils
- `DocumentGenerator` — génération Word, PDF, PPT, Excel

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
