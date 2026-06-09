# NURU V8 — Plan de Transformation Agentic RAG

> **Pour Hermes :** Implémenter ce plan tâche par tâche en validant chaque module avant de passer au suivant.

**Objectif :** Transformer NURU d'un pipeline RAG linéaire fragile en un système agentique multi-stratégie capable d'exploiter les documents locaux aussi efficacement qu'Hermes.

**Problème racine :** NURU utilise un pipeline fixe (extraction → chunking → embedding → retrieval → LLM) où chaque étape est une boîte noire. Si le score vectoriel est < 0.50, le contexte RAG est **vidé** — le LLM ne voit rien des documents. Pas de recherche alternative, pas de fallback, pas de diagnostic.

**Architecture V8 :** Système de recherche multi-stratégie avec fallback progressif :
1. Moteur de recherche capable d'essayer 5 stratégies en parallèle (vectorielle, FTS, métadonnées, grep, web)
2. **Score gate dynamique** : ne plus rejeter le contexte à 0.48 — le fournir avec un niveau de confiance explicite
3. **Outil "read_file" intégré** : NURU doit pouvoir lire un fichier directement quand la recherche vectorielle échoue
4. **Boucle de rétroaction** : si la réponse finale contient "je ne trouve pas", relancer une recherche élargie
5. **Diagnostic permanent** : chaque requête RAG produit un rapport de ce qui a été cherché et trouvé

**Tech Stack :** Python, SQLite FTS5, sqlite-vec, MLX, httpx (inchangé — on améliore la logique, pas les dépendances)

---

## Diagnostic — Pourquoi NURU rate ses documents

Analyse des points de défaillance identifiés dans le code source :

| Étape | Problème | Impact |
|-------|----------|--------|
| **Score Gate** (rag_engine.py:450) | Seuil à 0.50 → si score < 0.50, contexte RAG = "" | **CRITIQUE** : documents pertinents mais mal scorés → LLM voit ZÉRO |
| **Embedder local** (embedder.py) | multilingual-e5-base sur M1 → embeddings de qualité médiocre | Scores souvent entre 0.30-0.55 |
| **Chunking fragile** (v2_chunking.py) | Si chunking échoue → pas d'embeddings → rien dans la DB | Document présent mais invisible |
| **ContextBudget serré** (context_manager.py) | 80% de ~3000 tokens = 2400 tokens pour le RAG | Documents longs tronqués |
| **Pas d'accès direct** | Aucune capacité `read_file` ou `search_files` | Si le RAG ne trouve pas, NURU ne peut pas chercher autrement |
| **Pas de diagnostic** | RAGResult existe mais les logs sont dans des fichiers noirs | Impossibilité de debug "pourquoi ce doc n'a pas été trouvé" |
| **Modèle local faible** (llm_local.py) | Phi-4-mini 4bit → raisonnement limité | Hallucination ou incapacité à comprendre le contexte |
| **Pas de boucle de rétroaction** | Une seule passe RAG, pas de re-tentative | Si la première recherche rate, c'est fini |

---

## Plan d'implémentation

### Phase 0 : Fondations (diagnostic + outils basiques)

---

### Task 0.1 : Créer le diagnostic en temps réel

**Objectif :** Chaque requête RAG produit un rapport structuré visible dans le dashboard.

**Fichiers :**
- Créer : `src/rag/diagnostics.py`
- Modifier : `src/rag_engine.py` (injecter le diagnostic dans RAGResult)

**Step 1: Créer le module de diagnostic**

```python
# src/rag/diagnostics.py
"""
Diagnostic RAG temps réel — enregistre ce qui a été cherché, trouvé, rejeté.
"""
import json
import time

class RAGDiagnostic:
    """Rapport de diagnostic pour une requête RAG."""
    
    def __init__(self):
        self.query = ""
        self.strategies_tried: list[str] = []
        self.strategies_results: dict[str, dict] = {}
        self.verdict = ""
        self.timing_ms = 0.0
        
    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "strategies_tried": self.strategies_tried,
            "strategies_results": self.strategies_results,
            "verdict": self.verdict,
            "timing_ms": round(self.timing_ms, 1),
        }
        
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
    
    def log_strategy(self, name: str, found: int, top_score: float, hit: bool):
        """Enregistre le résultat d'une stratégie de recherche."""
        self.strategies_tried.append(name)
        self.strategies_results[name] = {
            "found": found,
            "top_score": round(top_score, 3),
            "hit": hit,
        }
```

