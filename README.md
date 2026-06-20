<div align="center">
  <img src="https://img.shields.io/badge/NURU-V12-00D4FF?style=for-the-badge&logo=python&logoColor=white" alt="NURU V12"/>
  <img src="https://img.shields.io/badge/Platform-macOS%20M1-39FF14?style=for-the-badge&logo=apple&logoColor=white" alt="macOS M1"/>
  <img src="https://img.shields.io/badge/RAM-8%20Go%20Unified-FFB000?style=for-the-badge" alt="8 Go RAM"/>
  <img src="https://img.shields.io/badge/Tests-66%20%F0%9F%94%B4%20Phase%200-success?style=for-the-badge" alt="66 Tests"/>
  <img src="https://img.shields.io/badge/Status-V12%20Actif%20(Phase%200%20%E2%9C%85)-00D4FF?style=for-the-badge" alt="Status V12"/>
</div>

<br/>

<h1 align="center">🌀 NURU — Personal Cognitive OS V12</h1>
<p align="center">
  <i>De l'assistant IA agentic au système d'exploitation cognitif personnel</i>
</p>

<p align="center">
  <b>🇫🇷 Français</b> · Conçu pour MacBook Pro M1 (8 Go RAM unifiée) · <b>Privacy-first</b>
</p>

---

## ✨ Vision

**NURU V12** est la fondation d'un **Personal Cognitive Operating System** — une présence numérique qui comprend, anticipe et agit pour son utilisateur. Pas un chatbot, pas un copilote : **un JARVIS personnel**.

| Pilier | V10 → V12 | Différenciateur |
|--------|-----------|-----------------|
| **Identité** | Prompt hardcodé → **PersonaEngine** + traits configurables | Z.ai : « plus grande faiblesse cachée » |
| **Mémoire** | Faits utilisateur simples → **SleepCycleManager** (3 phases light/deep/REM) | Courbe de l'oubli, journal de rêves |
| **Action** | « Copilote qui parle » → **Agent Loop** (planner → executor → verifier → recovery) | Contrôle OS, navigateur, shell sandboxé |
| **Voix/Vision** | Texte seul → **Pipeline vocal local** (STT+TTS+wake word+VAD+barge-in) + vision écran/doc | Présence Z.ai animée (Orb 7 états) |
| **Proactivité** | Attend qu'on lui parle → **ProactiveEngine** + signaux + routines | Rappels, suggestions, surveillance |
| **Écosystème** | Îlot → **MCP Client/Server** + intégrations Gmail/Calendar/Tâches | Interopérabilité Claude Desktop, Cursor |
| **Sécurité** | Correctifs ponctuels → **Privacy Layer** + CostGuard + Harnais d'évaluation | Opt-in granulaire, budget cloud |

---

## 🏗️ Architecture V12

```
┌──────────────────────────────────────────────────────────────────────┐
│                    PHASE 2a — GARDE-FOUS & IDENTITÉ                   │
│  PrivacyLayer · ConsentManager · AuditLog · PersonaEngine · Traits   │
├──────────────────────────────────────────────────────────────────────┤
│                    PHASE 2 — MULTIMODAL                               │
│  STT (mlx-whisper) · TTS (Kokoro) · Wake word · VAD · Barge-in       │
│  Vision écran (cloud) · Vision doc (OCR+LLM) · VoiceOverlay Z.ai     │
├──────────────────────────────────────────────────────────────────────┤
│                    PHASE 3 — PROACTIVITÉ & MÉMOIRE                    │
│  ProactiveEngine · SleepCycleManager · Prompt dynamique               │
│  PersonaEngine (plein) · Routines · Harnais d'évaluation              │
├──────────────────────────────────────────────────────────────────────┤
│                    PHASE 4 — ÉCOSYSTÈME                               │
│  MCP Client/Server · ModelRouter · CostGuard · Intégrations           │
│  (Gmail, Calendar, Tâches, Spotify, GitHub, Notion, Slack)           │
├──────────────────────────────────────────────────────────────────────┤
│                    PHASE 1 — AGENT LOOP (ACTION)                      │
│  ToolRegistry · Shell sandboxé · Navigateur · Contrôle OS · Fichiers │
├──────────────────────────────────────────────────────────────────────┤
│                    PHASE 0 — CONSOLIDATION (✅ TERMINÉE)               │
│  Router unique · DynamicPromptBuilder · 66 tests · Design Z.ai V12   │
├──────────────────────────────────────────────────────────────────────┤
│                    FONDATIONS V9-V10 (existant)                       │
│  RAG hybride · Mémoire V9 · Multi-provider cloud · TokenJuice        │
└──────────────────────────────────────────────────────────────────────┘
```

