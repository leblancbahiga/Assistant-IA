# Audit Qualité Pipeline RAG — NURU V12

**Date** : 2026-06-21  
**Contexte** : Projet NURU V12, pipeline RAG hybride sqlite-vec + FTS5 + RRF  
**Recall@5 annoncé** : 92% sur 25 queries  
**Objectif** : Identifier les 5 principales causes de perte de qualité RAG

---

## TOP 1 — CRITIQUE : HyDE + Grep jamais exécutés (dead code)

### Fichier : `src/rag_engine.py`, ligne 643

```python
ms_results, ms_diag = await self._multi_search.search(
    query=query,
    rewritten_query=optimized_query,
    confidence_label="HAUTE",  # ← HARDCODÉ !
    top_k=k * 2,
)
```

### Fichier : `src/rag/multi_search.py`, lignes 250, 312-318

```python
is_weak = confidence_label in ("FAIBLE", "ABSENT")  # ← Toujours False

# Lignes 312-318 :
if is_weak and ram_ok and self._grep:
    grep_task = asyncio.create_task(self._run_grep(query))
if is_weak and ram_ok and self._cloud:
    hyde_task = asyncio.create_task(self._run_hyde(query))
```

### Diagnostic

Le paramètre `confidence_label` est **hardcodé `"HAUTE"`** dans l'appel à `MultiSearchOrchestrator.search()`. Ce label n'est jamais mis à jour dynamiquement malgré le commentaire « multi_search décide du early stopping via scores ».  

Dans `multi_search.py`, les stratégies lourdes (Round 2 : HyDE + grep) sont conditionnées par `is_weak`, qui n'est `True` que pour `"FAIBLE"` ou `"ABSENT"`. Comme le label est toujours `"HAUTE"` :

- **HyDE** (amélioration du recall +15-25% sur requêtes ambiguës) n'est **jamais appelé**
- **Grep** (recherche fichier par fichier) n'est **jamais appelé**
- Les seules stratégies réellement utilisées sont : vectoriel, FTS, metadata

### Impact qualité

Perte massive sur les requêtes où le score vectoriel + FTS est faible. La feature "early stopping" empêche bien HyDE/grep quand vectoriel est fort (score > 0.75), mais ne peut PAS les déclencher quand vectoriel est faible — car le guard `is_weak` est toujours False.

**Toute requête mal couverte par l'embedding vectoriel ou FTS obtient un RAG vide ou de très mauvaise qualité, sans aucune tentative HyDE ou grep.**

### Correction suggérée

Remplacer la ligne 643 par une logique dynamique :

```python
# Après avoir exécuté les stratégies rapides (Round 1),
# calculer un vrai niveau de confiance basé sur les scores obtenus
initial_results, _ = await self._multi_search.search(
    query=query,
    rewritten_query=optimized_query,
    confidence_label="HAUTE",  # peut être ignoré par multi_search
    top_k=k * 2,
)
```

Ou mieux : supprimer le guard `is_weak` de Round 2 et laisser le `early_stopping` seul décider (score > 0.75 → skip, sinon → lancer HyDE+grep).

---

## TOP 2 — CRITIQUE : Normalisation RRF dépendante du nombre de stratégies, scores incomparables

### Fichier : `src/rag/multi_search.py`, lignes 130-147

```python
max_possible = len(strategy_results) * (1.0 / (k + 1))   # ligne 132
if max_possible <= 0:
    max_possible = 1.0

fused = [
    SearchResult(
        ...
        score=min(rrf_score / max_possible, 1.0),  # ligne 140
        ...
    )
    ...
]
```

### Diagnostic

Le score RRF est normalisé par `max_possible = nombre_de_stratégies × (1 / (k+1))`. Ceci signifie :

- **1 stratégie** (vectoriel uniquement) : `max_possible = 1/61 ≈ 0.0164`  
  → Un résultat rank-1 obtient `0.0164 / 0.0164 = 1.0`
