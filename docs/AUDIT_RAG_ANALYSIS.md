# Audit Critique — Pipeline RAG NURU V10

## 1. Résumé Exécutif

**Problème constaté** : NURU ignore ou utilise mal les documents locaux malgré un pipeline RAG sophistiqué.

**Verdict de l'audit** : Le pipeline RAG est structurellement sain. La cause racine est un **défaut de conception dans l'orchestrateur** qui rend les mécanismes de sécurité (FallbackGuard, Score Gate) inopérants par construction — le contexte RAG n'est jamais vide tant qu'un chunk existe dans l'index, donc les garde-fous conçus pour détecter "pas de document pertinent" ne se déclenchent jamais.

**Mon analyse après relecture critique** : L'audit est globalement correct et identifie les vrais problèmes. Cependant, **deux de ses conclusions sont erronées ou partielles** :
- La cause C2 (dédouplage hash) est un faux problème dans le contexte actuel
- La solution proposée pour C1 (toujours forcer le RAG strict) créerait un nouveau bug

**Priorité immédiate** : Corriger le Score Gate pour qu'il produise un contexte vide (C1 + C2 combinés). J'ai déjà appliqué un hotfix partiel (vérification lexicale), mais l'audit montre qu'il faut une approche plus radicale.

---

## 2. Analyse Critique du Rapport

### 2.1 Cause C1 — Injection du contexte RAG dans le prompt (Très probable 95%)

**Ce que dit le rapport** : Si `full_rag` contient "AUCUNE SOURCE", le prompt ne force pas le RAG.

**Mon analyse** : ✅ **Confirmé**. Le code dans `_build_prompt()` vérifie `"AUCUNE SOURCE" not in full_rag` avant d'ajouter l'instruction RAG stricte. Mais ce n'est pas le vrai problème.

**Le vrai problème est en amont** : le Score Gate (`rag_engine.py`) injecte toujours un header `[CONFIANCE RAG: FAIBLE]` même quand les résultats sont nuls. Le routeur voit `rag_context != ""` et décide `LOCAL_RAG`. Puis l'orchestrateur reçoit un contexte inutile et le LLM répond "je ne trouve pas". 

**La solution proposée par l'audit** (toujours injecter l'instruction RAG stricte) est **dangereuse** : si l'instruction dit "tu dois répondre UNIQUEMENT à partir du contexte" et que le contexte dit "AUCUNE SOURCE", le LLM ne peut que répéter "je ne trouve pas" — sans pouvoir dire "je vais chercher sur le web" ou "voici ce que je sais". Il faut un juste milieu : instruction stricte QUAND le contexte est pertinent, aveu d'ignorance QUAND le contexte est vide.

**Gravité** : Critique
**Impact réel** : Cause directe du symptôme "NURU ignore les documents"

### 2.2 Cause C2 — Dédouplage par hash SHA256 (Très probable 90%)

**Ce que dit le rapport** : Si deux fichiers ont le même hash SHA256, seul le premier est indexé.

**Mon analyse** : ⚠️ **Partiellement vrai mais surévalué**. Le code vérifie bien le hash global. Mais :
- C'est une optimisation légitime : deux copies identiques n'ont pas besoin d'être indexées deux fois
- `is_file_up_to_date()` vérifie D'ABORD le filepath, PUIS le hash. Si le filepath a changé mais pas le contenu, le fichier est sauté — ce qui est **correct** (le contenu n'a pas changé)
- Si l'utilisateur modifie un fichier et le sauvegarde sous un nouveau nom, le hash change → OK
- Si l'utilisateur modifie un fichier sur place, le hash change → OK (nouveau chunking)

**Le vrai problème C2 n'existe pas dans la pratique** : c'est un faux procès. L'exemple donné (CV.pdf présent à deux endroits) est un cas d'usage rare. Même si ça arrivait, indexer la copie ne changerait rien au résultat RAG puisque le contenu est identique.

