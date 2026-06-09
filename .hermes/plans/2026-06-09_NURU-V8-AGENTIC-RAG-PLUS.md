# NURU V8+ — Plan de Transformation Agentic RAG (Version Finale)

> **Version finale** intégrant :
> - 4 audits techniques externes
> - Feedback Leblanc (Groq = LLM principal)
> - 5 retours supplémentaires de validation croisée
> 
> Date : 2026-06-09 | Priorité : 🔥 Critique

---

## 0. Décision Architecturale Fondamentale

### Multi-Cloud, pas mono-fournisseur

Le plan V8+ mentionne "Groq" comme fournisseur cloud par défaut, mais **NURU ne dépend pas exclusivement de Groq**. L'utilisateur fournira des clés API pour plusieurs fournisseurs :
- **OpenCode Zen** (DeepSeek)
- **OpenRouter** (accès à ~200 modèles)
- **NVIDIA** (NIM / Llama / Nemotron)
- **DeepSeek** (API directe)
- **Groq** (déjà configuré)

Le pipeline ne doit PAS coder en dur `groq` comme seul fournisseur cloud. Le routage cloud est un choix entre **local (Phi-4-mini)** et **cloud (le meilleur fournisseur disponible)**. La sélection du fournisseur se fait via `settings.yaml` avec ordre de préférence, fallback, et circuit breaker — c'est déjà partiellement implémenté dans `llm_cloud.py` (V6).

**Règle d'implémentation :** partout où le plan dit "Groq" (Query Rewriter, HyDE, Vérificateur, Décomposeur, LLM principal RAG), lire "le LLM cloud configuré dans settings.yaml". La logique de sélection du fournisseur est dans `src/llm_cloud.py` et ne change pas structurellement.

### Nouveau routage (V8+)

```
[SemanticRouter V6 amélioré]
        │
        ├── SIMPLE (salutations, chitchat, sans RAG) → Phi-4-mini
        │
        ├── RAG (contexte documentaire présent)  → Cloud SYSTÉMATIQUE
        ├── COMPLEX (recherche web)              → Cloud
        ├── Query Rewriting / HyDE               → Cloud
        ├── Boucle rétroaction                   → Cloud
        ├── Vérificateur faits                   → Cloud
        ├── Décomposition questions              → Cloud
        └── Fallback (hors-ligne)                → Phi-4-mini + contexte tronqué
```

---

## 1. Micro-corrections intégrées (issues des 5 retours)

### 1.1 Décomposeur — Circuit breaker + conditionnement renforcé ✅

```python
# src/rag/decomposer.py
MAX_SUB_QUERIES = 3  # Plafond strict anti-explosion
MIN_WORDS_FOR_DECOMPOSE = 10  # Évite la décomposition de "superficie et population"

async def should_decompose(query: str) -> bool:
    """Ne décomposer que si la requête est assez longue ET a des connecteurs."""
    if len(query.split()) < MIN_WORDS_FOR_DECOMPOSE:
        return False
    connectors = {"et", "ainsi que", "ainsi qu'", ",", "ou", "puis", "ensuite",
                  "ainsi", "également", "de plus", "par ailleurs"}
    words = set(query.lower().split())
    return bool(words & connectors)

async def decompose_query(query: str) -> list[str]:
    if not await should_decompose(query):
        return [query]
    prompt = "..."
    sub_queries = await groq.generate_structured(prompt)
    return sub_queries[:MAX_SUB_QUERIES] if len(sub_queries) > 1 else [query]
```

### 1.2 Vérificateur faits — Protection anti-boucle ✅

```python
# src/core/query_context.py — Ajouter
already_fact_checked: bool = False

# src/rag/fact_checker.py — Ajouter
@dataclass
class FactCheckResult:
    verified: bool
    issues: list[str] = field(default_factory=list)
    confidence_delta: float = 0.0

# src/nuru_core.py — Dans la boucle de génération
if not ctx.already_fact_checked and confidence_label in ("FAIBLE", "MOYENNE"):
    ctx.already_fact_checked = True
    check = await fact_checker.verify(response, sources)
    if not check.verified and not ctx.already_retried_fact_check:
        ctx.already_retried_fact_check = True
        # Régénérer avec instruction stricte
    elif not check.verified:
        # Abandonner → renvoyer réponse avec warning de confiance faible
        response += "\n\n⚠️ **Avertissement** : Certaines affirmations n'ont pas pu être vérifiées contre les sources disponibles."
```