- **4 stratégies** (vectoriel + FTS + metadata + HyDE) : `max_possible = 4/61 ≈ 0.0656`  
  → Un résultat rank-1 dans une seule stratégie obtient `0.0164 / 0.0656 = 0.25`

Les scores normalisés ne sont donc **pas comparables entre deux requêtes** utilisant un nombre différent de stratégies. Pourtant, les seuils de confiance dans `rag_engine.py` (lignes 669-683) sont des constantes **fixes** :

```python
MIN_ABSOLUTE_SCORE = 0.30   # ligne 669
FALLBACK_THRESHOLD = 0.25   # ligne 670
RAG_MIN_USABLE_SCORE = 0.20 # ligne 671
```

Ces seuils traitent le score comme une mesure universelle de similarité sémantique, mais c'est en réalité une grandeur dépendante de l'architecture de la requête.

### Impact qualité

- Les labels HAUTE/MOYENNE/FAIBLE/ABSENT sont **peu fiables** — une requête simple avec 1 stratégie sera toujours classée HAUTE, même si le contenu est médiocre. Une requête avec 4 stratégies sera pénalisée avec des scores plus bas pour des résultats équivalents.
- Le déclenchement conditionnel du reranker (`_should_use_reranker`, seuil à 0.15) et les rejets « hors-sujet » (seuil à 0.20) peuvent **injustement rejeter des résultats valides** selon le nombre de stratégies utilisées.
- Le score final rapporté à l'utilisateur (`result.top_score`, ligne 791) n'est pas une mesure fiable de pertinence.

### Correction suggérée

Remplacer la normalisation par une approche robuste : soit fixer `max_possible` à une constante (ex: 4 × (1/61) = 0.0656 pour 4 stratégies max théoriques), soit ne pas normaliser du tout et utiliser les rangs pour la décision finale.

---

## TOP 3 — MAJEUR : Perte de structure tableaux DOCX

### Fichier : `src/ingestion.py`, lignes 44-53

```python
elif ext == ".docx":
    doc = Document(str(path))
    # V10.1 : extraire aussi le contenu des tables
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            row_text = "\t".join(cell.text for cell in row.cells if cell.text.strip())
            if row_text.strip():
                parts.append(row_text)
    text = "\n".join(parts)
```

### Diagnostic

Les tableaux DOCX sont extraits ligne par ligne, cellules concaténées avec des tabulations, mais **sans les en-têtes de colonnes**. Si un tableau a en-têtes `[Date, Montant, Description]` et une ligne `[2023, 5000, Semences]`, l'extraction produit :

```
2023\t5000\tSemences
```

Le lien entre la colonne et sa valeur est perdu. La phrase extraite ne contient pas `Date : 2023, Montant : 5000`. Pour les documents techniques, rapports financiers, budgets — très courants dans le domaine agronomique — c'est une perte structurelle importante.

### Impact qualité

- Les embeddings sont calculés sur du texte plat sans contexte de colonnes. Une valeur comme `5000` perd son sens (est-ce un montant, une superficie, une quantité de semences ?).
- La recherche FTS ne peut pas retrouver efficacement les données tabulaires.
- Impact particulièrement fort sur les propositions techniques (BEACCOM, formulaires TECH) qui sont une partie importante du dataset d'évaluation.

### Correction suggérée

```python
for table in doc.tables:
    headers = [cell.text.strip() for cell in table.rows[0].cells] if table.rows else []
    for row in table.rows[1:]:
        row_text_parts = []
        for j, cell in enumerate(row.cells):
            val = cell.text.strip()
            hdr = headers[j] if j < len(headers) else ""
            if val:
                row_text_parts.append(f"{hdr}: {val}" if hdr else val)
        if row_text_parts:
            parts.append(" | ".join(row_text_parts))
```

---

## TOP 4 — MAJEUR : Injection de contexte dans le contenu des chunks dilue le signal d'embedding

### Fichier : `src/rag/v2_chunking.py`, lignes 74-92

