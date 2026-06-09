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

## 🔮 Idées futures (V9+)

- **Mode profane** (V10) — Rejeté en V8+, planifié pour plus tard
- **Web search amélioré** — Intégration Firecrawl ou équivalent
- **Dashboard analytics** — Statistiques d'usage, top sources, stratégies gagnantes
- **Plugins** — Architecture extensible pour nouvelles sources de données
