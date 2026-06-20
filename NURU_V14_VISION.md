# NURU V14 — Vision Long Terme (après V12)

> Ce document décrit ce qui vient **après** V12. Tout ce qui était V13 (PersonaEngine, SleepCycleManager, ModelRouter, CostGuard, connecteurs de base, pipeline vocal) a été **absorbé dans V12**.
>
> V14 = uniquement ce qui est vraiment nouveau.

---

## Architecture V14 (additive sur V12)

```
┌─────────────────────────────────────────────────────────────┐
│               V14 — COUCHES ADDITIVES                       │
├─────────────────────────────────────────────────────────────┤
│  LifeOS — Fusion automatique agenda/tâches/projets/objectifs │
├─────────────────────────────────────────────────────────────┤
│  Skills Ecosystem (SDK complet + marketplace local)          │
├─────────────────────────────────────────────────────────────┤
│  Media Intelligence (MediaPipe + VLM pour diagnostic agro)  │
├─────────────────────────────────────────────────────────────┤
│  LiveKit — Voix distante multi-appareils (pont, pas remplacement)│
├─────────────────────────────────────────────────────────────┤
│  GoalMemory & ProjectMemory                                    │
├─────────────────────────────────────────────────────────────┤
╞═════════════════════════════════════════════════════════════╡
│               V12 — FONDATIONS (achevée)                    │
│  PersonaEngine · Privacy Layer · SleepCycleManager          │
│  ModelRouter · CostGuard · Connecteurs de base              │
│  Pipeline vocal local · Vision écran/doc · MCP              │
└─────────────────────────────────────────────────────────────┘
```

---

## Module 1 — GoalMemory & ProjectMemory (6 semaines)

**Objectif** : NURU sait ce que tu veux accomplir (objectifs long terme) et où en sont tes projets.

### GoalMemory — `src/goals/`

```yaml
goals:
  - name: "Développer NURU version stable"
    status: "active"
    deadline: "2027-03"
    subgoals: ["V12 release", "V14 release"]
    progress: 35%
    priority: 1
  - name: "Terminer MBA"
    status: "active"
    deadline: "2027-09"
    documents: ["memoire_v3.docx"]
    priority: 2
```

- Objectifs long terme avec échéances
- Progression automatique via connecteurs + apprentissage
- Liens vers projets, documents, tâches associés

### ProjectMemory — `src/projects/`

```yaml
projects:
  - name: "Projet Palabek"
    status: "active"
    tasks: ["Rapport Q3", "Réunion donateurs"]
    milestones: ["2026-08", "2026-12"]
    documents: ["palabek_q2.docx"]
    connected_goals: ["MBA", "YARID"]
```

### AutoDream v2 (extension V12 SleepCycleManager)

La phase REM du SleepCycleManager existant (V12 Phase 3) est étendue pour **créer des insights orientés objectifs** :

```python
class GoalAwareDream(SleepCycleManager):
    """Étend la phase REM avec conscience des objectifs."""
    async def rem_cycle(self):
        links = await self._find_cross_domain_links()
        # + priorisation basée sur les goals actifs
        goal_alerts = self._match_links_to_goals(links)
        await self._propose_goal_insights(goal_alerts)
```

Exemple : "Tu travailles sur le rapport Palabek (projet actif) et ta dernière recherche concernait le M23 (région). Les deux documents partagent le contexte Nord-Kivu — veux-tu que je les relie ?"

---

## Module 2 — LiveKit (voix distante) — 3 semaines

**Rappel** : le pipeline vocal local (STT/TTS/VAD/wake word) est déjà dans V12 Phase 2. LiveKit ajoute **l'accès distant** — depuis un téléphone, un autre Mac, ou depuis Kampala vers l'instance à Goma.

| Aspect | Décision |
|--------|----------|
| Serveur | `livekit-server` auto-hébergé (Docker local), pas cloud managé — privacy-first |
| Mode par défaut | Pipeline local V12 — aucune dépendance réseau |
| LiveKit activé | Opt-in explicite pour accès distant uniquement |
| Pipeline | LiveKit Agents (STT-LLM-TTS) avec barge-in natif |
| Dégradation | Si réseau instable → message texte différé plutôt que voix dégradée |

Ne pas remplacer le pipeline local par LiveKit — l'utiliser comme **pont** pour les cas où tu n'es pas devant le Mac.

---

## Module 3 — Media Intelligence (MediaPipe + VLM) — 4 semaines

**Objectif** : Vision et audio temps réel **sur device**, avec escalade cloud conditionnelle pour les cas complexes.

### Stack technique

| Tier | Technologie | RAM | Usage |
|------|-------------|-----|-------|
| **Détection structurée** | MediaPipe (visages, mains, objets, scène) | ~150 Mo | Temps réel, aucun envoi réseau |
| **Interprétation ouverte** | VLM local ou cloud (selon confidentialité) | ~400 Mo ou réseau | Diagnostic agricole, questions ouvertes |

### Architecture

```python
class MediaPipeline:
    def analyze(self, frame):
        # Tier 1 : MediaPipe (toujours local, toujours gratuit)
        detection = self.mediapipe.detect(frame)
        
        # Tier 2 : VLM si nécessaire
        if detection.requires_interpretation:
            if self.privacy_mode:
                return self.local_vlm.analyze(frame)   # VLM quantisé MLX
            else:
                return self.cloud_vlm.analyze(frame)   # GPT-4o Vision
```

