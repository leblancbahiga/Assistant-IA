# NURU — Registre des problèmes actuels

> Document de référence créé le 6 août 2026 — session de stabilisation.
> Objectif : lister TOUS les problèmes rencontrés avec NURU, leur cause racine
> connue, leur statut, et la référence d'audit correspondante.
> 🔄 **Retour expert n°1 intégré le 8 août 2026** (R1 reformulé, R2 promu,
> R4 nuancé, R7 priorité absolue, R8 confirmé, R9 précisé, R11 ajouté,
> ordre de stabilisation revu).
> À mettre à jour après chaque fix (ne pas laisser ce registre vieillir).
>
> **USAGE** : ce document est destiné à être soumis à l'avis et à l'audit
> d'experts externes. La section 8 « Réflexions en cours » contient les
> hypothèses à valider — chaque entrée est formulée avec ses données,
> ses causes possibles et les questions ouvertes.

---

## 0. ÉTAT ACTUEL DE NURU (au moment de la rédaction)

- **LoRA RAG : DÉSACTIVÉ** (`config/settings.yaml` → `lora_adapter_enabled: false`)
  — le modèle base Phi-4-mini répond seul.
- **Modifications non commitées** (session en cours, à stabiliser) :
  - `src/config.py` — `local_max_tokens` 1024 → 2048
  - `src/llm_local.py` — SAMPLING_PROFILES (audit B-3) + plafonds RAM relevés
  - `src/kernel/pipeline_steps.py` — garde-fou evidence actif (régénération stricte)
  - `src/rag_engine.py` — keyword_rejection : noms propres comptés double
  - `src/routing/prompt_builder.py` — retrait « utilise tes connaissances » + « ne répète jamais deux fois la même phrase »
- **Process NURU : arrêté** (kill pendant la session de debug).
- Dernier commit stable : « fix: LoRA RAG desactive definitivement + rep_penalty 1.15 ».
- Référence durable des audits : `/Users/leblancbahiga/Downloads/audit/` (8 rapports, 17 650 lignes) — **À CONSULTER AVANT TOUT FIX**.

---

## 1. PROBLÈMES DE GÉNÉRATION / LLM

### P1. Hallucinations du modèle base (CRITIQUE — observé)
- **Symptôme** : question « expérience professionnelle de Leblanc Bahiga » → le modèle
  invente des postes et détails plausibles mais non sourcés (Equity BCDC, stratégie
  semencière FAO, PICAGL…), SANS citation [Source: …] (2859 chars, 64s).
- **Cause racine** : le prompt RAG contenait « Si le contexte ne contient pas
  l'information, utilise tes connaissances » → autorisation d'halluciner.
- **Statut** : prompt corrigé (retrait de l'échappatoire). À re-tester.
- **Référence** : audit _5 lignes 340-371 (prompt « Si tu ne sais pas, dis-le ») ;
  audit _6 ligne 1134 (« 80 % des hallucinations viennent du pipeline RAG »).
- **Règle du skill** : l'instruction RAG ne doit JAMAIS être absolue ni dans
  l'autre sens trop lâche — « utilise le contexte en priorité ».

### P2. Boucle de répétition (CRITIQUE — observé)
- **Symptôme** : « Il a une expérience dans la gestion de projet (suivi), l'évaluation
  des activités et le développement d'outils. » répété ~15× (modèle base, SANS LoRA).
- **Cause racine** : probablement sampling trop rigide (temp 0.3, rep_penalty 1.15)
  + prompt qui n'interdisait pas la répétition.
- **Statut** : SAMPLING_PROFILES de l'audit appliqués (RAG : temp 0.55, top_p 0.92,
  rep_penalty 1.05, min_p 0.05) + « Ne répète jamais deux fois la même phrase »
  ajouté au prompt. À re-tester.
- **Référence** : AUDIT_NURU_V16_V17 (1).md lignes 240-254 (B-3).

### P3. Réponses trop courtes (défaut historique)
- **Symptôme** : réponses de 2-3 phrases, citations coupées.
- **Cause racine** : `local_max_tokens: 1024` + throttling RAM dynamique
  (384/640 tokens sous 2 Go RAM) + prompt « concis ».
- **Statut** : `local_max_tokens` → 2048 ; plafonds RAM relevés à 1024/1536 ;
  prompt « concis » retiré (audit _5). À re-tester.
- **Référence** : audit _2 lignes 97-119 ; audit _5 ligne 350.

### P4. Meta-discours (symptôme historique — LoRA v1, corrigé)
- **Symptôme** : « La réponse doit s'appuyer exclusivement… », « Cet extrait fournit
  une base documentaire claire… » — 100 % des réponses ouvraient sur du meta.
- **Cause racine** : dataset LoRA v1 contaminé (généré par IA externe avec prompt
  strict → l'IA produisait du discours sur la réponse au lieu de la réponse).
- **Statut** : LoRA désactivé. Dataset v2 nettoyé (157+17 intros retirées) mais
  inutilisable (voir P5).

---

## 2. PROBLÈMES LoRA

### P5. LoRA v2 entraîné correctement mais inutilisable (DÉSACTIVÉ)
- **Symptôme** : loss 0.008/0.016 (excellent) mais boucle hallucinée à l'inférence :
  « ## DÉFINITIONS DISPONIBLES / Le sujet est limité au contexte… » × 30 (2555 chars,
  72s) — pattern ABSENT du dataset (0 occurrence grep).
- **Cause racine** : dataset v2 généré par templates (`build_nuru_dataset_v2.py`) :
  phrases fixes, `[Source: …]` après chaque phrase, 4 titres de section répétés 46×,
  phrases identiques dans 100 % des exemples → le LoRA a appris la STRUCTURE
  template et la régurgite en boucle. Val loss remonte après iter 450 (sur-apprentissage).
- **Statut** : désactivé définitivement (config), adapters conservés (réversibles).
- **Référence** : audit principal lignes 402-455 (dataset « long answers » 300-800 mots
  avec citations [Source X, p. Y] + negative examples pour rejection fine-tuning).