### 1.3 HyDE — Trigger aligné sur FAIBLE/ABSENT ✅

```python
# src/rag/multi_search.py
# Au lieu de checker score < 0.50 (obsolète avec le nouveau seuil à 0.40) :
if confidence_label in ("FAIBLE", "ABSENT"):
    hyde_results = await _try_hyde(rewritten_query)  # ← requête réécrite, pas originale
```

**Latence réelle HyDE** (documentée) : Appel Groq (0.3s) + Embedding MLX (0.2s) + sqlite-vec (0.1s) = **~0.6-1.0s**. Gérée via `asyncio.to_thread` + message UI "🔍 Recherche approfondie...".

### 1.4 Ordre Query Rewriter → HyDE ✅

```
Requête originale
    │
    ▼
[Query Rewriter (Groq)] → requête réécrite
    │
    ▼
[Multi-Strategy Orchestrator]
    ├── Vectoriel (original + réécrite) — Dual Query (déjà en V6)
    ├── FTS5
    ├── Métadonnées
    ├── Grep (si FAIBLE/ABSENT)
    └── HyDE (si FAIBLE/ABSENT) **← utilise la REQUÊTE RÉÉCRITE**
```

### 1.5 Score Gate — Alignement des seuils ✅

```python
MIN_ABSOLUTE_SCORE = config.rag_score_threshold  # 0.40
FALLBACK_THRESHOLD = config.rag_score_fallback    # 0.25

# HyDE trigger :
if confidence_label in ("FAIBLE", "ABSENT"):  # = score < 0.25
    hyde_results = await _try_hyde(rewritten_query)

# Boucle rétroaction :
if confidence_label in ("FAIBLE", "ABSENT") and found_chunks == 0 and max_score < 0.30:
    retry_needed = True
```

### 1.6 ContextBudget — Budget distinct pour le vérificateur ✅

```
Budget génération (Groq) : 90% RAG / 5% faits / 3% historique / 2% autres
Budget vérificateur (Groq) : séparé, ~2500 tokens (2000 sources + 500 réponse)

Le vérificateur a SON propre appel API, pas de compétition avec le budget génération.
```

### 1.7 Gestion offline — Check connectivité en tête de pipeline ✅

```python
# src/nuru_core.py — Avant toute opération RAG
async def _check_groq_online(self) -> bool:
    """Vérification rapide (0.5s timeout) avant d'engager le pipeline RAG."""
    import socket
    try:
        loop = asyncio.get_running_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, 
                lambda: socket.create_connection(("api.groq.com", 443), timeout=0.5)),
            timeout=0.5
        )
        return True
    except (socket.timeout, OSError, asyncio.TimeoutError):
        return False

# Dans process_query() :
if intent_internal in ("RAG", "COMPLEX"):
    groq_available = await self._check_groq_online()
    if not groq_available:
        yield "⚠️ **Mode hors-ligne** : Groq indisponible. Analyse documentaire limitée.\n\n"
        # Fallback : Phi-4-mini avec top_1 chunk seulement
        rag_context, rag_result = await self.rag.retrieve(query, top_k=1)
        # Troncature agressive pour fenêtre 4096 tokens
        rag_context = rag_context[:2000]  # ~500 tokens max
        use_cloud = False
```

### 1.8 Normalisation RRF — Utiliser les RANGS, pas les scores bruts ✅

```python
# src/rag/multi_search.py — Correction de la fusion
def reciprocal_rank_fusion(results_lists: list[list[tuple]], k: int = 60) -> list[tuple]:
    """RRF standard : utilise les RANGS, pas les scores.
    
    Chaque stratégie contribue : 1 / (k + rang)
    Un document présent dans 2 stratégies obtient un score = somme des RRF.
    """
    from collections import defaultdict
    scores = defaultdict(float)
    
    for strategy_results in results_lists:
        for rank, (content, source, _) in enumerate(strategy_results, start=1):
            rrf_score = 1.0 / (k + rank)
            scores[(content, source)] += rrf_score
    
    # Trier par score RRF décroissant
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [(content, source, score) for (content, source), score in ranked]
```

### 1.9 Extraction PDF — Bibliothèque encapsulée dans to_thread ✅