```python
def to_dict(self) -> dict:
    context_parts = []
    if self.level == "document":
        context_parts.append(f"[RÉSUMÉ] {self.doc_title}")
    elif self.section_title:
        context_parts.append(f"[{self.doc_title} - {self.section_title}]")
    else:
        context_parts.append(f"[{self.doc_title}]")
    if self.importance == "high":
        context_parts.append("[IMPORTANT]")
    content = " ".join(context_parts) + "\n" + self.content  # ← ICI
    return {"content": content, ...}
```

### Fichier : `src/rag/chunking.py`, lignes 138-154 (même pattern)

```python
context_prefix = f"[{doc_title}"
if title:
    context_prefix += f" - {title}"
context_prefix += "]\n"
# contextualized = context_prefix + text  stocké dans le content
```

### Fichier : `src/ingestion.py`, lignes 129-137

```python
chunk_dicts = [c.to_dict() for c in primary_chunks]
contents = [d["content"] for d in chunk_dicts]
# contents[i] est le texte AVEC préfixe [Doc - Section]
embeddings = await self.embedder.embed(contents, is_query=False)
```

### Diagnostic

Le contenu stocké dans l'index et **servant à calculer les embeddings** inclut un préfixe `[Document - Section]` (30-50 caractères). Pour un chunk de 300 caractères, ce préfixe représente 10-17% de la chaîne. Cela signifie que :

1. **L'embedding vectoriel représente autant de métadonnées que de contenu réel** pour les chunks courts. La similarité cosine entre deux chunks du même document mais de sections différentes sera artificiellement élevée à cause du préfixe commun `[Document - ...]`.
2. **La recherche FTS (BM25)** matche sur des mots du préfixe. Une requête pour un terme présent uniquement dans les métadonnées (ex: "CV" dans `[CV Leblanc - Compétences]`) peut faire remonter un chunk peu pertinent.
3. Le `[IMPORTANT]` tag est aussi embarqué dans l'embedding, ce qui est un signal non-sémantique.

### Impact qualité

- Les scores de similarité vectorielle sont « pollués » par le préfixe commun, réduisant la précision de la recherche sémantique.
- Les chunks de sections différentes du même document sont artificiellement rapprochés dans l'espace vectoriel.

### Correction suggérée

Stocker deux champs : `content` (texte brut) pour l'embedding et `contextualized` (texte avec préfixe) pour l'affichage. L'embedding doit être calculé sur le contenu brut uniquement :

```python
# Ingestion : embedding sur contenu brut
embedding = embedder.embed(c.content, is_query=False)  # sans préfixe
# Stockage : contenu contextualisé pour le LLM
store(content=c.to_dict()["content"])  # avec préfixe
```

---

## TOP 5 — MINEUR : Dataset d'évaluation non représentatif et métriques peu informatives

### Fichier : `tests/rag_eval_dataset.yaml` (25 queries)

```yaml
- question: "Quel est le diplôme de Toussaint Omombo ?"
  expected_source: "1 - CURRICULUM VITAE-Omombo...pdf"
  expected_keywords: ["Master", "Environnement", "Gestion des Ressources"]
  doc_type: cv
# ... 24 autres queries similaires
```

### Fichier : `tests/rag_eval_dataset.results.json`

```json
{
  "recall_at_5": 92.0,
  "avg_precision": 89.67,
  "avg_latency": 1.23,
  "n": 25
}
```

### Fichier : `tests/eval_rag.py`, lignes 144-150

```python
# Nettoyer les résultats pour le JSON (enlever les sérialisations complexes)
clean = {k: v for k, v in results.items() if k != "results"}
json.dump(clean, f, indent=2, ensure_ascii=False)
```

### Diagnostic