### P6. Aucun dataset LoRA fiable à ce jour
- v1 : contaminé (meta-discours) — abandonné.
- v2 : templates rigides (boucles) — désactivé.
- **Leçon** : un dataset LoRA doit contenir des réponses NATURELLES variées
  (pas de templates), avec citations espacées, ET un échantillon de refus.
- **Statut** : à décider — améliorer le générateur ou abandonner le LoRA.

---

## 3. PROBLÈMES RAG / PIPELINE

### P7. Faux refus « Je ne trouve pas cette information » (CRITIQUE — observé)
- **Symptôme** : question pertinente (« expérience professionnelle de Leblanc Bahiga »)
  → « Je ne trouve pas cette information dans les documents fournis. [Source: AUCUNE SOURCE] »
  alors que l'information EST indexée (la réponse id=941 la citait).
- **Cause racine (chaîne complète)** :
  1. `keyword_rejection` (config `rag_keyword_rejection: true`) : seuil 50 % durci
     (V17 : 30 % → 50 %) → requête avec nom propre « Leblanc Bahiga » : seuls
     2/5 mots-clés matchent (40 %) → REJET « hors-sujet » à tort.
  2. RAG vide → `FallbackGuard` remplace le contexte par le marqueur
     « AUCUNE SOURCE DOCUMENTAIRE PERTINENTE TROUVÉE ».
  3. Le LLM génère sans contexte → 0 citation → garde-fou evidence (P8) déclenché.
  4. Régénération stricte injecte le marqueur AUCUNE SOURCE comme contexte valide
     → échec garanti → refus final.
- **Statut** : corrigé — noms propres comptés double dans keyword_rejection
  (« Leblanc Bahiga » = 4/5 ≥ 50 %) + garde-fou ne régénère que si le contexte
  contient du vrai contenu. À re-tester.
- **Référence** : skill nuru-pipeline-layer-debugging (keywords ne doivent pas
  rejeter les noms propres).

### P8. Garde-fou evidence passif (corrigé en cours)
- **Symptôme** : le Validate détectait « ⚠️ Score évidence faible: 0.00 — Aucune
  citation » mais ne faisait QUE logger → l'hallucination passait à l'utilisateur.
- **Statut** : corrigé — si score < 0.3 et contexte réel disponible, régénération
  stricte (citation obligatoire) streamée vers l'UI ; sinon refus honnête.
  Service utilisé : `llm_generator` (PAS `llm_gen` — piège du registre kernel).
- **Référence** : skill nuru-pipeline-layer-debugging (services kernel != noms orchestrateur).

### P9. Couches de garde-fous contradictoires (STRUCTUREL — le vrai problème)
- **Symptôme** : keyword_rejection rejette ce que le RAG a trouvé ; FallbackGuard
  remplace le contexte par un marqueur ; evidence verifier refuse ce que le LLM
  a généré ; prompt_builder injecte le marqueur comme contexte valide.
  Personne ne décide en dernier → jeu de taupes systématique.
- **Cause racine** : le RAG est devenu un écosystème de garde-fous ajoutés les uns
  sur les autres (FactChecker, Query Rewriter, FallbackGuard, keyword_rejection,
  evidence verifier, self-consistency, LoRA…) sans hiérarchie de décision claire.
- **Statut** : OUVERT — décision de design à prendre (qui décide en dernier ?).
- **Référence** : audit _6 ligne 1198 (cause profonde n°1 : « Le RAG est utilisé
  comme moteur universel ») ; audit _2 ligne 78-91 (FactChecker coûteux).

### P10. Query Rewriter cloud systématique
- **Symptôme** : `Cloud Query Rewriting: '...' -> '...'` à chaque requête RAG
  (+2-5s, dépendance cloud même en local_only).
- **Statut** : OUVERT (non prioritaire).
- **Référence** : audit _2 lignes 60-70 (early stopping doit sauter les stratégies lourdes).

### P11. Session / cache contaminés
- **Symptôme** : les anciennes mauvaises réponses (refus, boucles) sont réinjectées
  dans l'historique de session → le modèle s'appuie dessus.
- **Statut** : OUVERT — purger `sessions.db` après stabilisation.
- **Référence** : skill nuru-pipeline-layer-debugging (clear session après fix).

---

## 4. PROBLÈMES PERFORMANCE / RESSOURCES (M1 8 Go)

### P12. RAM critique / thrash
- **Symptôme** : swap ~86 %, chargement modèle 5-10 min, 2 tok/s pendant les
  réponses longues, bascule cloud forcée à mi-génération (« RAM critique »).
- **Statut** : OUVERT — connu et documenté ; mitigé par RAMMonitor + force_cloud.
- **Référence** : mémoire projet (M1 8 Go, keep_alive MLX 30s, DocWatcher attend
  set_generating).

### P13. max_tokens cloud vs local
- `local_max_tokens` 1024 → 2048 (appliqué) ; `cloud_max_tokens` 4096.
- Attention : sur M1 8 Go, une réponse locale complète à 2048 tokens peut thrash —
  observer le compromis longueur vs vitesse après test.

---

## 5. PROBLÈMES DE PROCESS / OUTILLAGE (leçons de cette session)

### P14. Fix à l'aveugle sans consulter les audits
- **Symptôme** : j'ai corrigé rep_penalty 1.15 → 1.30 alors que l'audit recommande
  1.05 (profil RAG) — fix en sens INVERSE de la recommandation.
- **RÈGLE** : consulter `/Users/leblancbahiga/Downloads/audit/` AVANT tout fix NURU.
  Chaque fix doit être mappé à une ligne précise d'un rapport.

### P15. Tests à l'œil, pas de métriques
- Pas de définition de « bonne réponse » ni de benchmark de régression.
- Les audits proposent : hallucination score, précision citations (40-60 % → 75-90 %),
  longueur moyenne, temps au premier token.
- **Statut** : OUVERT — à définir si on continue sur la qualité des réponses.

