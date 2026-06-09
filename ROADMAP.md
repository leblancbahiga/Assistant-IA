# NURU V8+ — Roadmap

> Dernière mise à jour : 2026-06-09
> Audit V8+ (P1-P10) ✅ terminé — restes des Sprints 5-6.

---

## ✅ Terminé (Sprints 1-6 + Audit V8+)

| Section | Statut |
|---------|--------|
| Sprint 1 — Recherche sémantique + FTS | ✅ |
| Sprint 2 — Cloud LLM + Routage sémantique | ✅ |
| Sprint 3 — Recherche fichiers (grep, PDF, cache) | ✅ |
| Sprint 4 — Multi-stratégie (HyDE, RRF, Query Rewriting, Décomposition) | ✅ |
| Sprint 5 — Rétroaction + Vérificateur | ✅ |
| Sprint 6 — Consolidation | ✅ |
| Audit P1-P10 | ✅ (9 commits) |

---

## 🔲 Reste à faire (Sprint 6 + Sprint 5 reliquats)

### 6.2 — Cache sémantique : stocker diagnostic AVEC réponse
**Fichier :** `src/memory_store.py`
**But :** Le cache sémantique stocke actuellement la réponse sans le diagnostic RAG.
Ajouter `rag_diagnostic` au cache pour pouvoir inspecter le diagnostic des
requêtes précédentes.
- [ ] Étendre le schéma/format du cache pour inclure le diagnostic
- [ ] Injecter le diagnostic au moment du store
- [ ] Rendre le diagnostic accessible via `get_cache()`

### 6.3 — Nettoyage orchestrator.py vs nuru_core.py
**Fichiers :** `src/core/orchestrator.py`, `src/nuru_core.py`
**But :** Les deux fichiers ont du code qui se chevauche (routage, FactChecker,
boucle de rétroaction). Nettoyer les responsabilités.
- [ ] Identifier la logique dupliquée
- [ ] Migrer toute la logique RAG dans `orchestrator.py`
- [ ] `nuru_core.py` devient un wrapper mince

### 6.4 — apply_chat_template Phi-4-mini
**Fichier :** `src/llm_local.py`
**But :** Le Phi-4-mini a un format de chat spécifique (tokenizer).
Actuellement le prompt est envoyé brut — utiliser `apply_chat_template()`
pour un formatage correct.
- [ ] Charger le tokenizer/chat_template du modèle
- [ ] Formater le prompt via `apply_chat_template()`
- [ ] Tester avec des messages multi-tour (system/user/assistant)

### 6.5 — Tests d'intégration
**Fichier :** `tests/test_integration.py`
**But :** Les tests unitaires couvrent les modules individuellement. Créer
un test d'intégration qui exécute le pipeline complet : route → retrieve →
generate → verify.
- [ ] Pipeline RAG complet avec mock cloud
- [ ] Pipeline avec décomposition
- [ ] Pipeline avec FactChecker + retry
- [ ] Pipeline offline (mode dégradé)

### 5.6 — Message UI + warning si échec vérification
**Fichier :** `src/core/orchestrator.py`
**But :** Quand le FactChecker détecte un problème mais que la régénération
n'est pas possible (déjà retryé), un avertissement est yieldé dans le flux
mais pas toujours visible. Améliorer le message UI.
- [ ] Message plus visible (encadré, couleur)
- [ ] Optionnel : log dans la session pour relecture

---

## 🎨 Nouveau Design UI — Migration 3 colonnes (en attente)

> Design cible : `/Users/leblancbahiga/Downloads/nuru_v8plus_dashboard_mockup.html`
> Mockup : sidebar 220px + chat central + panel droit 300px (diagnostic RAG temps réel)