1. **5 documents seulement** couvrent 25 questions : 2 CVs, 1 proposition technique BEACCOM, 2 lettres de motivation. **Aucune question** ne teste le domaine agronomique (rendement, cultures, sols, irrigation…) pourtant au cœur du projet.
2. **Métriques limitées** : `source_recalled` (match binaire du nom de fichier) et `keyword_precision` (proportion de keywords dans le contexte formaté). Pas de MRR, NDCG, ni mesure de pertinence humaine.
3. **Pas de trace des requêtes ayant échoué** : le fichier `results.json` supprime volontairement les résultats individuels (ligne 148 « enlever les sérialisations complexes »). Impossible de savoir quelles 2 queries sur 25 ont raté, ni pourquoi.
4. **Le Recall@5 à 92% est probablement gonflé** : la majorité des questions ciblent les 2 mêmes CVs. Un système qui retourne 5 chunks dont la plupart viennent des deux documents les plus indexés a de fortes chances de matcher par coïncidence.

### Impact qualité

- Impossible de savoir où le pipeline échoue réellement.
- Les optimisations ne peuvent pas être validées objectivement.
- Un domaine entier (agronomie) n'est pas testé du tout.

### Correction suggérée

1. Ajouter 20+ questions agronomiques (rendement, sols, climat, ONG terrain).
2. Ajouter des métriques de rang (MRR, NDCG@5).
3. Sauvegarder les résultats individuels dans `results.json` (`"results"` inclus).
4. Diversifier les types de documents : rapports, données chiffrées, tableaux, documents longs.

---

## Synthèse des 5 problèmes

| # | Sévérité | Problème | Fichier(s) | Ligne(s) | Impact RAG |
|---|----------|----------|------------|----------|------------|
| 1 | **CRITIQUE** | HyDE + Grep jamais exécutés (dead code) | `rag_engine.py`, `multi_search.py` | 643, 250, 312-318 | HyDE améliore le recall de +15-25% sur requêtes ambiguës — perte totale de cette capacité |
| 2 | **CRITIQUE** | Normalisation RRF dépendante du # de stratégies | `multi_search.py` | 132-140 | Scores incomparables, seuils de confiance invalides, rejets injustifiés |
| 3 | **MAJEUR** | Perte de structure tableaux DOCX | `ingestion.py` | 44-53 | Informations tabulaires décontextualisées, embeddings bruités |
| 4 | **MAJEUR** | Préfixe `[Doc - Section]` dans le contenu embarqué | `v2_chunking.py`, `chunking.py`, `ingestion.py` | 84, 138-154, 129-137 | Signal sémantique dilué, similarité artificielle entre chunks d'un même doc |
| 5 | **MINEUR** | Dataset d'évaluation trop petit / non-représentatif | `rag_eval_dataset.yaml`, `eval_rag.py` | 1-128, 148 | Recall@92% non fiable, pas de debug possible, domaine agronomie non testé |

---

## Analyse complémentaire

### Ce qui fonctionne bien

- Architecture `sqlite-vec + FTS5 + RRF` est solide conceptuellement
- Le batch embedding V10.3l (ingestion.py:127-132) améliore significativement les performances d'indexation
- La détection de profil par type de document (v2_chunking.py:105-111) est pertinente
- Le `semantic_dedup` par Jaccard (multi_search.py:155-191) est léger et efficace
- Le PromptGuard et la sanitization des requêtes (rag_engine.py:29-81) sont bien conçus

### Problèmes notables mais non retenus dans le TOP 5

- **IndexHealth** : comparaison basée sur `fname in indexed_sources` (index_health.py:126) — fragile si deux fichiers ont le même nom dans des répertoires différents.
- **STOP_WORDS dupliqués** : 3 copies différentes (query_rewriter.py:7, rag_engine.py:918, spotlight.py:28) — peut diverger.
- **Metadata search** toujours retourne des scores fixes décroissants 0.5, 0.4, 0.3... (multi_search.py:450) quel que soit le match réel.
- **Short_Doc_Threshold** (v2_chunking.py:31) à 2000 caractères : les documents courts ne sont pas chunkés du tout, perte de granularité possible.
- **Chunk date** toujours `""` puis remplacé par aujourd'hui (ingestion.py:139, rag_engine.py:997) — le freshness scoring est inopérant.