```python
# src/rag/file_search.py
import pypdf  # Léger, pas de dépendance lourde
import asyncio

async def extract_pdf_text(filepath: str) -> str:
    """Extraction PDF encapsulée dans to_thread avec fallback silencieux."""
    try:
        def _extract():
            reader = pypdf.PdfReader(filepath)
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
                if len(text) > 5000:
                    break  # Limite 5000 chars
            return text.strip()
        
        text = await asyncio.to_thread(_extract)
        return text[:5000] if text else ""
    except Exception:
        return ""  # Fallback silencieux → _match_filename sera utilisé
```

### 1.10 Cache sémantique — Stocker le diagnostic AVEC la réponse ✅

```python
# src/memory_store.py — Modification du cache
def save_to_cache(self, query: str, response: str, diagnostic: dict = None):
    """Stocke réponse + diagnostic pour retracer la décision."""
    payload = {
        "response": response,
        "diagnostic": diagnostic or {},
        "timestamp": time.time(),
    }
    # ... stocker dans semantic_cache (inchangé)
```

---

## 2. Architecture V8+ Finale

```
REQUÊTE UTILISATEUR
        │
        ▼
[Cache Sémantique] ← hit → Réponse immédiate (avec diagnostic stocké)
        │ (miss)
        ▼
[SemanticRouter]
        │
        ├── SIMPLE → [Phi-4-mini]
        │
        └── RAG / COMPLEX
            │
            ▼
        [Check Groq Online] ← 0.5s timeout → indisponible ?
            │                       ├── OUI → Fallback Phi-4-mini (top_1 chunk, tronqué)
            │                       └── NON → continuer
            │
            ▼
        [RAGDiagnostic]
            │
            ▼
        [Index Health Check]
            │
            ▼
        [Query Rewriter (Groq)] → requête réécrite
            │
            ▼
        [Décomposeur] ← si len > 10 + connecteurs → MAX_SUB_QUERIES=3
            │
            ▼
        [Multi-Strategy Orchestrator] ← to_thread()
            ├── 1. Vectoriel + FTS5 (Dual Query V6, réécrite)
            │   └── Si score > 0.75 → STOP (early stopping)
            ├── 2. Métadonnées
            ├── 3. HyDE (si FAIBLE/ABSENT) ← requête réécrite
            └── 4. Grep (si FAIBLE/ABSENT, to_thread, ligne par ligne, exclude Nuru_Brain)
            │
            ▼
        [RRF Fusion] ← RANGS, pas scores (k=60)
            │
            ▼
        [Déduplication sémantique] ← cos > 0.90 → drop
            │
            ▼
        [Score Gate 3 niveaux] ← TOUJOURS contexte
            HAUTE   → top_k=5
            MOYENNE → top_k=3
            FAIBLE  → top_k=2 + déjà grep/HyDE
            │
            ▼
        [ProfileBoost x2.5]
            │
            ▼
        [Groq Generation] ← streaming, 90% budget RAG
            │
            ▼
        [Détection échec] ← métriques objectives
            ── confidence FAIBLE/ABSENT + found_chunks=0 + max_score<0.30
            │
            ├── Échec → [Reformulation Groq] → [2ème passe (retry=1)]
            └── Succès → [Vérificateur faits (Groq)] 
                │           ← already_fact_checked guard
                ├── OK → Réponse finale
                ├── KO + retry → Régénération (1 max)
                └── KO + déjà retry → Warning + réponse originale
            │
            ▼
        [Réponse UI + Diagnostic → Cache sémantique]
```

---

## 3. Plan d'implémentation — Sprints

### Sprint 0 : Infrastructure (1 jour)

| # | Tâche | Fichier | Durée |
|---|-------|---------|-------|
| 0.1 | Mode WAL SQLite | `src/rag_engine.py` | 15min |
| 0.2 | Vérification RAM avant multi-stratégie | `src/rag/multi_search.py` | 30min |
| 0.3 | Whitelist chemins read_file | `src/rag/read_tool.py` | 30min |
| 0.4 | Exclure ~/Nuru_Brain du grep | `src/rag/file_search.py` | 15min |
| 0.5 | Check connectivité Groq en tête pipeline | `src/nuru_core.py` | 30min |

### Sprint 1 : Observabilité (2 jours)

