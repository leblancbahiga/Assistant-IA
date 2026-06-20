# NURU V13 — Personal Cognitive Operating System

> Vision : Transformer NURU d'un assistant IA agentique avancé en un **système d'exploitation cognitif personnel**.
>
> *Comprendre l'utilisateur — Mémoriser durablement — Gérer des projets — Exécuter des tâches — Utiliser des outils — Interagir par la voix — Anticiper les besoins — Apprendre continuellement — Consolider sa mémoire — Fonctionner localement et dans le cloud*

---

## Architecture V13

```
┌─────────────────────────────────────────────┐
│            NURU PERSONAL OS                 │
├─────────────────────────────────────────────┤
│ Vues & Interface                            │
├─────────────────────────────────────────────┤
│ Voice Engine                                │
├─────────────────────────────────────────────┤
│ Agent Orchestrator                          │
├─────────────────────────────────────────────┤
│ Goal & Project Manager                      │
├─────────────────────────────────────────────┤
│ Memory System + AutoDream                   │
├─────────────────────────────────────────────┤
│ Skills & Presets                            │
├─────────────────────────────────────────────┤
│ Personal Connectors                         │
├─────────────────────────────────────────────┤
│ Multi-LLM Router                            │
├─────────────────────────────────────────────┤
│ Knowledge Graph                             │
├─────────────────────────────────────────────┤
│ Media Intelligence                          │
├─────────────────────────────────────────────┤
│ Learning & Self Improvement                 │
└─────────────────────────────────────────────┘
```

---

## Phase 1 — NURU Memory OS (V13.1) — 4 semaines

Transformer la mémoire actuelle en véritable **cerveau numérique**.

### Module GoalMemory

`src/goals/` — `goal_manager.py`, `goal_tracker.py`, `goal_prioritizer.py`, `goal_reviewer.py`

- Objectifs long terme
- Sous-objectifs
- Échéances
- Progression
- Priorités

Exemples : Développer NURU, Terminer MBA, Projet Palabek, YARID LEAD

### Module ProjectMemory

`src/projects/` — Gestion projets, tâches, jalons, documents, historique.

Chaque projet :
```yaml
name: Projet Palabek
status: active
tasks: [...]
documents: [...]
milestones: [...]
```

### Module AutoDream

`src/dream/` — `dream_engine.py`, `memory_consolidator.py`, `memory_cleaner.py`, `insight_generator.py`

Cycle automatique :
```
Consolidation → Compression → Détection patterns → Création d'insights → Nettoyage
```

Exécution : toutes les nuits ou lors des périodes d'inactivité.

---

## Phase 2 — Knowledge Graph (V13.2) — 3 semaines

### Personal Knowledge Graph

`src/knowledge_graph/` — `graph_builder.py`, `graph_search.py`, `graph_visualizer.py`, `graph_memory_sync.py`

Technologie : NetworkX, SQLite, GraphRAG

```
Leblanc
 ├── MBA
 ├── NURU
 ├── YARID
 ├── Agriculture
 └── Palabek
```

### Smart Context Engine

Relie automatiquement : personnes, projets, documents, événements, souvenirs.

---

## Phase 3 — Multi-LLM System (V13.3) — 2 semaines

### Model Manager

`src/models/` — `model_registry.py`, `model_manager.py`, `model_router.py`, `benchmark_engine.py`

**Modèles locaux** : Phi 4, Gemma 3, Qwen 3, Llama, Mistral

**Modèles cloud** : OpenAI, Anthropic, Google, Groq, DeepSeek, OpenRouter

**Smart Routing** :
| Type | Modèle |
|------|--------|
| Question simple | Phi 4 |
| Programmation | GPT |
| Recherche | Claude |
| Analyse complexe | Qwen |

---

## Phase 4 — Voice System (V13.4) — 4 semaines

**Technologies** : LiveKit, Whisper, Piper, OpenWakeWord

`voice_manager.py`, `wakeword_engine.py`, `stt_engine.py`, `tts_engine.py`, `conversation_stream.py`

- Conversation temps réel
- Mode mains libres
- Wake word "NURU"