### P16. Fichiers non commités / artefacts
- `.idea/workspace.xml` modifié (IDE — ne pas committer).
- `NURU_CODE_CONCATENATED.txt` créé à la racine (artefact d'analyse — à supprimer
  ou déplacer).
- `data/adapters/rag/` dans .gitignore (voulu) — datasets/adapters non commités.

---

## 6. DÉCISIONS EN ATTENTE

1. **LoRA** : améliorer le générateur de dataset (réponses naturelles, sources
   espacées, refus variés) OU abandonner définitivement ?
2. **Hiérarchie de décision RAG** (P9) : qui décide en dernier qu'une réponse est
   bonne — le RAG, le garde-fou, ou le LLM ?
3. **Périmètre** : stabiliser l'existant OU refonte ciblée du RAG (séparation
   Router/Search/Generation, audit _6) OU accepter les limites et passer à l'UI ?
4. **Benchmark** : définir un mini-jeu de 10 questions de référence pour mesurer
   les régressions après chaque fix.

---

## 7. RÉFLEXIONS EN COURS (pour avis d'experts)

> Session du 6 août 2026 — phase de réflexion. AUCUNE action n'a été prise sur
> ces points ; ils sont consignés pour être soumis à des experts externes.

### R1. Hypothèse : le problème d'hallucination vient du LLM local, pas (seulement) du RAG ou du LoRA

> 🔄 **RÉVISÉ après retour expert n°1 (8 août 2026)** : la formulation initiale
> donnait trop de poids au benchmark HHEM. Formulation robuste retenue :
> **« Phi-4-mini pourrait AMPLIFIER les hallucinations d'un pipeline imparfait,
> mais rien ne démontre encore qu'il en soit la cause principale. »**
> Justification de l'expert : HHEM mesure un modèle dans des conditions standardisées
> (benchmark isolé), alors que NURU est un système complet (RAG + prompt + retriever +
> reranker + context builder + validator + fallback + history + session + mémoire +
> RAM + MLX + sampling). Les deux ne sont pas comparables : remplacer Phi par Qwen
> demain, avec un reranker qui continue d'envoyer les mauvais chunks, produira
> toujours des hallucinations — simplement différentes.

**Contexte observé** :
- Modèle local actuel : `mlx-community/Phi-4-mini-instruct-4bit` (config/settings.yaml:13).
- Phi-4-mini répond correctement quand le contexte RAG est bon (réponse id=941, sourcée, parfaite),
  mais hallucine des détails plausibles (postes Equity BCDC, FAO, ENABEL) quand le contexte est
  faible ou absent, et boucle sur des phrases répétitives.
- Le LoRA RAG (v1 contaminé, v2 templates) a été tour à tour accusé, entraîné, désactivé.
  Question : et si la source commune des hallucinations était le LLM lui-même ?

**Données vérifiées le 6 août 2026** (leaderboard Vectara HHEM — hallucination rate sur
résumé de documents, la métrique pertinente pour du RAG ; mis à jour 11 mai 2026) :

| Modèle | HHEM (hallucination) | Empreinte RAM (4-bit) | MLX dispo |
|---|---|---|---|
| Phi-4-mini-instruct (ACTUEL) | **23,5 %** | ~2,5 Go | oui |
| Qwen3-4B | **5,7 %** | ~2,5 Go | oui (vérifié HTTP 200) |
| Gemma 3-4B-it | 6,4 % | ~2,5 Go | oui |
| Qwen3.5-4B | 10,5 % (régression) | multimodale | oui |

**Lecture** : Phi-4-mini a un score MMLU élevé (~70 %, « connaissances ») mais un taux
d'hallucination documentaire ~4× pire que les modèles de sa classe. C'est cohérent avec
le symptôme : le modèle sait des choses, mais invente quand il doit s'ancrer sur des documents.
Référence technique complète : skill `mlx-local-llm` → `references/model-selection-m1.md`
(compilé le 21 juin 2026 à partir d'un audit des hallucinations Phi-4-mini de NURU — le
problème était déjà documenté avant cette session).

**Les audits NURU convergent** :
- AUDIT_NURU_V16_V17 (1).md:398 : défaut recommandé = Qwen2.5-3B-Instruct-4bit (ou Phi-4-mini)
- AUDIT_NURU_V16_V17 (1).md:1209 (F-1) : « local_model = 1.5B trop petit → Qwen2.5-3B »
- AUDIT_NURU_V16_V17 (1).md:447 : base du LoRA = Qwen2.5-3B

**Questions ouvertes pour les experts** :
1. Le HHEM 23,5 % vs 5,7 % justifie-t-il à lui seul un changement de modèle, ou le
   pipeline (prompt, garde-fous) explique-t-il une part mesurable des hallucinations ?
2. Qwen3-4B est-il le meilleur choix pour M1 8 Go (RAG text-only, français), ou un autre
   modèle de la classe 3-4B est-il supérieur (Gemma 3-4B, autres) ?
3. Risque du changement : le template de prompt change (Phi-4 → ChatML Qwen). Le code
   utilise `apply_chat_template` — vérifier la compatibilité avant bascule.