### 🎨 Design Z.ai — Présence Numérique

Le design V12 remplace le cockpit 3 colonnes par une **présence animée** :

| Composant | Description |
|-----------|-------------|
| **NuruPresenceOrb** | Orbe 120px animé QPainter, **7 états** (idle, listening, thinking, speaking, acting, error, sleeping), cycle EventBus |
| **VoiceOverlay** | Fenêtre frameless 60%×40%, animations de transition (scale 0.8→1.0, 250ms), disparition après 8s silence |
| **FloatingWidget** | Widget flottant 160px, parallélisable (Phase 3) |
| **macOS native** | Menu bar QSystemTrayIcon, raccourcis ⌥␣ ⌘⇧N |
| **Palette** | `#0D1117` (fond) / `#00D4FF` (cyan) / `#E8A87C` (corail accent) |
| **Performance** | < 5% CPU (QPainter), max 5% CPU animations |

---

## 🚀 Roadmap V12 (21 sprints, ~5 mois)

```text
Phase 0   ✅ Consolidation       (S1-S2)    Nettoyage V4, routeur unique, 66 tests
Phase 1   🔄 Agent Loop          (S3-S8)    Shell → OS → Navigateur → Fichiers → MCP
Phase 2a  🔜 Garde-fous         (S8.5)     Privacy Layer + PersonaEngine (base)
Phase 2   🔜 Multimodal          (S9-S14)   STT → TTS → Wake word → VAD → Vision
Phase 3   🔜 Proactivité         (S15-S18)  Proactive → PersonaEngine → SleepCycle → Routines
Phase 4   🔜 Écosystème          (S19-S20)  MCP → ModelRouter → CostGuard → Intégrations
```

### 🧬 V13 — Absorption dans V12

Conformément à la stratégie « formaliser, réconcilier, compléter », les modules V13-A/B sont **intégrés dans V12** :

| Module V13 | Absorbé dans V12 | Sprint |
|------------|------------------|--------|
| **PersonaEngine** | Identité NURU (traits, presets, ToneAdapter) | Phase 2a (base) + S16 (plein) |
| **Privacy & Consent Layer** | Opt-in capteurs, journal d'audit, indicateur macOS | Phase 2a S8.5 |
| **SleepCycleManager** | 3 phases mémoire (light/deep/REM) | Phase 3 S16 |
| **ModelRouter** | Choix délibéré du LLM par tâche | Phase 4 S20 |
| **CostGuard** | Budget cloud (2$/jour) + bascule auto locale | Phase 4 S19 |
| **Connecteur Tâches** | Reminders/Todoist générique | Phase 4 S20 |
| **Harnais d'évaluation** | Tests régression mémoire + cohérence persona | Phase 3 S18 |

**Ce qui reste V13** (après V12) : LiveKit (voix distante), Médiatisation locale MLX, Skills SDK + Vues.

---

## 📁 Structure du projet