**Step 2: Modifier RAGResult pour accepter le diagnostic**

Dans `src/rag_engine.py`, ajouter dans `RAGResult` :
```python
diagnostic: dict = None  # Ajout V8 — rapport de diagnostic
```

**Step 3: Injecter le diagnostic dans RAGEngine.retrieve()**

À la fin de `retrieve()` :
```python
diagnostic = RAGDiagnostic()
diagnostic.query = query
diagnostic.strategies_tried = ["vectorielle", "fts"]
diagnostic.strategies_results["vectorielle"] = {
    "found": len(vec_results),
    "top_score": top1_score,
    "hit": top1_score >= MIN_ABSOLUTE_SCORE,
}
diagnostic.strategies_results["fts"] = {
    "found": len(fts_results),
    "top_score": 0 if not fts_results else 1.0,
    "hit": len(fts_results) > 0,
}
diagnostic.verdict = f"{'✅' if context else '❌'} {'context_injected' if context else 'empty_rejected'}"
diagnostic.timing_ms = (time.time() - t_start) * 1000
result.diagnostic = diagnostic.to_dict()
```

**Vérification :**
```bash
cd "/Users/leblancbahiga/Downloads/Assistant IA" && .venv/bin/python3 -c "
from src.rag.diagnostics import RAGDiagnostic
d = RAGDiagnostic()
d.query = 'test'
d.log_strategy('vectorielle', 3, 0.65, True)
d.log_strategy('fts', 0, 0.0, False)
print(d.to_json())
"
```
Attendu : JSON structuré avec les deux stratégies.

---

### Task 0.2 : Créer le module de recherche directe fichiers (grep-like)

**Objectif :** NURU doit pouvoir chercher directement dans les fichiers texte quand le RAG vectoriel ne trouve rien.

**Fichiers :**
- Créer : `src/rag/file_search.py`

**Step 1 : Implémenter la recherche dans les fichiers**

```python
# src/rag/file_search.py
"""
Recherche directe dans les fichiers texte — fallback quand le RAG vectoriel échoue.
Fonctionne comme search_files() d'Hermes.
"""
import os
import re
import logging
from pathlib import Path
from typing import Optional
from src.config import config

logger = logging.getLogger(__name__)

# Répertoires de documents monitorés
DOC_DIRS = [
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Downloads/Assistant IA/data"),
]

SUPPORTED_EXTS = {".txt", ".md", ".py", ".json", ".yaml", ".yml", ".csv", ".xml", ".html", ".pdf", ".docx"}

def grep_documents(
    query: str,
    max_results: int = 5,
    context_lines: int = 0,
) -> list[dict]:
    """Cherche le query dans les fichiers des répertoires monitorés.
    
    Returns:
        Liste de {path, filename, line, content, preview, score}
    """
    results = []
    query_lower = query.lower()
    words = [w for w in re.findall(r'\w+', query_lower) if len(w) > 2]
    
    if not words:
        return results
    
    for doc_dir in DOC_DIRS:
        if not os.path.isdir(doc_dir):
            continue
        
        for root, _, files in os.walk(doc_dir):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in SUPPORTED_EXTS:
                    continue
                    
                filepath = os.path.join(root, fname)
                if os.path.getsize(filepath) > 5 * 1024 * 1024:  # Skip >5MB
                    continue
                    
                try:
                    # Pour les PDF/DOCX, on utilise le texte existant s'il est indexé
                    if ext in (".pdf", ".docx"):
                        # Fallback: on cherche juste dans les métadonnées du nom
                        score = _match_filename(fname, words)
                        if score > 0:
                            results.append({
                                "path": filepath,
                                "filename": fname,
                                "line": 0,
                                "content": f"[Document: {fname}]",
                                "preview": fname,
                                "score": score * 0.5,  # pénalité : pas de contenu texte
                            })
                        continue
                    
                    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    
                    score = _score_content(content, words)
                    if score > 0.3:
                        preview = content[:300].replace("\n", " ")
                        results.append({
                            "path": filepath,
                            "filename": fname,
                            "line": 0,
                            "content": content[:2000],
                            "preview": preview[:200],
                            "score": round(score, 3),
                        })
                except (IOError, OSError):
                    continue
    
    # Trier par score décroissant
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


def _match_filename(fname: str, words: list[str]) -> float:
    """Score de correspondance dans le nom de fichier."""
    fname_lower = fname.lower()
    matches = sum(1 for w in words if w in fname_lower)
    return matches / len(words) if words else 0.0


def _score_content(content: str, words: list[str]) -> float:
    """Score TF-like simple : proportion de mots trouvés."""
    content_lower = content.lower()
    matches = sum(1 for w in words if w in content_lower)
    if matches == 0:
        return 0.0
    ratio = matches / len(words)
    # Bonus si les mots sont proches (dans les 200 premiers caractères)
    first_200 = content_lower[:200]
    early_matches = sum(1 for w in words if w in first_200)
    early_bonus = 0.2 * (early_matches / len(words)) if words else 0
    return min(1.0, ratio + early_bonus)
```