| # | Tâche | Fichier | Durée | Test |
|---|-------|---------|-------|------|
| 1.1 | RAGDiagnostic (timing par stratégie) | `src/rag/diagnostics.py` | 1h30 | ✅ |
| 1.2 | Injecter diagnostic dans retrieve() | `src/rag_engine.py` | 1h | ✅ |
| 1.3 | Index Health Check | `src/rag/index_health.py` | 2h30 | ✅ |
| 1.4 | Wrapper to_thread sur I/O | `src/rag_engine.py` | 1h | ✅ |
| 1.5 | Persister diag dans TraceCollector | `src/learning/trace_collector.py` | 1h | - |
| 1.6 | already_fact_checked + already_retried_fact_check dans QueryContext | `src/core/query_context.py` | 30min | ✅ |

### Sprint 2 : Routage cloud + Score Gate (3 jours) 🔥

| # | Tâche | Fichier | Durée | Test |
|---|-------|---------|-------|------|
| 2.1 | Routage : Groq par défaut pour RAG/COMPLEX | `src/nuru_core.py` | 2h | ✅ |
| 2.2 | Refactor retrieve() — supprimer return early | `src/rag_engine.py` | 3h | ✅ |
| 2.3 | 3 niveaux + effective_k adaptatif | `src/rag_engine.py` | 1h | ✅ |
| 2.4 | Guard vec_results vide | `src/rag_engine.py` | 30min | ✅ |
| 2.5 | Seuils 0.40 / 0.25 | `config/settings.yaml` | 15min | - |
| 2.6 | ContextBudget 90% RAG | `src/context_manager.py` | 30min | - |
| 2.7 | Fallback offline : troncature contexte + top_1 | `src/nuru_core.py` | 1h | ✅ |
| 2.8 | Prompt Groq + warning offline | `src/nuru_core.py` | 1h | - |

### Sprint 3 : Recherche fichiers (2 jours)

| # | Tâche | Fichier | Durée | Test |
|---|-------|---------|-------|------|
| 3.1 | file_search (to_thread, ligne par ligne, max 2MB) | `src/rag/file_search.py` | 2h30 | ✅ |
| 3.2 | Extraction PDF via pypdf dans to_thread | `src/rag/file_search.py` | 2h | ✅ |
| 3.3 | Grep conditionnel (si FAIBLE/ABSENT) | `src/rag_engine.py` | 1h | ✅ |
| 3.4 | read_tool (décision Python) | `src/rag/read_tool.py` | 1h | ✅ |
| 3.5 | Cache grep TTL 60s | `src/rag/file_search.py` | 30min | ✅ |

### Sprint 4 : Multi-stratégie + Query Intelligence (3 jours)

| # | Tâche | Fichier | Durée | Test |
|---|-------|---------|-------|------|
| 4.1 | multi_search (orchestrateur + to_thread) | `src/rag/multi_search.py` | 2h | ✅ |
| 4.2 | Query Rewriter Groq | `src/rag/query_rewriter.py` | 2h | ✅ |
| 4.3 | Décomposeur (circuit breaker 3, len>10) | `src/rag/decomposer.py` | 1h30 | ✅ |
| 4.4 | RRF par RANGS (k=60), pas scores bruts | `src/rag/multi_search.py` | 1h | ✅ |
| 4.5 | Déduplication sémantique (cos > 0.90) | `src/rag/multi_search.py` | 1h | ✅ |
| 4.6 | Early stopping (score > 0.75) | `src/rag/multi_search.py` | 30min | ✅ |
| 4.7 | **HyDE** (si FAIBLE/ABSENT, requête réécrite) | `src/rag/hyde.py` | 2h | ✅ |
| 4.8 | Intégrer multi_search dans RAGEngine | `src/rag_engine.py` | 1h30 | ✅ |

### Sprint 5 : Rétroaction + Vérificateur (2 jours)

| # | Tâche | Fichier | Durée | Test |
|---|-------|---------|-------|------|
| 5.1 | Détection échec métriques (conf FAIBLE/ABSENT + chunks=0 + max_score<0.30) | `src/nuru_core.py` | 1h | ✅ |
| 5.2 | FactCheckResult dataclass | `src/rag/fact_checker.py` | 30min | ✅ |
| 5.3 | Vérificateur faits Groq (already_fact_checked guard) | `src/rag/fact_checker.py` + `nuru_core.py` | 2h30 | ✅ |
| 5.4 | Reformulation Groq 2ème passe | `src/nuru_core.py` | 1h | ✅ |
| 5.5 | already_retried + max=1 | `src/core/query_context.py` | 30min | ✅ |
| 5.6 | Message UI + warning si échec vérif | `src/nuru_core.py` | 30min | - |