```
src/
├── core/                     # Cœur (orchestrateur, policies, exceptions)
├── routing/                  # Routeur N0-N6 + DynamicPromptBuilder (Phase 0)
├── agent/                    # Agent Loop : TaskPlanner, Executor, Verifier (Phase 1)
├── personality/              # PersonaEngine : traits, presets, ValueGuardrails
├── privacy/                  # Privacy & Consent Layer, audit log (Phase 2a)
├── voice/                    # Pipeline vocal : STT, TTS, wake word, VAD (Phase 2)
├── vision/                   # Vision écran, documents (Phase 2)
├── proactive/                # ProactiveEngine, signaux, routines (Phase 3)
├── memory/                   # MemoryManager V9, SleepCycleManager (Phase 3)
├── mcp/                      # MCP Client/Server, intégrations (Phase 4)
├── models/                   # ModelRouter, CostGuard (Phase 4)
├── security/                 # Security hardening, sandbox (Phase 4)
├── eval/                     # Harnais d'évaluation mémoire & persona (Phase 3)
├── ui/                       # Dashboard, VoiceOverlay, NuruPresenceOrb
│   └── assets/               # Logos V5
├── rag/                      # Multi-stratégie, chunking, HyDE
├── cache/                    # Cache LLM multi-niveau (L1 RAM + L2 SQLite)
├── token_juice.py            # Compression tokens (-40% à -50%)
├── config.py                 # Configuration
└── nuru_core.py              # Orchestrateur principal
```

---

## 🧠 Modules clés

### Routeur Intent-First (V10+)
Classification LLM (~100ms) : `GENERAL_KNOWLEDGE` / `RAG` / `WEB` / `SIMPLE` / `COMPLEX` — décide **avant** tout appel d'outil.

### RAG Hybride V10
Vectoriel + FTS5 + HyDE + Query Rewriting + RRF. Gate de score ≥ 0.30. Extraction DOCX complète (tableaux inclus). Profil auto-détecté (cv/rapport/note).

### Mémoire V9
- **EpisodicMemory** — souvenirs datés et contextuels
- **SemanticMemory** — faits structurés clé/valeur/confiance
- **UserMemory** — préférences utilisateur persistantes
- **ErrorMemory** — historique des erreurs pour auto-correction
- **SleepCycleManager** — consolidation en 3 phases (light/deep/REM)

### Multi-Provider Cloud
Groq (Llama 3.3 70B, primaire) → OpenRouter → DeepSeek → Phi-4-mini (local). Circuit breaker + fallback + **ModelRouter** (choix délibéré par tâche).

### TokenJuice
Compression adaptative -40% à -50% tokens selon le contexte — l'avantage compétitif qui rend tout possible sur M1 8 Go.

---

## 📊 État d'avancement

| Phase | Statut | Modules | Tests |
|-------|--------|---------|-------|
| **Phase 0** — Consolidation | ✅ Terminée | 3 (routing/, prompt_builder, tests/) | **66 ✅** |
| **Phase 1** — Agent Loop | 🔄 En cours | ToolRegistry, executor, planner | — |
| **Phase 2a** — Garde-fous | 🔜 Planifié | Privacy, PersonaEngine base | — |
| **Phase 2** — Multimodal | 🔜 Planifié | STT, TTS, Wake word, VAD, Vision | — |
| **Phase 3** — Proactivité | 🔜 Planifié | Proactive, SleepCycle, Routines, Éval | — |
| **Phase 4** — Écosystème | 🔜 Planifié | MCP, ModelRouter, CostGuard, Intégs | — |

**RAM cible finale** : < 7.0 Go (tous modes confondus)
**V13 Vision** : `NURU_V13_VISION.md` — LiveKit, médiatisation locale, skills SDK

---

## 🚀 Démarrage rapide

```bash
# Lancer le dashboard
python3 src/ui/dashboard.py

# Tests Phase 0
python3 -m pytest tests/ -v
```

---

## 📜 Documentation

| Document | Contenu |
|----------|---------|
| `NURU_V9.md` | Plan V12 détaillé (phases, sprints, design Z.ai) |
| `NURU_V13_VISION.md` | Vision Personal Cognitive Operating System |
| `NURU_AUDIT_SYNTHESE.md` | 7 rapports d'audit, 88 trouvailles |
| `ROADMAP.md` | Roadmap unifiée V12→V13 |

---

*Document mis à jour le 20 juin 2026 — NURU V12 — Phase 0 ✅ — V13-A/B absorbé*