**Vérification :**
```bash
cd "/Users/leblancbahiga/Downloads/Assistant IA" && .venv/bin/python3 -c "
from src.rag.file_search import grep_documents
results = grep_documents('cv leblanc competences', max_results=3)
for r in results:
    print(f'  [{r[\"score\"]:.2f}] {r[\"filename\"]}')
print(f'Total: {len(results)} résultats')
" 2>&1 | head -20
```

---

### Phase 1 : Score Gate Dynamique (correction critique)

---

### Task 1.1 : Remplacer le score gate binaire par un système à 3 niveaux

**Objectif :** Au lieu de `score < 0.50 = contexte VIDE`, fournir le contexte avec un niveau de confiance explicite que le LLM peut interpréter.

**Fichiers :**
- Modifier : `src/rag_engine.py` (lignes 436-470)

**Step 1 : Ajouter les niveaux de confiance**

Dans `retrieve()`, remplacer la confidence gate :

```python
# AVANT (problématique) :
# if not is_reliable:
#     result.rejection_reason = ...
#     return "", result

# APRÈS (V8 — 3 niveaux) :
if is_reliable:
    confidence_label = "HAUTE"
elif top1_score >= FALLBACK_THRESHOLD:
    confidence_label = "MOYENNE"
    logger.info(f"RAG V8: score={top1_score:.2f} >= fallback ({FALLBACK_THRESHOLD}) → contexte fourni avec confiance MOYENNE")
else:
    confidence_label = "FAIBLE"
    logger.info(f"RAG V8: score={top1_score:.2f} < fallback ({FALLBACK_THRESHOLD}) → contexte fourni avec confiance FAIBLE")
```

Puis, après le formatage, **toujours** injecter le contexte, mais avec un en-tête de confiance :

```python
# Remplacer l'ancien "return '', result" par :
confidence_header = f"[CONFIANCE RAG: {confidence_label}] "
if not context.strip():
    context = confidence_header + "Aucun document pertinent trouvé dans l'index vectoriel."
else:
    context = confidence_header + "\n" + context
```

**WARNING :** Cela signifie qu'il faut déplacer TOUTE la logique après le score gate (la fusion RRF, le reranking, etc.) pour qu'elle s'exécute même quand le score est bas. Actuellement, la fonction `return` tôt quand `not is_reliable`. Il faut restructurer pour que le pipeline continue mais avec `top_k` réduit pour les scores faibles.

**Code de remplacement précis (lignes 436-470) :**

