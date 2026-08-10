# Architecture NURU — Séquence d'une requête

**Chantier** : V18-15 apport ④ (documents d'architecture vivants)
**Contrat** : V18.md — V18-15 (l.59), V18-41 (critères de sortie, l.86)
**Nature** : documentation vivante — ZÉRO code

---

## 1. Vue d'ensemble

Une requête utilisateur traverse le pipeline Kernel (7 steps + Act gâté V18.1
C4), qui orchestre les services enregistrés dans `NuruKernel`. Le chemin
actif est `PipelineEngine` (`src/kernel/pipeline.py`) → steps
(`src/kernel/pipeline_steps.py`) → `RAGOrchestrator`
(`src/orchestration/rag_pipeline.py`) → `RAGEngine` (`src/rag_engine.py`).

```
Utilisateur / UI
      │  query
      ▼
PipelineEngine.run(query, session_id)
      │
      ├── 1. ReceiveQuestion ── normalise, session, TokenJuice
      ├── 2. Route ─────────── Router V16 (déterministe) + legacy, intent
      ├── 3. Retrieve ──────── RAG primary + multi + web fallback + gardes
      ├── 4. BuildContext ──── prompt, faits LTM, RAG, budget token
      ├── 5. Generate ──────── ToT / CoT / Self-Consistency / stream
      ├── 6. Validate ──────── ArchonRefiner, StrictRAG, persistance mémoire
      ├── 6b. Act ──────────── (V18-09, V18.1 C4) actions/tools, GATÉ
      │                        config.enable_act_step (OFF par défaut)
      └── 7. Respond ───────── yield final vers UI
```

## 2. Déroulé détaillé

### 2.1 ReceiveQuestion
- Normalise la requête, crée/récupère la session (`session_store`), applique
  TokenJuice en entrée si configuré.
- Règle V17 : l'intent `SIMPLE` court-circuite RAG et historique session en
  aval (prompt minimal, cf. BuildContext).

### 2.2 Route
- Le routeur V16 (`src/routing/v16/router_v16.py`) est 100 % déterministe :
  N1 fast-rules → N2 intent-scoring → N3 semantic (ambigu uniquement) →
  N4 context → N5 fusion → N6 multi-route. Zéro LLM, zéro cloud, zéro modèle.
- Le routeur legacy (`src/routing/router.py`) conserve le chemin Spotlight
  (N4) et le fallback cloud (N5), gâtés par `minimal_pipeline` en Mode
  Minimal Pipeline (V18-15).

### 2.3 Retrieve
- `RAGOrchestrator.retrieve_primary` : retrieval unique via
  `RAGEngine.retrieve` (sqlite-vec + BM25, RRF).
- `RAGOrchestrator.retrieve_multi` : décomposition optionnelle
  (`_try_decompose`) + recherche multi-sous-requêtes + web fallback.
- Format du contexte RAG produit : `[SOURCE i]` (`rag_engine.py`).
- Garde V18-31 Fast-Fail : `check_strict_blocks` bloque la génération quand
  une requête documentaire n'a AUCUN contexte (refus Strict RAG).

### 2.4 BuildContext
- Assemble prompt système + RAG + web + faits LTM + historique session.
- V18-24 (non implanté) : rebranchement du prompt système via
  `NuruCore.build_system_prompt` (actuellement `None` selon chemin actif).
- Mode Minimal Pipeline (V18-15) : intégration Spotlight court-circuitée.

### 2.5 Generate / Validate / Act / Respond
- Generate : streaming, ToT/CoT/Self-Consistency selon configuration.
- Validate : vérification citations post-génération, ArchonRefiner,
  persistance mémoire (LTM, session, faits).
- Act (V18.1 C4) : step d'action, no-op strict quand
  `config.enable_act_step=False` (défaut) — ne charge `src.tools` qu'à la
  demande.
- Respond : retour final vers l'UI (ou le contexte appelant).

## 3. Mode Minimal Pipeline (V18-15, flag benchmark UNIQUEMENT)

`config.minimal_pipeline` (False par défaut) court-circuite 5 optimisations :

| Optimisation | Point de gating |
|---|---|
| Query Rewrite | `rag_engine.py` (branche `optimized_query = query`) |
| HYDE | `multi_search.py` `_should_use_hyde` → False |
| Spotlight | `router.py` (N4) + `pipeline_steps.py` (intégration) |
| Speculative RAG | `rag_pipeline.py` (non instancié) |
| Décomposition | `rag_pipeline.py` `_try_decompose` → `[query]` |

Les gardes V18-31 (Fast-Fail Strict RAG), V18-02 (état RAG typé) et V18-14
(FSM Validate) ne sont JAMAIS désactivées par ce flag.

## 4. Dernière vérification

- Date : 2026-08-10
- Vérifié : chemin actif `PipelineEngine` 8 steps (dont Act gâté), routeur
  V16 déterministe (40/40 cas), gardes `check_strict_blocks` /
  `VerifyCitations` indépendantes du flag minimal, 5 gating points
  `minimal_pipeline` présents.