4. Le LoRA reste-t-il pertinent si le modèle de base change (un LoRA entraîné sur Phi-4
   n'est pas transférable) ?

**Aucune décision prise** — options : (a) garder Phi-4-mini, (b) basculer Qwen3-4B,
(c) A/B avant/après sur 10 questions de référence (voir P15).

---

### R2. Le jeu de taupes : chaque fix en crée un autre (réflexion structurelle) — ⭐ LE CŒUR DU DOCUMENT

> 🆕 **RETOUR EXPERT n°1 (8 août 2026)** : « C'est LE cœur du document. Il mérite
> de passer en première position — il explique quasiment tous les autres problèmes. »
> L'expert pousse la formulation plus loin : il ne s'agit pas seulement d'un « jeu
> de taupes », mais d'une **« absence d'architecture de gouvernance »** : retriever →
> keyword rejection → fallback → prompt → validator → fact checker → LoRA → LLM —
> **personne ne décide, donc chacun corrige le précédent.**

**Constat** : en une session, la chaîne de correctifs suivante a été observée :
LoRA v1 contaminé → désactivé → dataset v2 → LoRA réactivé → boucle de répétition →
LoRA désactivé → hallucinations du modèle base → garde-fou evidence → faux refus
« je ne trouve pas » → keyword_rejection 50 % trop strict → (fix en cours)…

**Hypothèse** : ce n'est pas une série de bugs isolés, c'est l'absence de HIÉRARCHIE DE
DÉCISION dans le pipeline. Cinq couches de garde-fous coexistent sans arbitre final :
keyword_rejection, FallbackGuard, prompt_builder, evidence verifier, FactChecker.
Chacune peut rejeter/remplacer/refuser le travail des autres.

**Questions ouvertes pour les experts** :
1. Quelle est la bonne architecture de décision pour un RAG local sur M1 8 Go ?
   (une seule autorité de décision ? un ordre strict de garde-fous ?)
2. Faut-il privilégier « refuser plutôt qu'halluciner » (comportement actuel) ou
   « tenter avec le contexte disponible » ?
3. Le FallbackGuard qui remplace le contexte par un marqueur « AUCUNE SOURCE » est-il
   une bonne pratique ? (il a causé un faux refus en cascade)

---

### R3. Pas de définition de « bonne réponse » ni de benchmark (réflexion méthodologique)

**Constat** : toutes les évaluations se font à l'œil, une question à la fois.
Aucune métrique de régression n'existe : on ne peut pas dire si un fix améliore ou
dégrade la qualité globale.

**Propositions à valider par les experts** :
1. Constituer un mini-benchmark de 10 questions de référence (5 RAG réelles, 3 pièges
   hors-sujet, 2 questions de mémoire utilisateur) avec réponses attendues.
2. Métriques : précision des citations (audit : 40-60 % → objectif 75-90 %), taux de
   refus inutiles, longueur, temps.
3. Mesurer avant/après chaque changement de modèle ou de prompt.

---

### R4. La lenteur « inexpliquée » du pipeline — décomposition de 50,86s (réflexion kernel)

> ⚠️ **NUANCE après retour expert n°1 (8 août 2026)** : le thrash RAM comme
> « cause commune des hallucinations » est une **HYPOTHÈSE, pas une conclusion**.
> Le thrash explique très bien les répétitions, la lenteur et les timeouts — mais
> pas forcément toutes les hallucinations. **Il faudra des tests A/B** (R3) pour
> le démontrer. Conserver la prudence : thrash = facteur aggravant avéré ;
> cause des hallucinations = à mesurer.

**Contexte** : le kernel centralise tout (7 steps, PipelineEngine, KernelMetrics, cache 5 régions),
pourtant une requête RAG simple prend 50,86s. Réflexion : où partent réellement les secondes ?

**Décomposition réelle (log 13:35:19 → 13:36:10, requête « expérience professionnelle de Leblanc Bahiga »)** :

| Étape | Durée | Observation |
|---|---|---|
| Route | 0,0s | instantané (routeur sémantique, 0 LLM) ✅ |
| **Cloud Query Rewriting** | **+3,4s** | appel cloud à CHAQUE requête RAG, même en local_only |
| **Rechargement embedder** | **+6,2s** | l'embedder avait été déchargé par RAMMonitor (ping-pong, voir R5) |
| RAG retrieval + rejet keyword | +1,3s | rejeté à tort (P7) |
| **Chargement du modèle LLM** | **+3,5s** | lazy-load au premier generate |
| **Génération locale** | **+32,2s** | 52 tokens = **1,6 tok/s** (au lieu de ~12 tok/s attendus) ← LE GOUFFRE |
| Validate + régénération cloud | +8s | bascule cloud forcée (RAM critique) |

**Total : 50,86s** — dont ~80 % hors du contrôle réel du kernel (chargements + thrash).

**Trois découvertes pour les experts** :

1. **Le LLM local thrash sous pression RAM (1,6 tok/s)** : le skill mlx-local-llm documente ce
   phénomène — « swap > 85 % → le modèle perd la cohérence attentionnelle, produit des boucles
   de répétition et des artefacts ». **Hypothèse forte : le thrash RAM est la cause racine COMMUNE
   des boucles (P2) ET d'une partie des hallucinations (P1)** — le modèle n'est pas seulement
   « mauvais », il tourne depuis le swap.
2. **Le ping-pong embedder ↔ LLM** : RAMMonitor décharge l'embedder (~400 Mo) quand le LLM se
   charge (pression RAM) ; la requête suivante le recharge (+6s) ; le LLM se charge à son tour ;
   l'embedder est re-déchargé… Chaque requête paie un rechargement. Le kernel devait coordonner
   ces chargements — visiblement la coordination ne tient pas.
3. **Le mode « local_only » n'est pas vraiment local** : Cloud Query Rewriting à chaque requête
   (+3,4s), FallbackGuard → cloud, régénération → cloud. Des appels cloud cachés persistent.

**Données brutes (logs du 6 août 2026)** :
- `13:35:22 Cloud Query Rewriting: '...' -> 'Leblanc Bahiga expérience professionnelle parcours carrière emplois'`
- `13:35:33 Embedder déchargé (RAMMonitor) — libère ~400 Mo` (PENDANT le chargement du LLM)
- `13:36:02 ✅ Généré: 52 tokens en 32.2s (2 tok/s) | model=` ← `model=` VIDE (bug de visibilité, voir R6)
- `13:36:02 ☁️ RAM critique (swap/ram) — bascule cloud forcée`

**Question ouverte pour les experts** :
1. Sur M1 8 Go, un LLM 4-bit (~2,5 Go) + embedder (~400 Mo) + reranker + UI PySide6 + macOS :
   est-il réaliste de tout garder en mémoire, ou faut-il accepter le ping-pong (avec cache d'embedding
   persistant pour ne pas re-encoder) ?
2. Le chargement lazy du LLM à la PREMIÈRE requête (+3,5s, parfois 5-10 min selon la mémoire) ne
   devrait-il pas être fait au boot, en arrière-plan, pendant que l'UI est utilisable ?
3. Un cache d'embedding persistant (sqlite) éviterait-il de re-encoder 630 fichiers à chaque
   déchargement/rechargement ?

---

### R5. Le ping-pong embedder ↔ LLM : la coordination RAM ne tient pas (réflexion kernel)

**Constat** : le kernel a un RAMBudgetManager (politiques 60/70/80/90 %) + KernelResources +
cache 5 régions. Pourtant les logs montrent l'embedder déchargé PENDANT le chargement du LLM
(13:35:33), puis rechargé à la requête suivante (+6,2s).

**Hypothèse** : les politiques de déchargement sont déclenchées par la pression RAM brute
(psutil), pas par une connaissance des MODÈLES en cours d'utilisation. Le kernel ne sait pas
que « l'embedder vient d'être utilisé pour cette requête et va resservir » → il le décharge
au profit du LLM, qui thrash quand même (1,6 tok/s).

**Question pour les experts** :
1. Faut-il un ordre de priorité de déchargement explicite (LLM > embedder > reranker) avec
   interdiction de décharger un modèle utilisé dans les N dernières secondes ?
2. Le rechargement lazy est-il acceptable si le cache d'embeddings est persistant (pas de
   re-encodage) ?