```python
        # === V8 : SCORE GATE DYNAMIQUE (3 niveaux) ===
        top1_dist = vec_results[0][2] if vec_results else 1.0
        top1_score = 1 - top1_dist

        self.last_top_score = top1_score
        result.top_score = top1_score
        result.all_scores = [1 - d for _, _, d, _ in vec_results] if vec_results else []

        MIN_ABSOLUTE_SCORE = config.rag_score_threshold
        FALLBACK_THRESHOLD = config.rag_score_fallback

        # V8 : Toujours exécuter le pipeline, mais adapter top_k selon le score
        if top1_score >= MIN_ABSOLUTE_SCORE:
            confidence_label = "HAUTE"
            effective_k = k
        elif top1_score >= FALLBACK_THRESHOLD:
            confidence_label = "MOYENNE"
            effective_k = max(1, k // 2)  # Moins de chunks pour éviter le bruit
            logger.info(f"RAG V8: confiance MOYENNE (score={top1_score:.2f}), top_k réduit à {effective_k}")
        else:
            confidence_label = "FAIBLE"
            effective_k = max(1, k // 3)
            logger.info(f"RAG V8: confiance FAIBLE (score={top1_score:.2f}), top_k réduit à {effective_k}")
            # V8 : Lancer une recherche de fallback dans les fichiers
            try:
                from src.rag.file_search import grep_documents
                file_results = grep_documents(query, max_results=3)
                if file_results:
                    logger.info(f"RAG V8: Fallback grep trouvé {len(file_results)} résultats")
            except Exception:
                pass

        # Continuer le pipeline (fusion RRF, reranking, etc.) avec effective_k
        # ... (code existant après la confidence gate, mais en utilisant effective_k)
```

**Vérification :** Après modification, lancer une requête avec un score bas et vérifier que le contexte est TOUJOURS fourni, avec le bon niveau de confiance.

---

### Task 1.2 : Ajuster le ContextBudget pour prioriser le RAG

**Objectif :** Augmenter le budget RAG de 80% à 90% quand le LLM est le cloud (modèle frontier = grand contexte), et réduire le système prompt.

**Fichiers :**
- Modifier : `src/context_manager.py`

**Step 1 : Ajouter un paramètre de priorité RAG**

```python
def allocate(self, system: str, rag: str, facts: list[str], history: list[dict], 
             user_facts: list[str] = None, include_system: bool = True, 
             model_family: str = "phi", rag_priority: bool = False) -> str:
    # AVANT : budget fixe
    # rag_budget = int(budget * 0.8)
    # user_facts_budget = int(budget * 0.10)
    
    # APRÈS V8 :
    if rag_priority:
        rag_budget = int(budget * 0.90)
        user_facts_budget = int(budget * 0.05)
        facts_budget = int(budget * 0.02)
        history_budget = int(budget * 0.03)
    else:
        rag_budget = int(budget * 0.80)
        user_facts_budget = int(budget * 0.10)
        facts_budget = int(budget * 0.03)
        history_budget = int(budget * 0.07)
```

**Step 2 : Dans `nuru_core.py`, passer `rag_priority=True` quand le modèle est cloud**

Modifier `process_query()` :
```python
full_prompt = self.context_budget.allocate(
    system=system_msg,
    rag=full_rag_context,
    facts=facts,
    history=history,
    include_system=(intent_internal != "COMPLEX"),
    model_family=model_family,
    rag_priority=(intent_internal == "COMPLEX"),  # V8 : plus de contexte RAG pour le cloud
)
```

---

### Phase 2 : Multi-Strategy Retrieval (recherche parallèle)

---

### Task 2.1 : Implémenter la recherche multi-stratégie

**Objectif :** Une requête RAG lance plusieurs stratégies en parallèle et fusionne les résultats.