### Cas d'usage

- **Agriculture** : MediaPipe détecte `objet_avec_taches_suspectes` → VLM local interprète "mildiou probable"
- **Documents** : OCR intelligent + MediaPipe pour structure de page
- **Webcam** : détection présence utilisateur + contexte (réunion ? travail ?)
- **Audio scène** : classification sonore (réunion, silence, environnement) sans transcription

**Important** : MediaPipe seul ne fait pas de diagnostic — il détecte des formes. Pour "diagnostic maladies" en agriculture, il faut un VLM fine-tuné ou l'escalade cloud.

---

## Module 4 — Skills Ecosystem (SDK + Marketplace) — 4 semaines

**Objectif** : NURU devient une plateforme extensible — n'importe qui peut ajouter un skill sans toucher au noyau.

### SDK de skills

```yaml
# skills/agronomy/manifest.yaml
name: "Agronomy Expert"
version: "1.0"
entrypoint: "skill.py:run"
permissions:
  - "read_weather_api"
  - "write_nuru_brain"
  - "read_documents"
trigger: ["mode_agronomy", "commande:diagnostic"]
```

### Architecture

| Composant | Rôle |
|-----------|------|
| **SkillRegistry** | Charge les manifestes au démarrage, valide les permissions |
| **SkillSandbox** | Exécution en sous-processus isolé (même logique que CodeExecutor V12) |
| **ViewManager** | Layouts dashboard indépendants : Vue Code, Vue Terrain, Vue Standard |
| **Marketplace local** | Dossier `skills/community/` synchronisable via Nuru_Brain/Obsidian |

### Skills natifs proposés

- Agronomy Expert (diagnostic cultures, météo, marchés)
- MBA Assistant (planning cours, deadlines, révisions)
- Developer (focus code, logs RAG, debug)
- Project Manager (Gantt, jalons, rapports)

**Stratégique** : les skills permettent à NURU d'évoluer sans toucher au noyau. C'est ce qui transforme un projet solo en plateforme.

---

## Module 5 — LifeOS (fusion transverse) — émerge des connecteurs

**Pas un module dédié** — plutôt un **orchestrateur qui fusionne** les données de GoalMemory + ProjectMemory + ConnectorHub pour donner l'impression que NURU comprend la vie de son utilisateur.

```
Goal: "Lancer NURU V14"
  ↓
Project: "Roadmap V14" (ProjectMemory)
  ↓
Réunion demain 10h (Calendar) → Agenda mis à jour
  ↓
Email à préparer pour le partenaire (Gmail)
  ↓
Tâche de développement à terminer (Todoist)
  ↓
Document concerné (Knowledge Graph)
  ↓
Tout ça dans une seule vue "Aujourd'hui"
```

LifeOS n'est pas un sprint séparé — c'est le **résultat** de tous les connecteurs quand GoalMemory + ProjectMemory + Calendar + Tasks sont en place. Il émerge naturellement en Phase 4 V14.

---

## Budget RAM V14 additif

| Module | RAM (pic) | Activation |
|--------|-----------|------------|
| GoalMemory + ProjectMemory | ~80 Mo | Toujours actif |
| LiveKit (session active) | ~250 Mo | Opt-in, distant seulement |
| MediaPipeline (MediaPipe) | ~150 Mo | Capture active seulement |
| VLM local (quantisé) | ~400 Mo | Sur demande d'interprétation |
| SkillSandbox (par skill) | ~30-80 Mo | À la demande |
| **Total V14** | **~550-960 Mo** | (additif sur les ~6.5 Go V12) |

**⚠️ Règle** : `MediaPipeline` et `voice_conversation` (V12) restent mutuellement exclusifs dans le RAMOrchestrator — ne jamais autoriser les deux simultanément sur M1 8 Go.

---

## Roadmap V14

```text
V14.1 ─ GoalMemory + ProjectMemory (6 sem.)
           ↓
V14.2 ─ LiveKit — voix distante (3 sem., dépend V12 Phase 2)
           ↓
V14.3 ─ Media Intelligence (4 sem., dépend V12 Phase 2a Privacy)
           ↓
V14.4 ─ Skills SDK + Marketplace (4 sem.)
           ↓
[LifeOS émerge automatiquement des connecteurs en place]
```

**Durée totale estimée** : ~17 semaines (~4 mois) — après V12 terminé.

---

## Résumé — V12 vs V14

| Ce qui est dans V12 (ne pas re-coder) | Ce qui est vraiment V14 |
|--------------------------------------|------------------------|
| PersonaEngine (traits, presets, ToneAdapter) | GoalMemory & ProjectMemory |
| SleepCycleManager (3 phases mémoire) | LiveKit (voix distante) |
| ModelRouter & CostGuard | Media Intelligence (MediaPipe + VLM) |
| Connecteurs Gmail/Calendar/Tâches | Skills Ecosystem SDK + Marketplace |
| Privacy & Consent Layer | LifeOS (fusion transverse, émerge) |
| Pipeline vocal local (STT/TTS/VAD) | AutoDream v2 orienté objectifs |
| Knowledge Graph SQLite | |
| ProactiveEngine & Routines | |
| MCP Client/Server | |

---

*Vision notée le 20 juin 2026 — V12 Phase 0 achevée (HEAD `e6aceb8`) — V14 propose ~17 semaines de travail après V12*