---

### R6. Visibilité : le pipeline mesure tout mais ne loggue rien d'utile (réflexion outillage)

**Constat** :
- `ctx.step_timings` est collecté par step (pipeline.py:248) mais seul le TOTAL est loggé
  (« 🏁 Pipeline terminé: 50.86s ») — impossible de voir quel step a coûté 32s.
- `model=` est VIDE dans « ✅ Généré: 52 tokens en 32.2s | model= » : `last_model` n'existe
  pas sur llm_generator (getattr → ''), on ne sait même pas QUEL chemin a généré.
- Sans ces deux données, toute réflexion sur la lenteur est aveugle — on vient de le
  découvrir en recomposant les timestamps à la main.

**Proposition pour les experts** : logger `step_timings` dans le résumé pipeline
(1 ligne JSON par requête : {route: 0.0, retrieve: 7.5, generate: 32.2, validate: 8.0})
+ fixer `last_model`. Coût : ~5 lignes. Gain : toute future optimisation devient mesurable.

---

### R7. Embedder et Reranker : le maillon cassé de la chaîne française (réflexion RAG) — 🚨 PRIORITÉ ABSOLUE

> 🆕 **RETOUR EXPERT n°1 (8 août 2026)** : « R7 est probablement SOUS-ESTIMÉ.
> Un reranker anglais sur un corpus français, c'est une ERREUR ARCHITECTURALE.
> Le retriever peut retrouver le bon chunk, puis le reranker le déclasser — le LLM
> ne le verra jamais. Et tu accuseras ensuite Phi, le prompt, le LoRA, alors que
> le problème est survenu AVANT la génération. » → **L'expert recommande de mettre
> R7 dans les priorités absolues.**

**Question posée** : l'embedder et le reranker sont-ils configurés pour le français ?
Sont-ils à la base de la mauvaise qualité des réponses ?

**Audit des 3 maillons de langue de la chaîne RAG (vérifié dans le code le 6 août 2026) :**

| Maillon | Modèle réel | Français ? | Verdict |
|---|---|---|---|
| **Embedder** | `mlx-community/Qwen3-Embedding-0.6B-4bit-DWQ` (log 13:35:28) | ✅ 100+ langues (doc officielle : « Support over 100 languages », MTEB No.1 au 5 juin 2025) | OK |
| **BM25 / FTS5** | `unicode61 remove_diacritics` (rag_engine.py:432, V17.2) | ✅ corrigé — l'audit F-3/B-4 signalait `porter` (stemmer ANGLAIS, +200-400 % de rappel perdu) ; la migration one-shot est dans le code | OK |
| **Reranker** | `cross-encoder/ms-marco-MiniLM-L-6-v2` (config.py:72) | ❌ **EN-only** — entraîné sur MS MARCO (anglais) | **CASSÉ** |

**Le problème** : le reranker décide de l'ORDRE des 15 candidats → les 3-5 meilleurs
sont envoyés au LLM. Un modèle entraîné uniquement sur l'anglais qui reranke des chunks
français produit un classement aberrant : les bons chunks peuvent être relégués en fin de
liste et JAMAIS vus par le LLM → le LLM n'a pas l'information → hallucination (il compense)
ou refus (P7). Le commentaire dans config.py:72 dit « reranker multilingue pas dispo » —
**c'est FAUX** : `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` existe (vérifié HTTP 200,
entraîné sur mMARCO, multilingue, ~470 Mo, même famille architecture).

**Impact estimé** : c'est probablement UNE des causes de la mauvaise qualité des réponses
RAG françaises — le reranker est un filtre qui détruit de l'information AVANT le LLM.
Chaque requête : retrieval correct (embedder multilingue) → réordonnancement erroné
(reranker EN) → mauvais contexte → hallucination/refus.

**Questions pour les experts** :
1. Basculer sur `mmarco-mMiniLMv2-L12-H384-v1` (multilingue) est-il le bon choix, ou un
   reranker MLX natif (Qwen3-Reranker-0.6B) est-il disponible/supérieur ?
2. Le reranker actuel est-il même activé (seuils `_rerank_min_score=0.40`, `_rerank_max_score=0.75`,
   `_can_rerank`) ? Un reranker cassé mais désactivé coûte 0 ; activé, il coûte 400 Mo + 300 ms
   ET dégrade.
3. L'embedder 0.6B 4-bit est-il suffisant pour du français, ou un bge-m3 / Qwen3-Embedding-4B
   améliorerait-il le retrieval (au prix de la RAM) ?

---

### R8. Pourquoi NURU consomme autant de RAM — et ce n'est PAS l'UI (réflexion ressources)