**Personnalités vocales** : Professionnel, Coach, Jarvis, Enseignant, Agronome

---

## Phase 5 — Personal Connectors (V13.5) — 5 semaines

### Connector Hub

`src/connectors/`

| Catégorie | Services |
|-----------|----------|
| Productivité | Google Calendar, Outlook Calendar, Apple Calendar |
| Tâches | Todoist, Microsoft To Do |
| Notes | Obsidian, Notion |
| Communication | Gmail, Outlook |
| Médias | Spotify, YouTube Music |

Capacités : Lire, Créer, Modifier, Rechercher, Automatiser.

---

## Phase 6 — Media Intelligence (V13.6) — 4 semaines

Intégration **MediaPipe**.

`image_analyzer.py`, `video_analyzer.py`, `audio_analyzer.py`, `realtime_stream.py`

**Cas d'utilisation** :
- Agriculture : diagnostic maladies
- Documents : OCR intelligent
- Webcam : analyse contexte utilisateur
- Smartphone : vision temps réel

---

## Phase 7 — Personality Engine (V13.7) — 2 semaines

### Personality Manager

`src/personality/`

**Personnalités natives** :
| Nom | Usage |
|-----|-------|
| NURU Professional | Entreprise |
| NURU Coach | Motivation |
| NURU Researcher | Recherche |
| NURU Agronomist | Agriculture |
| NURU Jarvis | Assistant exécutif |

Paramètres : `tone`, `humor`, `initiative`, `verbosity`, `empathy`, `proactivity`.

---

## Phase 8 — Skills Ecosystem (V13.8) — 5 semaines

### Skill Engine

`src/skills/`

```yaml
skill:
  name: Agronomy Expert
  tools: [météo, diagnostic, marchés]
  prompts: [...]
  memory: [...]
  permissions: [...]
```

**Skills officiels** : Agronomy Expert, MBA Assistant, Developer, Project Manager

**Marketplace** : Skill Store avec installation dynamique.

---

## Phase 9 — Presets & Modes (V13.9) — 2 semaines

**Presets** : Work, Research, Agronomy, MBA, Coding, Executive

Chaque preset modifie : outils, personnalité, mémoire, modèles.

---

## Phase 10 — Proactive Intelligence (V13.10) — 4 semaines

### Insight Engine

`src/insights/` — `insight_engine.py`, `activity_monitor.py`, `recommendation_engine.py`

Capacités : détecter retards, opportunités, échéances, incohérences.

> *Exemple : "Le rapport YARID doit être remis demain. Souhaitez-vous le finaliser ?"*

---

## Phase 11 — Nouvelles vues UI (V13.11) — 4 semaines

Chat View, Project View, Goal View, Memory View, Graph View, Skills View, Dashboard View, Voice View, Connector View.

---

## Phase 12 — NURU OS Final (V13.12) — 4 semaines

Intégration complète et validation.

**Objectifs de performance** :
| Métrique | Cible |
|----------|-------|
| RAM | < 7 Go |
| Temps de réponse | < 2 secondes |
| Taux de réussite | > 90 % |
| Hallucinations | < 1 % |

---

## Priorité réelle d'implémentation

1. **GoalMemory** — Objectifs long terme
2. **ProjectMemory** — Gestion projets
3. **AutoDream** — Consolidation nocturne
4. **Knowledge Graph** — Graphe de connaissances
5. **Multi-LLM Manager** — Routage intelligent
6. **Personality Engine** — Personnalités
7. **Connector Hub** — Connecteurs
8. **Voice System** — Voix temps réel
9. **Skills Ecosystem** — Skills dynamiques
10. **Proactive Intelligence** — Proactivité
11. **Media Intelligence** — Vision
12. **Nouvelles vues** — UI

> *Cet ordre maximise la valeur utilisateur tout en limitant les risques techniques. À la fin de cette feuille de route, NURU ne sera plus simplement un assistant IA local, mais un véritable système d'exploitation cognitif personnel capable de gérer les connaissances, les projets, les objectifs, les outils et les interactions de son utilisateur dans un environnement unifié.*

---

*Vision notée le 20 juin 2026 — Phase 0 V12 achevée (HEAD `032eb5b`)*