### Sprint 6 : Consolidation (2 jours)

| # | Tâche | Fichier | Durée |
|---|-------|---------|-------|
| 6.1 | ProfileBoost APRÈS fusion multi_search | `src/rag_engine.py` | 1h |
| 6.2 | Cache sémantique : stocker diagnostic AVEC réponse | `src/memory_store.py` | 2h |
| 6.3 | Nettoyage orchestrator.py vs nuru_core.py | `src/core/orchestrator.py` | 1h |
| 6.4 | apply_chat_template Phi-4-mini | `src/llm_local.py` | 2h |
| 6.5 | Tests d'intégration | `tests/test_integration.py` | 3h |

---

## 4. Synthèse — Toutes les propositions

| # | Proposition | Source | Verdict |
|---|-------------|--------|---------|
| 1 | Score Gate Dynamique | Audits | ✅ **Adopté** |
| 2 | asyncio.to_thread() | Audits | ✅ **Adopté** |
| 3 | Index Health Check | Audits | ✅ **Adopté** |
| 4 | Normalisation scores → RANGS | Retours | ✅ **Adopté** |
| 5 | read_file décision Python | Audits | ✅ **Adopté** |
| 6 | Boucle métriques objectives | Audits | ✅ **Adopté** |
| 7 | Query Rewriting | Audits | ✅ **Adopté** |
| 8 | Early stopping | Audits | ✅ **Adopté** |
| 9 | Exclure Nuru_Brain | Audits | ✅ **Adopté** |
| 10 | Lecture ligne par ligne | Audits | ✅ **Adopté** |
| 11 | ProfileBoost timing | Audits | ✅ **Adopté** |
| 12 | Déduplication sémantique | Audit 4 | ✅ **Adopté** |
| 13 | Mode WAL SQLite | Audit 2 | ✅ **Adopté** |
| 14 | Cache grep TTL | Audit 4 | ✅ **Adopté** |
| 15 | Prompt injection guard | Audits | ✅ **Adopté** |
| 16 | Timing par stratégie | Audit 3 | ✅ **Adopté** |
| 17 | Tests unitaires | Audit 4 | ✅ **Adopté** |
| 18 | apply_chat_template | Audit 4 | ✅ **Adopté** |
| 19 | **Groq = LLM principal** | **Leblanc** | ✅ **Adopté** 🔥 |
| 20 | **HyDE** | Réévalué | ✅ **Adopté** |
| 21 | **Vérificateur faits** | Réévalué | ✅ **Adopté** |
| 22 | **Décomposition questions** | Réévalué | ✅ **Adopté** |
| 23 | **Décomposeur circuit breaker (MAX=3)** | Retour 1 | ✅ **Adopté** |
| 24 | **already_fact_checked flag** | Retour 1 | ✅ **Adopté** |
| 25 | **HyDE trigger = FAIBLE/ABSENT** | Retour 1 | ✅ **Adopté** |
| 26 | **Check Groq offline en tête** | Retour 1 | ✅ **Adopté** |
| 27 | **RRF par rangs (pas scores)** | Retour 4 | ✅ **Adopté** |
| 28 | **Extraction PDF via pypdf+to_thread** | Retour 3 | ✅ **Adopté** |
| 29 | **Cache sémantique stocke diagnostic** | Retour 4 | ✅ **Adopté** |
| 30 | **Budget vérificateur distinct** | Retour 1 | ✅ **Adopté** |
| 31 | Mode profane | Audit 3 | ❌ **Rejeté** (V10) |

---

## 5. Règles d'exécution strictes

1. **Chaque module créé → testé en isolation AVANT de passer au suivant**
2. **Ne JAMAIS modifier 2 fichiers critiques simultanément** (rag_engine.py + nuru_core.py)
3. **Committer après chaque tâche validée**
4. **Si un test échoue → revenir en arrière**
5. **Check Groq offline en tête du pipeline RAG** avant tout engagement

---

*Plan V8+ Final — 2026-06-09. Intègre 4 audits + feedback Leblanc + 5 validations croisées.*