> ✅ **CONFIRMATION après retour expert n°1 (8 août 2026)** : « Ton analyse mémoire
> est juste. Ce qui m'intéresse surtout : le budget RAM est calculé sur la RAM
> totale — ça, si c'est vrai, explique énormément de comportements. »
> → Le point `hard=6.0 Go` fixe (config) est bien calculé sur la RAM TOTALE (8 Go),
> pas sur la RAM DISPONIBLE (~1,5 Go constaté au boot).

**Question posée** : la RAM de NURU est très haute sans rien avoir ajouté vs les versions
précédentes « plus économes ». Est-ce le LLM local ? l'UI PySide6 ? Quelle en est la cause ?

**Réponse courte : ni l'UI, ni un ajout récent — c'est le trio (LLM local + PyTorch/reranker
+ budget RAM mal calibré), sur une machine déjà saturée.**

**Fait n°1 — la machine est saturée AVANT NURU** (log du 6 août 13:32:12) :
`🧠 Mémoire système : 8.00 Go total | 1.49 Go disponible au départ`
→ macOS + apps = **~6,5 Go déjà consommés avant le moindre chargement NURU**.
À l'instant où NURU charge SON premier modèle, il ne reste plus que 1,5 Go de marge.

**Fait n°2 — le budget RAM de NURU est calibré pour une machine VIDE** :
`RAMBudgetManager initialisé (hard=6.0 Go, soft=5.0 Go)` (log 13:32:11).
NURU croit disposer de 6 Go sur 8 — il n'en a réellement que ~1,5. Les politiques de
déchargement (60/70/80/90 %) se déclenchent donc TOUJOURS trop tard → swap massif → thrash
(1,6 tok/s mesuré, R4). Le commentaire `V16 FIX : 6.0 Go max sur 8 Go (macOS ~2 Go)` est
FAUX : macOS + apps prennent ~6,5 Go, pas 2.

**Fait n°3 — qui consomme quoi (estimation footprint, M1 8 Go) :**

| Composant | Footprint | Techno | Coupable ? |
|---|---|---|---|
| **LLM local** Phi-4-mini 4-bit | **~2,5 Go** | MLX | ⚠️ le plus gros, incompressible en local |
| **Reranker** ms-marco + **PyTorch** | **~2 Go** (torch + sentence_transformers !) | **PyTorch, PAS MLX** | 🔴 chargé/déchargé à CHAQUE requête RAG |
| Embedder Qwen3-Embedding-0.6B | ~400 Mo | MLX | 🟡 ping-pong (R5) |
| **UI PySide6 + Python** | ~300-500 Mo | Qt | ✅ PAS le coupable |
| faster-whisper (STT) | ~500 Mo si actif | CTranslate2 | selon usage |

**Le reranker est le seul composant PyTorch** (`from sentence_transformers import CrossEncoder;
import torch` — reranker.py:52-53) : importer torch + sentence_transformers coûte ~1,5-2 Go de
footprint à lui seul, AVANT même de charger le modèle. Et il est chargé/déchargé à chaque
requête RAG (mémoire : « Reranker charge/decharge a chaque requete RAG ») → le pic RAM
pendant une requête = LLM 2,5 + reranker/torch 2 + embedder 0,4 = **~5 Go sur 1,5 disponible** →
swap garanti.

**Fait n°4 — pourquoi les versions précédentes étaient plus économes :**
le cache HF montre les anciens modèles : `Qwen2.5-1.5B-Instruct-4bit` (~1 Go) et
`Qwen2.5-0.5B-Instruct-4bit`. Le passage à Phi-4-mini (2 Go sur disque, ~2,5 Go en RAM)
a ajouté ~1,5 Go. Et le reranker PyTorch n'était peut-être pas chargé systématiquement avant.

**Pépite découverte dans le cache HF** : des alternatives multilingues SONT DÉJÀ téléchargées
mais NON utilisées :
- `models--jinaai--jina-reranker-v2-base-multilingual` (reranker multilingue PyTorch)
- `models--mlx-community--Qwen3-Reranker-0.6B-mxfp8` (reranker **MLX natif** — pas de PyTorch !)
- `models--mlx-community--Qwen3-Embedding-0.6B-4bit-DWQ` (embedder actuel, MLX)
- `models--mlx-community--Qwen3.5-2B-4bit`, `gemma-3-4b-it-4bit` (candidats LLM testés)

**Conclusion pour les experts** :
1. Le vrai coupable de la RAM = LLM local + **PyTorch/reranker**, PAS l'UI PySide6.
2. Le budget `hard=6.0` est irréaliste : il devrait être calculé sur la RAM DISPONIBLE
   (1,5 Go !) au lieu de la RAM totale, sinon les politiques de déchargement sont inopérantes.
3. Passer le reranker sur **Qwen3-Reranker-0.6B MLX** (déjà en cache !) éliminerait ~1,5-2 Go
   de PyTorch ET serait multilingue (résout aussi R7).
4. Question : faut-il re-mesurer avec le « footprint » (pas RSS) comme métrique fiable
   (mémoire : « footprint (pas RSS) = mesure fiable ») avant toute décision ?

**Questions pour les experts** :
1. Le remplacement reranker PyTorch → MLX (Qwen3-Reranker-0.6B) est-il sans risque ?
2. Le budget RAM devrait-il être dynamique (% de RAM dispo) plutôt que fixe (6 Go) ?
3. Faut-il décharger le LLM local quand l'intent est SIMPLE/GENERAL (pas de RAG) pour
   libérer 2,5 Go entre les requêtes ?

---

### R9. L'intelligence de NURU est « inexistante » — comparaison honnête avec Hermes/OpenClaw (réflexion stratégique)

