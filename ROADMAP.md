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

## ✅ Terminé (Sprint 6 + Sprint 5 reliquats)

### 6.2 — Cache sémantique : stocker diagnostic AVEC réponse
**Fichier :** `src/rag/memory_store.py`
**Commit :** `c1d8121`
✅ `SemanticCache` avec stockage response + diagnostic (JSON envelope)
✅ `get_cache()`, `set_cache()`, `get_diagnostics()`, `get_stats()`, `clear()`

### 6.3 — Nettoyage orchestrator.py vs nuru_core.py
**Commit :** `c1d8121`
✅ `nuru_core.py` devient un wrapper mince autour de `NuruOrchestrator`
✅ Routeur, RAG, FactChecker, boucle rétroaction → tout dans orchestrator.py
✅ Émissions EventBus ajoutées : `rag_score`, `verification_warning`

### 6.4 — apply_chat_template Phi-4-mini
**Commit :** `c1d8121`
✅ `apply_chat_template()` avec détection intelligente multi-tour
✅ Support system/user/assistant via marqueurs de tokens spéciaux

### 6.5 — Tests d'intégration
**Fichier :** `tests/test_integration.py`
**Commit :** `c1d8121`
✅ Pipeline RAG complet avec mock cloud
✅ Pipeline avec décomposition (sub-queries)
✅ Pipeline avec FactChecker + retry loop
✅ Pipeline offline (mode dégradé)

### 5.6 — Message UI + warning si échec vérification
**Fichier :** `src/core/orchestrator.py`
**Commit :** `c1d8121`
✅ Message formaté en markdown (encadré, couleurs, émoji ⚠️)
✅ 3 issues max affichées (au lieu de 2)
✅ Émission EventBus `verification_warning` pour le dashboard

---

## ✅ Migration UI 3 colonnes — Terminée ✅

> Design cible : `/Users/leblancbahiga/Downloads/nuru_v8plus_dashboard_mockup.html`
> Commits : `afdbac9` + `fcb2992`

### Module 1 — RightPanelDiagnostic (panel droit)
**Fichier :** `src/ui/components/right_panel.py` (1089 lignes)
✅ `RightPanelDiagnostic` remplace `MetricsPanel` (même API publique)
✅ RagTabWidget (3 onglets : Métriques, Index, Traces)
✅ MetricsGrid (2×2 : Tokens/s, RAM, Chunks, Latence)
✅ RamBar + RagScoreBar + StrategyDiagnostic + IndexHealthWidget
✅ FactCheckWidget + RetroBanner
✅ `update_from_events()` — draine l'EventBus vers les widgets

### Module 2 — Sidebar enrichie
✅ RecentDocuments + CloudStatusBadge dans NavSidebar
✅ Dots de statut (indexed=#1E6B3A, partial=#6B4E1E)

### Module 3 — Connecteur EventBus → UI
✅ Timer draine les events RAG → widgets diagnostic
✅ Routes : `rag_score`, `generation_complete`, `verification_warning`, `query.decomposed`

### Module 4 — Styles.qss
✅ Palette violet → bleu-vert (#0A0E14, #1A6A9A, #2A8A4A)
✅ Bulles chat bordure colorée, badges RAG chips, citations mockup style

### Module 5 — Composants atomiques
✅ MetricCard, StrategyRow, FactCheckRow, CitationChip

### Composants obsolètes
- `nuru_widgets.py` (MetricsPanel, MetricMiniBar, CircularGaugeWidget) — conservés pour compatibilité mais non utilisés

---

## 🔮 Idées futures (V9+)

- **Mode profane** (V10) — Rejeté en V8+, planifié pour plus tard
- **Web search amélioré** — Intégration Firecrawl ou équivalent
- **Dashboard analytics** — Statistiques d'usage, top sources, stratégies gagnantes
- **Plugins** — Architecture extensible pour nouvelles sources de données