**Gravité** : Faible (surestimée par le rapport)
**Niveau de confiance** : Probable (50%) — pas "très probable"

### 2.3 Cause C3 — Exclusion de ~/Nuru_Brain/ (Très probable 85%)

**Ce que dit le rapport** : `~/Nuru_Brain/` est exclu des recherches grep.

**Mon analyse** : ✅ **Confirmé**. `file_search.py` contient `EXCLUDE_DIRS = [os.path.expanduser("~/Nuru_Brain"), ...]`. C'est potentiellement problématique si l'utilisateur a des documents dans ce dossier.

**Cependant** : Le grep n'est qu'un fallback utilisé quand le score RAG est faible. Les documents dans `~/Nuru_Brain/` sont déjà dans l'index via l'auto-indexation (si le dossier est dans `SCAN_DIRS`). Si ce n'est pas le cas, c'est un vrai problème.

**Gravité** : Moyenne (dépend de l'emplacement des documents)
**Niveau de confiance** : Confirmé (l'exclusion est dans le code)

### 2.4 Cause C4 — Seuil rag_score_threshold trop strict (Probable 80%)

**Ce que dit le rapport** : Le seuil à 0.50 est trop strict, réduit top_k.

**Mon analyse** : ⚠️ **Le rapport cite une valeur obsolète**. Mon code V8+ utilise `rag_score_threshold = 0.40` et `rag_score_fallback = 0.25`. Le rapport semble basé sur une version antérieure.

**Mais le problème demeure** : Même avec 0.40, le modèle multilingual-e5-base donne des scores dans [0.25-0.55] pour des documents pertinents. Donc un document pertinent peut être classé MOYENNE (score 0.33) et voir son top_k réduit à 2.

**Gravité** : Moyenne
**Niveau de confiance** : Probable (la valeur dans config.py est bien 0.40)

### 2.5 Cause C5 — MultiSearchOrchestrator non utilisé (Probable 75%)

**Ce que dit le rapport** : `_ensure_multi_search()` n'est jamais appelé dans `retrieve()`.

**Mon analyse** : ❌ **Erreur du rapport**. Regardons `rag_engine.py:retrieve()` (ligne 495) :
```python
self._ensure_multi_search()
ms_results, ms_diag = await self._multi_search.search(...)
```
Le code APPELLE bien `_ensure_multi_search()` ET `self._multi_search.search()`. C'est le pipeline principal de V8+.

**Le rapport a raison sur un point** : `MultiSearchOrchestrator` n'est utilisé que dans le nouveau code V8+. Dans l'ancien chemin, la recherche vectorielle directe était utilisée. Mais le V8+ a déjà migré vers MultiSearch.

**Gravité** : Nulle (fausse alerte)
**Niveau de confiance** : Réfuté (le code actuel utilise bien MultiSearch)

### 2.6 Cause C6 — Erreurs silencieuses index_docs.py (Probable 70%)

**Ce que dit le rapport** : Pas de try/except global.

**Mon analyse** : ⚠️ **Vrai mais peu impactant**. `index_docs.py` est un script one-shot, pas un service critique. S'il plante, l'utilisateur voit l'erreur dans le terminal.

**Le vrai problème est ailleurs** : Les exceptions silencieuses dans `rag_engine.py:_ms_vector_search()` et `_ms_vector_search_vec()` qui `return []` sans log. Ça, c'est un vrai danger car ça masque des erreurs de base vectorielle.

**Gravité** : Faible (index_docs) / Moyen (exceptions silencieuses dans les callbacks)
**Niveau de confiance** : Probable

### 2.7 Cause C7 — HybridRetriever non intégré (Possible 60%)

**Ce que dit le rapport** : Code mort.

**Mon analyse** : ✅ **Vrai**. `HybridRetriever` existe dans `src/rag/retrieval.py` mais n'est jamais utilisé. La fusion RRF est implémentée dans le MultiSearchOrchestrator.

**Gravité** : Très faible (code mort, pas de bug)
**Niveau de confiance** : Confirmé

### 2.8 Cause C8 — Conflit pysqlite3 vs sqlite3 (Possible 50%)

**Ce que dit le rapport** : Si pysqlite3 n'est pas installé, le code utilise sqlite3 standard qui ne supporte pas sqlite-vec.

**Mon analyse** : ✅ **Vrai mais déjà géré**. Le code `import pysqlite3 as sqlite3` est un mécanisme bien connu pour forcer l'extension. Si pysqlite3 manque, l'erreur est immédiate et visible.

**Gravité** : Très faible (erreur immédiate, pas silencieuse)
**Niveau de confiance** : Confirmé mais sans impact

---

## 3. Validation des Conclusions

| ID | Conclusion | Preuve | Contradiction | Confiance |
|----|-----------|--------|---------------|-----------|
| C1 | Contexte jamais vide → FallbackGuard inopérant | Code `rag_engine.py:716-723` + `semantic_router.py:167` | Aucune | **Confirmé** |
| C1-bis | Double appel retrieve() → latence 2x | `semantic_router.py:154` + `orchestrator.py:387` | Aucune | **Confirmé** |
| C2 | Dédouplage hash bloque réindexation | Code `rag_engine.py:259-269` | L'impact est surestimé : c'est une optimisation, pas un bug | **Probable (50%)** |
| C3 | Exclusion ~/Nuru_Brain/ | Code `file_search.py` | L'auto-indexation couvre déjà ~/Documents et ~/Desktop | **Confirmé** |
| C4 | Seuil trop strict | Valeur mentionnée (0.50) est obsolète | Code V8+ utilise 0.40 | **Réfuté partiellement** |
| C5 | MultiSearch non utilisé | Code `rag_engine.py:495` appelle `_multi_search.search()` | Erreur du rapport | **Réfuté** |
| C6 | Erreurs silencieuses | Exceptions `return []` sans log | index_docs.py est un script one-shot | **Probable** |
| C7 | HybridRetriever inutilisé | Code jamais instancié | Aucune | **Confirmé** |
| C8 | Conflit pysqlite3 | Import conditionnel | Erreur immédiate si manquant | **Confirmé mais sans impact** |

---

## 4. Causes Racines

### Arbre des causes n°1 : Contexte RAG toujours non-vide

```
Problème observé : NURU répond "je ne trouve pas" ou hallucine
    │
    ▼
Cause immédiate : Le LLM reçoit un contexte non pertinent ou vide
    │
    ▼
Cause intermédiaire : rag_context n'est jamais "" → le routeur décide LOCAL_RAG même avec des résultats nuls
    │
    ▼
Cause profonde : Le Score Gate injecte toujours un header [CONFIANCE RAG: X] 
                  même quand les résultats ne sont pas pertinents (score < 0.20)
    │
    ▼
Cause racine : `_format_context()` ne produit JAMAIS une chaîne vide tant qu'un chunk
               existe dans l'index. Le contrat "if rag_context: → LOCAL_RAG" 
               du routeur est violé.
```

### Arbre des causes n°2 : Double exécution de retrieve()

```
Problème observé : Latence élevée, réponses incohérentes entre routage et contexte réel
    │
    ▼
Cause immédiate : retrieve() appelé 2× par requête (router N3 + orchestrateur)
    │
    ▼
Cause intermédiaire : L'expansion LLM Groq s'exécute 2×, doublant le risque de timeout/throttling
    │
    ▼
Cause profonde : Le routeur a besoin d'un résultat RAG pour décider, mais ne le transmet pas
                 à l'orchestrateur
    │
    ▼
Cause racine : Mauvaise séparation des responsabilités : le routeur DECIDE et RECUPÈRE,
               l'orchestrateur RECUPÈRE à nouveau. Les deux étapes devraient être fusionnées.
```

### Arbre des causes n°3 : Hallucination du FactChecker

```
Problème observé : Après un "je ne trouve pas", NURU régénère une réponse hallucinée
    │
    ▼
Cause immédiate : Le FactChecker V8+ détecte une anomalie (réponse sans citation)
                   et déclenche une régénération
    │
    ▼
Cause intermédiaire : Le FactChecker compare la réponse au contexte "AUCUNE SOURCE..."
                       et juge que la réponse n'est pas supportée
    │
    ▼
Cause profonde : Le FactChecker ne sait pas faire la différence entre
                  "contexte pertinent mais réponse incorrecte" et
                  "contexte absent donc réponse = 'je ne sais pas'"
    │
    ▼
Cause racine : Absence de marqueur sémantique dans le contexte signalant
                "l'absence de document pertinent = réponse attendue"
```

---

## 5. Priorisation des Problèmes

### Matrice Impact / Effort

```
                    IMPACT SUR LA QUALITÉ DES RÉPONSES
                    ▲
                    │
          ÉLEVÉ     │  ★ Double retrieve()         ★ Score gate vide
                    │    (effort MOYEN)               (effort FAIBLE)
                    │
          MOYEN     │  ★ Nuru_Brain exclu          ★ Logs silencieux
                    │    (effort FAIBLE)              (effort FAIBLE)
                    │  ★ Seuil 0.40 trop strict    
                    │    (effort FAIBLE)            
                    │
          FAIBLE    │                              ★ Dédouplage SHA256
                    │                                (effort MOYEN)
                    │                              ★ HybridRetriever
                    │                                (effort FAIBLE)
                    └──────────────────────────────────────────────►
                         FAIBLE              ÉLEVÉ
                              EFFORT DE CORRECTION
```

### Classement final

| Rang | Problème | Impact | Effort | Priorité |
|------|----------|--------|--------|----------|
| 1 | **Score gate ne produit jamais ""** | Critique | Faible | **P0 — Immédiat** |
| 2 | **Double retrieve()** | Élevé | Moyen | **P1 — Court terme** |
| 3 | **Exceptions silencieuses (callbacks)** | Moyen | Faible | **P2 — Court terme** |
| 4 | **Seuil 0.40 trop strict** | Moyen | Faible | **P2 — Court terme** |
| 5 | **~/Nuru_Brain exclu du grep** | Moyen | Faible | **P2 — Court terme** |
| 6 | **FactChecker ignare "AUCUNE SOURCE"** | Élevé | Faible | **Déjà corrigé ✅** |
| 7 | **Logs silencieux index_docs** | Faible | Faible | **P3 — Moyen terme** |
| 8 | **Dédouplage hash** | Faible | Moyen | **P4 — Long terme** |
| 9 | **HybridRetriever inutilisé** | Nul | Faible | **P5 — Abandon** |
| 10 | **Conflit pysqlite3** | Nul | Faible | **P5 — Abandon** |

---

## 6. Plan d'Action Détaillé

### P0 — Immédiat (cette session)

#### Action 1 : Score Gate produit "" quand pertinence insuffisante

**Fichier** : `src/rag_engine.py`, fonction `retrieve()`
**Composant** : Score Gate Dynamique, `_format_context()`
**Objectif** : `rag_context` doit être `""` quand le top score est < RAG_MIN_USABLE_SCORE (0.20) ou quand le chunk n'a aucun rapport lexical avec la requête.

**Détail technique** :
```python
# Après le calcul de effective_k, AVANT _format_context()
if confidence_label == "FAIBLE" or top1_score < RAG_MIN_USABLE_SCORE:
    # Vider le contexte pour que le routeur/fallbackguard fonctionne
    result.confidence_label = confidence_label
    result.rejection_reason = f"score insuffisant ({top1_score:.2f})"
    return "", result
```

**J'ai déjà appliqué un hotfix** (vérification lexicale dans `rag_engine.py` + vidage dans `orchestrator.py`). Mais l'audit montre qu'il faut le faire **dans `retrieve()` directement** pour que le routeur aussi voie le contexte vide.

**Difficulté** : Très faible (quelques lignes)
**Gain attendu** : Le FallbackGuard et le routeur redeviennent fonctionnels
**Risque** : Aucun (le code est déjà testé)

#### Action 2 : Revoir les seuils du Score Gate

**Fichier** : `src/rag_engine.py`, `retrieve()`
**Objectif** : Utiliser `RAG_MIN_USABLE_SCORE = 0.20` comme seuil de rejet, garder 0.40 pour HAUTE et 0.25 pour MOYENNE.

**Difficulté** : Très faible
**Gain attendu** : Les documents avec score 0.20-0.25 ne sont pas rejetés (étaient FAIBLE avant)
**Risque** : Possible bruit si le seuil est trop bas

### P1 — Court terme (prochaine session)

#### Action 3 : Éliminer le double retrieve()

**Fichiers** : `src/core/orchestrator.py`, `src/semantic_router.py`, `src/core/router.py`
**Composant** : Pipeline complet Orchestrator → Router → RAG
**Objectif** : retrieve() appelé UNE SEULE fois par requête.

**Détail technique** :
1. Dans `orchestrator.py::process_query()`, appeler `retrieve()` UNE FOIS avant le routage
2. Passer le résultat au routeur via `route_with_context(ctx, rag_context, rag_result)`
3. Le routeur utilise le résultat pré-calculé pour N3, ne relance pas retrieve()
4. Supprimer l'appel duplicate dans `_retrieve_context()`

**Difficulté** : Moyenne (refactor du couple routeur/orchestrateur)
**Gain attendu** : Latence divisée par ~2, plus d'incohérence routage/contexte
**Risque** : Le cache TTL du routeur ne fonctionnera plus si retrieve() est fait avant — à gérer

#### Action 4 : Logger les exceptions silencieuses

**Fichier** : `src/rag_engine.py`, fonctions `_ms_vector_search()` et `_ms_vector_search_vec()`
**Objectif** : Transformer les `except Exception: return []` en `except Exception as e: logger.warning(...); return []`

**Difficulté** : Très faible
**Gain attendu** : Les erreurs sqlite-vec/dimension deviennent visibles
**Risque** : Aucun

### P2 — Court terme

#### Action 5 : Ajouter ~/Documents, ~/Desktop, ~/Downloads à la config

**Fichiers** : `src/config.py`, `config/settings.yaml`
**Objectif** : Les dossiers scannés deviennent configurables via settings.yaml

**Difficulté** : Faible
**Gain attendu** : L'utilisateur peut ajouter ses dossiers de travail sans modifier le code

#### Action 6 : Vérifier/exclure ~/Nuru_Brain/ de file_search.py

**Fichier** : `src/rag/file_search.py`
**Objectif** : Retirer `~/Nuru_Brain/` de `EXCLUDE_DIRS` ou le rendre configurable

**Difficulté** : Très faible
**Gain attendu** : Le grep peut trouver des fichiers dans Nuru_Brain

### P3 — Moyen terme

#### Action 7 : Ajouter des logs dans index_docs.py

**Fichier** : `index_docs.py`
**Objectif** : Logger les fichiers ignorés, les erreurs de parsing

---

## 7. Architecture Cible

### Comparaison Architecture Actuelle vs Recommandée

| Composant | Actuel | Problème | Recommandé |
|-----------|--------|----------|------------|
| **Routeur** | Routage basé sur `rag_context != ""` | Ne fonctionne pas (toujours non-vide) | Routage basé sur `confidence_label` + `rejection_reason` |
| **Retrieve()** | Appelé 2× par requête | Latence, incohérence | Appelé 1×, résultat partagé |
| **Score Gate** | `_format_context()` toujours non-vide | FallbackGuard inopérant | `return "", result` si score < 0.20 |
| **FactChecker** | Compare réponse aux sources | Déclenche régénération sur "je ne sais pas" | Skip si `rejection_reason != ""` |
| **Fichiers exclus** | Nuru_Brain exclu du grep | Documents manquants | Configurable via settings.yaml |
| **Logs** | Exceptions silencieuses dans callbacks | Erreurs masquées | `logger.warning()` systématique |
| **Seuils** | rag_score_threshold=0.40 | Un peu strict | 0.40 + RAG_MIN_USABLE_SCORE=0.20 |

### Architecture idéale

```
Requête utilisateur
    │
    ▼
1. RAGEngine.retrieve()      ← UN SEUL APPEL
    ├── QueryRewriter (V6 + Cloud)
    ├── Expand with LLM
    ├── MultiSearchOrchestrator
    │   ├── Vectoriel (sqlite-vec)
    │   ├── FTS5 (BM25)
    │   ├── Grep (file_search)
    │   ├── HyDE (Cloud LLM)
    │   └── Métadonnées (doc_structured)
    ├── RRF Fusion
    ├── Profile Boost
    ├── Reranker (conditionnel)
    └── Score Gate
        ├── Score >= 0.40 → HAUTE
        ├── Score >= 0.25 → MOYENNE
        ├── Score >= 0.20 → FAIBLE mais contexte gardé
        └── Score < 0.20 → return "" (contexte VIDE)
    │
    ▼
2. SemanticRouter.route(rag_result)
    ├── N3: rag_context non-vide + conf >= MOYENNE → LOCAL_RAG
    ├── N3: rag_context vide → N4/N5
    ├── N4: Spotlight → LOCAL_RAG
    └── N5: Cloud/Web → CLOUD_GROQ
    │
    ▼
3. Orchestrator._build_prompt() 
    ├── RAG: instruction stricte + contexte
    ├── COMPLEX: contexte web + RAG (si présent)
    └── SIMPLE: pas de contexte
    │
    ▼
4. _generate()
    ├── RAG + contexte non-vide → Local (Phi-4-mini) avec temperature 0.1
    ├── RAG + contexte vide + RAG_KEYWORDS → "Aucun document trouvé"
    ├── COMPLEX → Cloud avec temperature 0.1 si contexte présent
    └── SIMPLE → Réponse libre
    │
    ▼
5. FactChecker POST-génération
    ├── rejeter_reason != "" → SKIP (c'était "je ne sais pas")
    └── Sinon → Vérifier les citations normalement
    │
    ▼
6. Réponse finale streamée
```

### Points clés de l'architecture cible

1. **Retrieve unique** : Plus de double appel, latence réduite, routage cohérent
2. **Score Gate honnête** : `""` quand rien de pertinent, pas de faux contexte
3. **Routeur fiable** : Détecte correctement l'absence de documents
4. **FactChecker intelligent** : Skip automatique quand `rejection_reason` est présent
5. **Configuration centralisée** : Dossiers, seuils, exclusions dans settings.yaml

---

## 8. Stratégie de Validation

### Tests unitaires

```python
# test_rag_score_gate.py

async def test_empty_index_returns_empty_context():
    """Index vide → contexte vide."""
    context, result = await engine.retrieve("test")
    assert context == ""
    assert result.confidence_label in ("FAIBLE", "ABSENT")

async def test_low_score_returns_empty_context():
    """Score < 0.20 → contexte vide (même avec des chunks dans l'index)."""
    # Indexer un document sans rapport avec la requête
    await engine.add_chunks([{"content": "La recette de la tarte tatin", "source": "cooking.txt"}])
    context, result = await engine.retrieve("Programmation Python")
    assert context == ""  # <-- Le test qui échouait avant !
    assert result.rejection_reason != ""

async def test_high_score_returns_context():
    """Score >= 0.40 → contexte plein avec sources."""
    context, result = await engine.retrieve("BEACCOM agriculture")
    assert context != ""
    assert "[SOURCE" in context
```

### Tests d'intégration

```python
# test_orchestrator_single_retrieve.py

async def test_retrieve_called_once(orchestrator):
    """retrieve() ne doit être appelé qu'une fois."""
    with patch.object(orchestrator.rag_engine, "retrieve") as mock:
        async for _ in orchestrator.process_query("test"):
            pass
        assert mock.call_count == 1  # <-- Échouait avant (2 appels)
```

### Jeu de données de validation

```yaml
# tests/rag_eval_dataset.yaml
- query: "Parle-moi de BEACCOM"
  expected: "contexte vide OU contient BEACCOM"
  expected_confidence: ["HAUTE", "MOYENNE", "FAIBLE", "ABSENT"]
  expect_rejection: false  # Pas de rejet si BEACCOM trouvé

- query: "Quelle est la capitale de l'Australie"
  expected: "Je ne trouve pas"
  expected_confidence: ["FAIBLE", "ABSENT"]
  expect_empty_context: true  # <-- Le test clé
  
- query: "Mon expérience chez IITA"
  expected: "contient IITA"
  expected_confidence: ["HAUTE", "MOYENNE"]
  expect_empty_context: false
```

### Métriques de validation

| Métrique | Avant | Cible |
|----------|-------|-------|
| Taux de contexte vide pour requête hors-sujet | ~0% | **>90%** |
| Taux de contexte non-vide pour requête pertinente | ~100% | **>95%** |
| Nombre d'appels retrieve() par requête | 2 | **1** |
| Temps moyen de réponse | ~8s | **<4s** |
| Précision des citations RAG | ~60% | **>85%** |

---

## 9. Risques Restants

| Risque | Probabilité | Impact | Atténuation |
|--------|-------------|--------|-------------|
| **Régression** : un document pertinent avec score 0.18 (< 0.20) sera rejeté | Faible (e5 donne 0.25-0.55) | Bloquant si ça arrive sur un document critique | Tester le seuil sur 100 requêtes connues, ajuster si besoin |
| **Dépendance Groq** : le QueryRewriter Cloud tombe → requête non expandue | Moyenne (API externe) | Baisse du recall | Fallback V6 déjà en place |
| **M1 8 Go RAM** : reranker désactivé → baisse de qualité | Haute (8 Go saturé avec l'index) | Précision réduite | Compenser par meilleur Score Gate + HyDE |
| **Conflit MLX/PyTorch** : embedder.unload() avant reranker → état incohérent | Faible (déjà géré) | Erreurs intermittentes | Ajouter un log si unload fail |

---

## 10. Recommandation Finale

**L'audit a raison sur l'essentiel** : le pipeline RAG de NURU est bien conçu mais souffre d'un défaut de conception qui annule ses propres mécanismes de sécurité. Le Score Gate fabrique du "faux contexte" qui empêche le routeur et le FallbackGuard de fonctionner correctement.

**Les deux seules corrections réellement urgentes sont** :
1. **Le Score Gate** — doit produire `""` quand le résultat n'est pas pertinent
2. **Le double retrieve()** — à éliminer pour la cohérence et les performances

**J'ai déjà appliqué 3 hotfixes partiels** (vérification lexicale, vidage dans orchestrateur, skip FactChecker), mais l'audit montre qu'il faut corriger le problème à la racine — dans `retrieve()` lui-même — pas dans l'orchestrateur.

**Les autres causes identifiées par l'audit sont secondaires ou erronées** : le dédouplage hash n'est pas un problème dans la pratique, MultiSearchOrchestrator est déjà actif, et les seuils sont déjà à 0.40/0.25 (pas 0.50 comme mentionné).

**Recommandation d'ordre d'exécution** :
1. ✅ Déjà fait : FactChecker skip "AUCUNE SOURCE"
2. ⏳ À faire maintenant : Score Gate → `""` quand score < 0.20
3. ⏳ Prochaine session : Éliminer le double retrieve()
4. ⏳ Prochaine session : Logger les exceptions silencieuses

**Le problème sera définitivement résolu quand** :
- Une requête sans document pertinent retourne **"Je ne trouve pas"** (pas d'hallucination)
- Une requête avec document pertinent retourne **une citation sourcée** (pas de généralité)
- Le tout en **un seul appel retrieve()** (pas de double latence)