> 🆕 **RETOUR EXPERT n°1 (8 août 2026)** : « C'est la réflexion la plus stratégique.
> Hermes n'est pas seulement un chatbot, c'est un agent. Le LLM n'est probablement
> pas la différence majeure — la BOUCLE DE RAISONNEMENT l'est. »
> ⚠️ **Désaccord de l'expert sur un point** : « Tu sembles parfois raisonner comme
> si plus d'intelligence = plus de fonctionnalités. C'est faux. Pour l'utilisateur,
> INTELLIGENCE = le système fait la bonne chose — peu importe 2, 15 ou 0 agents.
> Si ton pipeline actuel répond juste, l'utilisateur dira "NURU est intelligent". »

**Constat de l'utilisateur (6 août 2026)** : « NURU n'utilise pas bien l'exploitation des
documents de ma machine, il ne réfléchit pas. C'est plus facile d'utiliser Hermes ou OpenClaw
avec un LLM local qui sont plus intelligents. L'intelligence est notre argument marketing. »

**Ce que NURU fait RÉELLEMENT aujourd'hui (vérifié dans le code) :**
- Pipeline **fixe à une passe** : ReceiveQuestion → Route → Retrieve → BuildContext → Generate
  → Validate → Respond. Question entrée → réponse sortie. **Aucune boucle agentique** (pas de
  `while`/itération multi-tours dans pipeline_steps.py — seule exception : 1 retry du Validator).
- **Aucun outil d'action** : WebResearcher (`research/web.py`) est un agrégateur passif
  (score/dedup/filter), pas un agent qui lit une page, extrait, vérifie.
- CoT réservé à COMPLEX, ToT/Self-Consistency = flags, pas de vraie planification.
- La mémoire (episodic/semantic/procedural) existe dans le code… mais le pipeline ne l'utilise
  pas pour raisonner — elle alimente le contexte, sans boucle de réflexion.

**Comparaison factuelle :**

| Capacité | NURU | Hermes / OpenClaw + LLM local |
|---|---|---|
| Boucle agentique (réfléchir → agir → observer → itérer) | ❌ une passe | ✅ oui |
| Outils d'action (terminal, fichiers, web, code) | ❌ aucun | ✅ oui |
| Exploitation des documents locaux | 🟡 RAG cassé (R7, P7) | ✅ lecture directe + raisonnement |
| Planification multi-étapes | ❌ non | ✅ oui |
| Skills/routines réutilisables | ❌ non | ✅ oui |
| UI native macOS verre morphique | ✅ | ❌ (chat/terminal) |
| 100 % local / confidentialité | ✅ | 🟡 local possible (MLX) |
| Mémoire inter-sessions | 🟡 existe mais passive | ✅ active |

**Lecture honnête :** NURU est un **chatbot RAG à une passe**, pas un agent. Hermes/OpenClaw
sont des **agents** : ils itèrent, agissent, se corrigent. Avec le MÊME LLM local, un agent
« paraît plus intelligent » car il peut tenter plusieurs fois, lire la sortie, s'adapter —
alors que NURU ne peut qu'espérer que la première génération soit bonne.

**L'argument marketing « intelligence » est intenable tant que NURU n'a ni boucle ni outils.**

**Questions stratégiques pour les experts (et pour nous) :**
1. **Positionnement** : NURU doit-il devenir un AGENT (boucle + outils + planification), ou
   assumer un positionnement différent (assistant local privé, UI native, exploitation de
   documents SANS être un agent généraliste) ?
2. **Architecture** : si agent, le kernel actuel est-il la bonne base ? (PipelineEngine 7 steps
   → boucle Agent-Critic ? Router 5-bucket → planification ?)
3. **Réalisme M1 8 Go** : une boucle agentique avec LLM local à 1,6 tok/s (R4) prendrait
   plusieurs minutes par étape. Un agent sur 8 Go est-il viable, ou faut-il un LLM cloud
   pour l'agenticité et le local uniquement pour le RAG ?
4. **Comparaison honnête** : qu'est-ce qui JUSTIFIE NURU face à Hermes/OpenClaw ? (UI native ?
   RAG profond sur ses documents ? voix ? zéro dépendance cloud ?) — il faut choisir UNE
   réponse, sinon NURU n'a pas de raison d'être.