### Contexte
Le dashboard actuel a une palette violette avec MetricsPanel à droite.
Le nouveau design remplace tout par une palette bleu-vert (#0A0E14, #1A6A9A, #2A8A4A)
avec un panel droit riche affichant le diagnostic RAG en temps réel.

### Plan de migration (5 modules)

#### Module 1 — RightPanelDiagnostic (panel droit)
- [ ] Créer `src/ui/components/right_panel.py` avec :
  - `RagTabs(QTabWidget)` : onglets Métriques / Index / Traces
  - `MetricsGrid(QWidget)` : grid 2×2 (tokens/s, RAM, chunks, latence)
  - `RamBar(QProgressBar)` : barre horizontale RAM unifiée
  - `RagScoreBar` : barre score RAG avec label HAUTE/MOYENNE/FAIBLE
  - `StrategyDiagnostic(QWidget)` : liste des stratégies (Vectoriel 0.81/48ms, FTS5…)
  - `IndexHealthWidget(QWidget)` : documents, warnings, dernier scan
  - `FactCheckWidget(QWidget)` : vérification par source (✅/⚠️)
  - `RetroBanner(QWidget)` : info décomposition, query rewriting
- [ ] Remplacer MetricsPanel par RightPanelDiagnostic dans dashboard.py
- [ ] Supprimer `nuru_widgets.py` (MetricMiniBar, CircularGauge, StrategyBadge deviennent obsolètes)

#### Module 2 — Sidebar enrichie
- [ ] Ajouter `RecentDocuments(QWidget)` : liste des documents récents avec dots de statut
- [ ] Ajouter `CloudStatusBadge(QWidget)` : badge Groq avec dot vert + modèle
- [ ] Ajuster la navigation : liste plate (pas 3 groupes)

#### Module 3 — Connecteur EventBus → UI
- [ ] Créer timer qui draine les events RAG vers les widgets diagnostic
- [ ] Connecter `generation_complete` → StrategyDiagnostic
- [ ] Connecter `query.decomposed` → RetroBanner
- [ ] Connecter `verification_failed` → FactCheckWidget

#### Module 4 — Styles.qss
- [ ] Palette violette → bleu-vert (#0A0E14 fond, #1A6A9A accent, #2A8A4A succès)
- [ ] Bulles chat : bordure gauche colorée (bleu NURU, violet user)
- [ ] Badges RAG : chips avec couleurs de confiance
- [ ] Citations : chips style mockup

#### Module 5 — Composants atomiques
- [ ] `MetricCard` : widget métrique réutilisable (label + valeur + sous-titre)
- [ ] `StrategyRow` : ligne de diagnostic (icône + nom + score + temps)
- [ ] `FactCheckRow` : ligne de vérification (icône ✅/⚠️ + texte)
- [ ] `CitationChip` : chip de source cliquable

### Données disponibles
Les données RAG arrivent via l'EventBus (déjà émis par orchestrator.py) :
- `generation_complete` → `rag_result.diagnostic` (strategies_tried, scores, timing)
- `rag_score`, `sources`, `tokens_injected`, `retrieval_time_ms`
- `query.decomposed` → sub_queries
- `verification_failed` → matched/missing citations
- `route.decided` → decision, confidence

### Fichiers concernés
- `src/ui/dashboard.py` — point d'entrée (remplacement MetricsPanel)
- `src/ui/styles.qss` — thème complet
- `src/ui/components/nuru_widgets.py` — obsolète partiellement
- `src/ui/components/console_page.py` — ajustements mineurs badge/citations
- `src/ui/components/chat_bubble.py` — ajout CitationChip si nécessaire
- Nouveau : `src/ui/components/right_panel.py`

### Estimation : ~2 jours de dev

---

## 🔮 Idées futures (V9+)

- **Mode profane** (V10) — Rejeté en V8+, planifié pour plus tard
- **Web search amélioré** — Intégration Firecrawl ou équivalent
- **Dashboard analytics** — Statistiques d'usage, top sources, stratégies gagnantes
- **Plugins** — Architecture extensible pour nouvelles sources de données