**Fichiers :**
- Créer : `src/rag/multi_search.py`
- Modifier : `src/rag_engine.py` (utiliser multi_search.retrieve_multi() comme nouveau point d'entrée)

**Step 1 : Moteur de recherche multi-stratégie**

```python
# src/rag/multi_search.py
"""
Moteur de recherche multi-stratégie V8.
Lance 5 stratégies en parallèle, fusionne les résultats par RRF.
"""
import asyncio
import logging
from typing import Optional
from src.rag.diagnostics import RAGDiagnostic

logger = logging.getLogger(__name__)

class MultiStrategySearch:
    """Orchestre la recherche multi-stratégie et fusionne les résultats."""
    
    STRATEGIES = ["vectorielle", "fts", "metadonnees", "grep_fichiers"]
    
    def __init__(self, rag_engine, file_search=None):
        self.rag = rag_engine
        self.file_search = file_search  # module file_search
    
    async def search(
        self,
        query: str,
        k: int = 5,
        diagnostic: Optional[RAGDiagnostic] = None,
    ) -> dict:
        """Lance toutes les stratégies en parallèle et fusionne."""
        results = {}  # stratégie → liste de (content, source, score)
        diag = diagnostic or RAGDiagnostic()
        
        async def _try_vector():
            # Recherche vectorielle standard (déjà dans RAGEngine)
            vec_results = self.rag._search_vector(query)
            if vec_results:
                results["vectorielle"] = vec_results
            diag.log_strategy("vectorielle", len(vec_results), 
                              vec_results[0][2] if vec_results else 0.0,
                              len(vec_results) > 0)
        
        async def _try_fts():
            # Recherche FTS5
            fts_results = self.rag._search_fts(query)
            if fts_results:
                results["fts"] = fts_results
            diag.log_strategy("fts", len(fts_results), 1.0, len(fts_results) > 0)
        
        async def _try_metadata():
            # Recherche dans les métadonnées structurées
            try:
                meta_results = self.rag._search_doc_meta(query)
                if meta_results:
                    results["metadonnees"] = meta_results
                diag.log_strategy("metadonnees", len(meta_results), 0.8, len(meta_results) > 0)
            except Exception:
                diag.log_strategy("metadonnees", 0, 0.0, False)
        
        async def _try_grep():
            # Recherche directe dans les fichiers
            if self.file_search:
                try:
                    file_results = self.file_search.grep_documents(query, max_results=3)
                    if file_results:
                        results["grep_fichiers"] = file_results
                    diag.log_strategy("grep_fichiers", len(file_results),
                                      0.6 if file_results else 0.0,
                                      len(file_results) > 0)
                except Exception:
                    diag.log_strategy("grep_fichiers", 0, 0.0, False)
        
        # Exécuter toutes les stratégies en parallèle
        tasks = [_try_vector(), _try_fts(), _try_metadata(), _try_grep()]
        await asyncio.gather(*tasks)
        
        return results, diag
```

---

### Task 2.2 : Ajouter un outil "read_file" utilisable par le LLM

**Objectif :** Quand le RAG ne trouve pas, NURU doit pouvoir dire "laisse-moi lire le fichier directement" et le faire.

**Fichiers :**
- Créer : `src/rag/read_tool.py`
- Modifier : `src/nuru_core.py` (intégrer le read_tool comme option de secours)

**Step 1 : Implémenter le lecteur de fichier**

```python
# src/rag/read_tool.py
"""
Outil de lecture directe de fichiers — accessible au LLM via le prompt.
Quand le RAG ne trouve rien, NURU peut demander à lire un fichier directement.
"""
import os
import logging
from pathlib import Path
from src.config import config

logger = logging.getLogger(__name__)

DOC_DIRS = [
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Downloads/Assistant IA/data"),
]

def find_and_read_file(filename_hint: str, max_chars: int = 5000) -> str:
    """Cherche un fichier par nom (partiel) et retourne son contenu.
    
    Usage dans le prompt LLM : 
    'Je n'ai pas trouvé dans l'index RAG. Laisse-moi lire le document [nom].'
    """
    # 1. Chercher le fichier par nom partiel
    candidates = []
    name_lower = filename_hint.lower()
    
    for doc_dir in DOC_DIRS:
        if not os.path.isdir(doc_dir):
            continue
        for root, _, files in os.walk(doc_dir):
            for fname in files:
                if name_lower in fname.lower():
                    filepath = os.path.join(root, fname)
                    candidates.append((filepath, fname))
    
    if not candidates:
        return f"[FICHIER INTROUVABLE : '{filename_hint}']"
    
    # 2. Lire le meilleur candidat
    best_path, best_name = candidates[0]
    try:
        with open(best_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if len(content) > max_chars:
            content = content[:max_chars] + "\n...[TRONQUÉ]"
        return f"=== CONTENU DE {best_name} ===\n{content}\n=== FIN ==="
    except Exception as e:
        return f"[ERREUR LECTURE {best_name}: {e}]"
```

**Step 2 : Dans le system prompt RAG, ajouter la possibilité d'utiliser "read_file"**

```python
# Dans nuru_core.py, build_system_prompt(), section "RAPPEL RAG"
if intent == "RAG":
    parts.append("""
# RAPPEL RAG
Le CONTEXTE ci-dessous (entre === DÉBUT DU CONTEXTE === et === FIN DU CONTEXTE ===)
est la source principale. Applique les règles du MODE RAG STRICT ci-dessus.

# ACCÈS DIRECT AUX FICHIERS (V8)
Si le contexte RAG est insuffisant ou si tu as besoin d'un document spécifique,
tu peux demander à lire un fichier directement. Ta réponse DOIT contenir
exactement la ligne suivante sur une ligne séparée pour déclencher la lecture :
[LIRE_FICHIER:nom_du_fichier]
Le système lira le fichier et te fournira son contenu dans le prochain tour.""".strip())
```

---

### Phase 3 : Boucle de rétroaction (2-pass RAG)

---

### Task 3.1 : Implémenter le "second tour" du RAG

**Objectif :** Après avoir généré une réponse, si NURU détecte qu'il n'a pas trouvé l'information, il relance une recherche élargie.

**Fichiers :**
- Modifier : `src/nuru_core.py` (dans process_query)

**Step 1 : Ajouter la détection d'échec et la re-tentative**

```python
# Dans process_query(), après la boucle de génération :
# (Ajouter ce bloc après que response_content est rempli)

# V8 : Boucle de rétroaction — si la réponse indique un échec, relancer
if "je ne trouve pas" in response_content.lower()[:200] or \
   "ne contient pas cette information" in response_content.lower()[:200] or \
   "je n'ai pas" in response_content.lower()[:100]:
    
    logger.info(f"RAG V8: Détection d'échec dans la réponse — re-tentative avec requête élargie")
    
    # Élargir la requête : prendre les 3 mots-clés principaux de la requête originale
    orig_words = [w for w in query.split() if len(w) > 2]
    expanded_query = " OR ".join(orig_words[:5])
    
    # Forcer la recherche web comme fallback
    if intent_internal != "COMPLEX":
        web_context = await self.web.search(query)
        if web_context:
            # Régénérer avec contexte Web
            full_rag_context = web_context
            intent_internal = "COMPLEX"
            # ... reconstruire le prompt et regénérer
            yield "\n\n[⚠️ Deuxième tentative avec recherche Web élargie...]\n\n"
            # Re-générer avec le nouveau contexte
```

---

### Phase 4 : Amélioration de l'affichage des résultats RAG

---

### Task 4.1 : Injecter le diagnostic dans le contexte visible par le LLM

**Objectif :** Le LLM sait pourquoi il a reçu tel contexte — peut adapter sa réponse en fonction.

**Fichiers :**
- Modifier : `src/rag_engine.py` (format_context)

**Step 1 : Ajouter un en-tête de diagnostic dans le contexte**

```python
# Dans _format_context, ajouter un en-tête :
header = f"""=== CONTEXTE DOCUMENTAIRE (RAG V8) ===
Niveau de confiance: {confidence_label}
Score top1: {top1_score:.2f}
Documents trouvés: {len(sources)}
Stratégies utilisées: {', '.join(strategies_used)}

"""
```

---

### Phase 5 : Optimisation continue

---

### Task 5.1 : Réduire le threshold de score gate progressivement

**Objectif :** Ajuster les seuils dans config/settings.yaml pour être moins agressif.

**Fichiers :**
- Modifier : `src/config/settings.yaml`

```yaml
# V8 : Seuils assouplis
rag_score_threshold: 0.40    # Était 0.50 — trop restrictif
rag_score_fallback: 0.25     # Était 0.40 — trop restrictif
rag_k: 5                     # Inchangé
rag_max_context_tokens: 1200 # Était 600 — doubler pour les docs longs
```

---

### Task 5.2 : Activer le cache sémantique intelligent

**Objectif :** Ne pas refaire la même recherche RAG 3 fois (une pour le routing, une pour le RAG, une pour le web).

**Fichiers :**
- Modifier : `src/memory_store.py`

Déjà implémenté dans le `NuruCore.process_query()` : lignes 234-241. Mais le cache est vidé trop tôt si la route change. Vérifier que le cache tient compte des variations de requête (pas de casse, pas de stop words).

---

## Récapitulatif : Ce qui change dans l'UX de NURU

| Avant (V7) | Après (V8) |
|------------|------------|
| "Je ne trouve pas cette info" → stop | "Je trouve X avec faible confiance, je vérifie..." + cherche ailleurs |
| Pipeline fixe → document raté = rien | Multi-stratégie : vectoriel + FTS + grep fichiers |
| Score < 0.50 = contexte vidé | Score < 0.50 = contexte fourni avec "FAIBLE CONFIANCE" |
| Aucun diagnostic | Rapport RAG complet dans le dashboard |
| Une seule passe RAG | Boucle de rétroaction : 2ème tentative si échec |
| Pas d'accès direct aux fichiers | read_file disponible via [LIRE_FICHIER:nom] |

---

## Risques et notes

1. **Performance** : La recherche grep dans les fichiers peut être lente si le répertoire est grand. Limiter à 5 fichiers max, ignorer les fichiers > 5MB.
2. **RAM** : Le grep ne charge qu'un fichier à la fois et lit par morceaux — pas de risque mémoire.
3. **Confiance FAIBLE** : Le LLM doit apprendre à utiliser la mention "FAIBLE CONFIANCE" et à ne pas sur-interpréter le contexte. C'est un prompt engineering à faire.
4. **Boucle de rétroaction** : Ne pas créer de boucle infinie. Maximum 2 passes RAG par requête.
5. **Priorité** : Task 1.1 (Score Gate Dynamique) est la plus critique — c'est le bug majeur qui fait que NURU ignore ses documents.

---

## Résumé des fichiers

| Fichier | Action | Rôle |
|---------|--------|------|
| `src/rag/diagnostics.py` | **Créer** | Diagnostic temps réel des recherches RAG |
| `src/rag/file_search.py` | **Créer** | Recherche grep dans les fichiers locaux |
| `src/rag/multi_search.py` | **Créer** | Orchestrateur multi-stratégie |
| `src/rag/read_tool.py` | **Créer** | Lecture directe de fichier (outil LLM) |
| `src/rag_engine.py` | **Modifier** | Score gate dynamique + diagnostic + fallback |
| `src/context_manager.py` | **Modifier** | Priorité RAG quand cloud + budget augmenté |
| `src/nuru_core.py` | **Modifier** | Boucle de rétroaction + read_tool integration |
| `config/settings.yaml` | **Modifier** | Seuils RAG assouplis |

## Ordre d'implémentation recommandé

1. **Task 0.1** → Diagnostics (prérequis pour tout debug)
2. **Task 0.2** → file_search (fallback concret)
3. **Task 1.1** → Score Gate Dynamique (**URGENT** — corrige le bug critique)
4. **Task 1.2** → ContextBudget prioritaire
5. **Task 2.1-2.2** → Multi-stratégie + read_file
6. **Task 3.1** → Boucle de rétroaction
7. **Task 4.1** → Diagnostic visible
8. **Task 5.1-5.2** → Optimisation

**Chaque tâche doit être : créée → testée individuellement → injectée → testée d'intégration → OK → tâche suivante.**