5. **Quick win immédiat (indépendant de la stratégie)** : si le RAG marchait correctement
   (reranker multilingue R7 + hiérarchie de décision R2 + pas de thrash R4), NURU répondrait-il
   « intelligent » sur SA spécialité (les documents de l'utilisateur) ? La perception
   « inutile » vient peut-être surtout des 6 problèmes P1-P9 non résolus, pas d'un défaut
   fondamental.

**Aucune décision prise** — consigné pour l'audit d'experts et la décision de positionnement.

---

### R10. La vision initiale vs la réalité — les 6 promesses non tenues (réflexion produit)

**La vision de départ (rappelée par l'utilisateur le 6 août 2026)** : NURU devait
1. **Réfléchir avant de répondre** et donner une réponse bonne
2. **Modifier des fichiers** sur l'ordinateur
3. **Parler**
4. **Naviguer sur internet**
5. **Se rappeler des conversations**
6. **S'améliorer**

**Ce que le code contient RÉELLEMENT (vérifié dans le code le 6 août 2026) :**

| Promesse | Dans le code ? | Connecté au chat ? | Verdict |
|---|---|---|---|
| 1. Réfléchir | CoT/ToT/Self-Consistency existent (`pipeline_steps.py:417-437, 577`) | 🟡 CoT réservé à COMPLEX, ToT = mots-clés manuels, SC = flag | **une passe, pas de vraie boucle** |
| 2. Modifier des fichiers | **`src/tools/` COMPLET** : `shell_exec.py`, `os_control.py`, `file_ops.py`, `memory_tools.py`, `document.py` + `ToolRegistry` | ❌ **ZÉRO appel depuis kernel/, orchestration/, nuru_core.py** — utilisés SEULEMENT par `ui/components/tool_tester.py` | 🔴 **le moteur existe, la transmission n'existe pas** |
| 3. Parler | TTS/STT présents (nuru_core, runtime_manager) | ❌ audit : « 2 moteurs vocaux parallèles + 4 backends STT/TTS + dépendances introuvables + conflit `say` français » | 🔴 cassé |
| 4. Naviguer internet | `web_context` dans Retrieve (`pipeline_steps.py:277-291`), WebResearcher (`research/web.py`) | 🟡 agrégateur passif (score/dedup), pas de lecture/extraction | 🟡 limité |
| 5. Se rappeler | session_store (24 messages, anaphore, `pipeline_steps.py:45-46`) | ✅ court terme OK ; mémoire LTM (episodic/semantic) passive | 🟡 |
| 6. S'améliorer | rien de connecté (feedback_page = UI seule) | ❌ | 🔴 absent |

**LA découverte centrale** : `src/tools/` est une bibliothèque d'outils complète
(ShellExec, OSControl, FileOps, MemoryTools, DocumentGenerator — avec ToolRegistry,
ToolDefinition, ToolParameter) **qui n'est branchée sur RIEN**. Seul `tool_tester.py`
(une page UI de test) les utilise. C'est comme un moteur sans transmission : tout le
potentiel « agent » est là, dans le code, inerte.

**Pourquoi ?** (hypothèses à valider par les experts) :
1. Le kernel a centralisé le PIPELINE (Route→RAG→Generate) mais personne n'a branché les
   TOOLS sur Generate — le LLM ne peut pas appeler d'outil, il ne peut que générer du texte.
2. Pas de tool-calling dans le prompt de génération (BuildContext n'injecte pas la liste
   des outils disponibles).
3. La priorité a été mise sur le RAG (documents) — l'argument marketing — au détriment
   des actions ; mais le RAG est cassé (R7), donc NURU n'a NI actions NI bons documents.

**Questions pour les experts** :
1. Le LLM local (Phi-4-mini 4-bit) supporte-t-il le tool-calling (function calling) ?
   Si non, un agent d'action nécessite-t-il le cloud, ou un schéma « outils → commandes
   JSON → exécuteur local » (sans LLM natif tool-calling) ?
2. Le ToolRegistry existant est-il la bonne fondation pour un step « Act » dans le
   pipeline (8e step) ? Ou faut-il une architecture Agent-Critic ?
3. Ordre de priorité proposé : (a) réparer le RAG → NURU répond bien sur les documents,
   (b) brancher les tools → NURU agit, (c) TTS → NURU parle. Lequel d'abord ?

---

### R11. NURU essaie-t-il de résoudre trop de problèmes ? (réflexion de l'expert n°1 — 8 août 2026)

> 🆕 **Ajouté sur proposition de l'expert n°1** : « Il manque une réflexion encore
> plus fondamentale : NURU essaie-t-il de résoudre trop de problèmes ? »
> Aujourd'hui NURU veut être : un RAG, un agent, un assistant personnel, un IDE,
> un éditeur, un moteur vocal, une mémoire, un navigateur, un système de plugins,
> un orchestrateur, un copilote, un shell, un gestionnaire documentaire, un
> assistant macOS…
> **Chaque nouvelle capacité ajoute de la RAM, de la complexité, des garde-fous,
> des dépendances, des interactions imprévues.**
> Suggestion : se demander sérieusement si l'architecture ne gagnerait pas à être
> **recentrée autour d'une promesse unique**.

**Lecture complémentaire (assistant)** : cette observation recoupe R9 (l'utilisateur
trouve NURU inutile face à Hermes/OpenClaw) ET R10 (les 6 promesses non tenues —
réfléchir, agir, parler, naviguer, se souvenir, s'améliorer). Le trait d'union entre
les trois : **NURU a accumulé des capacités (kernel, tools, TTS, mémoire, web, plugins)
sans jamais en finir une seule**. Un produit recentré sur UNE promesse (ex. : « mon
assistant qui connaît mes documents ») aurait :
- moins de RAM consommée (R8) — pas de TTS/plugins/browser à maintenir
- moins de garde-fous contradictoires (R2) — une seule chaîne de décision
- moins de dépendances cassées (R10) — la voix en est l'exemple type

**Questions pour les experts (complément) :**
1. Quelle promesse unique recommanderiez-vous pour NURU, sachant la contrainte M1 8 Go
   et l'audience (agronome/informaticien, chaînes de valeur Afrique) ?
2. Faut-il COUPER des capacités existantes (TTS, plugins, browser) pour recentrer,
   ou seulement ne plus en ajouter ?
3. Le recentrage est-il compatible avec l'argument marketing « intelligence »
   (R9) — ou faut-il changer l'argument ?

---

## 8. ORDRE DE STABILISATION SUGGÉRÉ (étape par étape)

> 🔄 **REVU après retour expert n°1 (8 août 2026)** — priorités ajustées :
> 1. **R7 (reranker anglais) — PRIORITÉ ABSOLUE** : erreur architecturale, problème
>    survenu AVANT la génération. Un reranker multilingue (Qwen3-Reranker-0.6B MLX,
>    déjà en cache) corrige la qualité du contexte.
> 2. **R2 (gouvernance)** : une seule autorité de décision — le cœur, qui explique
>    les autres problèmes.
> 3. **R3 (benchmark automatique)** : indispensable pour TOUT valider (A/B).
>    « Je pose une question → ça paraît mieux → je commit » n'est pas une méthode.
> 4. **R8/R4 (RAM)** : budget sur RAM disponible, pas totale + tests A/B sur le
>    lien thrash↔hallucinations (hypothèse à confirmer).
> 5. **R1 (LLM)** : Phi = amplificateur possible, PAS cause démontrée. Réévaluer
>    seulement APRÈS R7+R2 (un reranker cassé rend tout autre test invalide).
>
> (L'ordre initial ci-dessous est conservé pour traçabilité.)

1. Re-tester la question « expérience professionnelle de Leblanc Bahiga » avec les
   fixes en cours (P1, P2, P7, P8) → valider ou ajuster.
2. Commit de l'état stabilisé.
3. Purgersession / cache (P11).
4. Décider P9 (hiérarchie) — LA décision structurante.
5. Décider P6 (LoRA) et P15 (benchmark) selon la direction choisie.
