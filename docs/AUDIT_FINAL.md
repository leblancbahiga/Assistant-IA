# Audit Final — NURU V10

## Résumé Exécutif

**Périmètre** : 16 modules, 5 658 lignes, 3 audits parallèles
**Découvertes** : 18 critiques, 24 modérés, 5 mineurs

## 🔴 Critiques (action immédiate)

| ID | Problème | Fichier | Gravité |
|----|----------|---------|---------|
| R1 | **DELETE sur vec0 inefficace** — les chunks ne sont jamais supprimés | `rag_engine.py:339,831` | 🔴 |
| R2 | **retrieval.py (HybridRetriever) entièrement cassé** — appelle `_search_db_raw` inexistant | `rag/retrieval.py:82` | 🔴 |
| R3 | **Exceptions silencieuses** dans profile_boost, parsing meta, RAM check (aucun log) | `rag_engine.py:597,702,161,754` | 🔴 |
| L1 | **Concurrency non protégée** dans LocalLLM → crash/fuite GPU | `llm_local.py` | 🔴 |
| L2 | **Circuit Breaker non thread-safe** → fiabilité illusoire | `llm_cloud.py:84-110` | 🔴 |
| L3 | **Keep-alive inopérant** — référence dupliquée modèle → fuite GPU garantie | `llm_local.py` + `model_manager.py` | 🔴 |
| L4 | **stream_generate() synchrone** bloque l'event loop 30-60s | `llm_local.py:154` | 🔴 |
| L5 | **Timeout 5s sur generate()** → faux échecs constants | `llm_cloud.py:26` | 🔴 |
| L6 | **max_tokens=150** trop bas → FactChecker et QueryRewriter tronqués | `llm_cloud.py:59` | 🔴 |
| O1 | **Spotlight bloque l'event loop** — subprocess.run dans coroutine | `semantic_router.py:207` | 🔴 |
| O2 | **Keyword check détruit le contexte Spotlight** | `orchestrator.py:268-285` | 🔴 |
| O3 | **Web search jamais appelé** pour COMPLEX non décomposé | `orchestrator.py:199-203` | 🔴 |

## 🟠 Modérés (1 sprint)

| ID | Problème | Fichier |
|----|----------|---------|
| R4 | Reranker chargé/déchargé à chaque requête (1-3s perdu) | `rag_engine.py:621-629` |
| R5 | get_all_doc_meta() scanne toute la table sans limite | `rag_engine.py:680` |
| R6 | _search_db() et _fetch_parent_context() — code mort | `rag_engine.py:731,900` |
| R7 | Duplication embed_sync() / _embed_sync() — 30 lignes code mort | `embedder.py:72-112` |
| R8 | Regex URL cassée dans token_juice — URLs longues jamais compressées | `token_juice.py:57` |
| L7 | Parsing Gemini streaming cassé (indentation fragile) | `llm_cloud.py:170-175` |
| L8 | FactChecker échec silencieux → "tout va bien" même mort | `fact_checker.py:112` |
| L9 | Temperature 0.1 + top_p=1.0 → trop rigide pour RAG local | `llm_local.py:104-106` |
| L10 | max_tokens=600 trop bas pour réponses RAG complètes | `llm_local.py:158` |
| O4 | Seuil RAG incohérent routeur/orchestrateur (0.2 vs 0.35) | `orchestrator.py:242` |
| O5 | Routage émis pour réponses en cache → fausse UI | `orchestrator.py:152-169` |
| O6 | Fire-and-forget sans gestion d'erreurs (3 tasks) | `orchestrator.py:167,507,519` |

## 🟢 Ce qui est bon

- ✅ Score Gate V10 → contexte vide pour résultats non pertinents
- ✅ Vérification lexicale (0/3 mots-clés → rejet)
- ✅ Double retrieve() éliminé (1 appel au lieu de 2)
- ✅ FallbackGuard V2 fonctionnel (AUCUNE SOURCE)
- ✅ FactChecker ignore les contextes "AUCUNE SOURCE"
- ✅ Contexte Spotlight fusionné correctement avec RAG
- ✅ Singleton Embedder thread-safe
- ✅ Pas de fuite de connexion SQLite
- ✅ Tous les async sont correctement awaités

## Plan d'action

### Immédiat (cette session si tu veux)
- R3: Logger les 4 exceptions silencieuses restantes
- O2: Correction du keyword check qui détruit Spotlight
- O3: Web search pour COMPLEX non décomposé

### Prochaine session
- L5-L6: Timeouts 5s → 30s + max_tokens 150 → 500
- L1-L4: Thread-safety LocalLLM + fuite GPU
- O1: Spotlight async via asyncio.to_thread

### Refactor (moyen terme)
- R1: DELETE sur vec0 → rowid mapping
- R2: Supprimer retrieval.py
- R4: Reranker en cache (pas unload/load par requête)
- R6-R7: Nettoyer code mort
