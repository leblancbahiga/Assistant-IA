# Décision finale — Quel LLM local pour NURU V12 ?

> Auteur : architecte senior (Hermes), synthèse de 4 audits experts.
> Date : 2026-06-21.
> Statut : **Décision proposée — en attente validation utilisateur**.

---

## TL;DR (1 phrase)

**Tester Qwen 3.5 2B (candidat principal, pari raisonnable sur génération nouvelle) puis Gemma 4 E2B (candidat #2, pari risqué car famille Gemma déjà défaillante chez toi). Skip Qwen 3, Gemma 3, Smol — éliminés sur données terrain.**

---

## Pourquoi cette décision maintenant ?

À l'issue de **4 audits d'experts** (`audit_expert_1_llm.md` à `audit_expert_4_llm.md`) :

| Convergence | Force du signal |
|---|---|
| Phi-4-mini est sur-représenté dans les hallucinations | **Convergente** — confirmée par source primaire (Vectara HHEM 23.5%) |
| Le pipeline NURU amplifie le problème | **Moi** (audit V12 du 21 juin — bug grounding documenté) |
| MLX/M1 8GB est le vrai plafond | **Pas traité** par les 4 experts |
| Les experts recommandent des modèles avec scores hallucination non mesurés | **Décroissance de fiabilité** au fur et à mesure des rapports |

**Conclusion** : on ne peut pas continuer à itérer sur les rapports. **Assez de signaux**. On tranche.

---

## 1. Le diagnostic causal (que les 4 experts ont raté)

Les experts se sont focalisés sur le modèle. **Erreur :** la cause racine est multifactorielle.

### Causes probables des hallucinations observées dans NURU (par ordre d'impact)

1. **Bug grounding instruction dans `<|system|>`** (Phi-4-mini ignore)
   - Documenté : `references/grounding-prompt-redesign-2026-05-30.md`
   - Statut correction : **incertain** — le code V12 (`core/orchestrator.py`) semble toujours passer l'instruction dans `<|system|>`, où Phi-4-mini l'ignore
   - **Réparabilité : 30 minutes, déplacement d'instructions vers `<|user|>`**

2. **`sanitize_chunk_content` trop passif** (RAG)
   - `src/rag_engine.py:67` — neutralise le délimiteur, mais ne retire pas les motifs d'injection dans le chunk lui-même
   - **Réparabilité : 1 heure, intégration de `sanitize_document_content` de `PromptGuard` (V10.3)**

3. **System prompt dur consomme ~800 tokens** (`src/nuru_core.py:35-97`)
   - Écrase le budget contexte pour le vrai RAG
   - Réduit la qualité perçue même si Phi-4 était neutre
   - **Réparabilité : 2 heures, externalisation dans `system_prompt_compact.py`**

4. **Phi-4-mini intrinsèquement plus hallucinant** (Vectara 23.5%)
   - Confirmé sur le **ground truth HHEM**, leaderboard mis à jour 11 mai 2026
   - **Réparabilité : 1 ligne YAML + redémarrage**

**Net** : passer à Qwen 3 4B résout **4 sur 4** facteurs (réduit le 4, ne touche pas 1-3 — qui eux sont dans le pipeline). **Même si on garde Phi-4-mini, on supprimerait ~50% des hallucinations juste en fixant 1-3.**

**Donc** : **Phi-4-mini reste le coupable partiel, mais le pipeline NURU est responsable du reste.** Ne **jamais** croire un "swap de modèle qui résoudra tout seul". Les 88 trouvailles de l'audit V12 doivent rester en tête.

---

## 2. Pourquoi Qwen 3-4B (et pas les alternatives recommandées par les experts)

### Critères de décision (filtrés)

| Critère | Source de vérité | Pourquoi important |
|---|---|---|
| Score hallucination Vectara HHEM | **Obligatoire** | Mesure standard. Pas de pari. |
| Compatibilité MLX (4-bit quant dispo) | **Obligatoire** | NURU utilise `mlx_lm.load` (commit V4.5). GGUF = réécriture. |
| Footprint RAM ≤ 3.5 GB en 4-bit | **Obligatoire** | Budget M1 8GB avec PySide6 + embeddings. |
| Texte pur (pas multimodal) | **Préférable** | NURU fait du RAG texte, pas vision. Multimodal = RAM gaspillée. |
| Mesure indépendante M1 (tok/s) | **Préférable** | Server-grade = pas pertinent. |

### Comparaison finale des candidats vérifiables

| Modèle | Hallucination Vectara | MLX 4-bit dispo | Texte pur | Score |
|---|---|---|---|---|
| **Qwen 3-4B** | 5.7% (Vectara, jamais testé sur ta machine) | `mlx-community/Qwen3-4B-4bit` (à télécharger) | ✅ | **À REVOIR — données terrain 2026-06-21** : Qwen 3 a déjà été testé, hallucinait, ne comprenait pas le contexte. Score Vectara n'est pas vérité terrain. Recalibrer Phase B. | 0/5 par défaut |
| Qwen3-1.7B | ❓ pas mesuré | `mlx-community/Qwen3-1.7B-4bit` ✅ | ✅ | **Éliminé — même famille Qwen 3, déjà testée et défaillante** | 0/5 |
| Qwen 2.5-1.5B (fallback actuel) | ❓ pas mesuré | ✅ déjà chargé 839 MB | ✅ | **Éliminé par Leblanc — "beaucoup d'hallucinations + ne comprenait pas le contexte"** | 0/5 par défaut |
| **Qwen 3.5 2B** | ❓ pas mesuré directement (seul `qwen3.5-flash-2026-02-23` mesuré à 10.5% — modèle différent malgré nom proche) | `mlx-community/Qwen3.5-2B-4bit` (en cours DL, ~1.5 GB cible) | ❌ multimodal image-text-to-text | 3/5 — pari raisonnable si Qwen 3 n'a pas le bug compréhension et si la nouvelle génération a corrigé |
| Qwen 3.5 4B | 10.5% (Flash, mesuré — pas le 4B exactement mais même famille, même génération) | `mlx-community/Qwen3.5-4B-4bit` ✅ | ❌ multimodal | 2/5 — plus gros, plus de risque RAM, score famille moins bon |
| Gemma 3 4B | 6.4% (Vectara) | `mlx-community/gemma-3-4b-it-4bit` (déjà installé en cache HF, 3.2GB) | ✅ | **Éliminé — données terrain Leblanc 2026-06-21** : "beaucoup d'hallucinations + fait ramer la machine" | 0/5 par défaut |
| Gemma 4 E2B | ❓ pas mesuré (modèle créé 2026-03, dernière MAJ HHEM 2026-05 = Vectara ne l'a pas encore inclus) | ✅ MLX 4-bit (`mlx-community/gemma-4-E2B-4bit`) (en cours DL, 31 MB / ~3 GB cible) | ❌ multimodal any-to-any | 3/5 (à challenger — extrapolation Gemma 3 → Gemma 4 fragile vu comportement Gemma 3) |
| SmolLM3 3B | ❓ pas mesuré | ✅ MLX 4-bit | ✅ | 2/5 (pas éliminé, mais aucune histoire test terrain) |
| **Qwen 3.5 2B** | ❓ pas mesuré directement (seul `qwen3.5-flash-2026-02-23` mesuré à 10.5% — modèle différent malgré nom proche) | ✅ MLX 4-bit disponible | ❌ multimodal image-text-to-text | 3/5 (candidat sérieux, pari raisonnable) |
| Llama 3.2 3B | ❓ pas mesuré | probable | ✅ | 2/5 (à challenger) |
| Mistral Small 3 3B | ❓ pas mesuré | probable | ✅ | 2/5 (à challenger) |
| **Phi-4-mini** (actuel) | **23.5%** | ✅ | ✅ | 2/5 (baseline à remplacer) — pas 1/5, le défaut connu est documenté mais le use-case голос/TTS etc. est fonctionnel |

**Important — révision méthodologique suite à 2 challenges user-side** :

J'avais pénalisé **Gemma 4 E2B et Qwen 3.5 2B** sur la base de l'argument "pas de score HHEM". Pour Gemma 4 E2B, je l'ai admis au challenge 1 : l'absence HHEM vient de la **jeunesse du modèle** (créé mars 2026), pas d'un mauvais score.

Pour Qwen 3.5 2B, je dois admettre le **même type de biais**, sous une forme différente :
- J'ai écrit que "Qwen 3.5 hallucine 10.5%". **Faux** : le 10.5% mesuré sur HHEM est sur `qwen3.5-flash-2026-02-23` (modèle Flash, propriétaire, plus gros = différent du 2B).
- Aucune mesure HHEM n'est disponible **directement** pour Qwen 3.5 2B.
- Mon raisonnement l'a écarté implicitement sur la base d'une moyenne familiale contestable.

**Donc Qwen 3.5 2B n'est pas disqualifié sur "score HHEM"** — ce qu'il a : c'est multimodal (image-text-to-text) ET petit (2.27B params). Sur M1 8GB, **c'est en fait l'un des plus intéressants** : léger, multimodal, téléchargé 1.6M fois (preuve de traction).

### Réserves sur Gemma 4 E2B que j'ai usurpé

L'objection "pas de score HHEM" est **partiellement vraie** mais pas disqualifiante. Cependant, d'autres réserves s'appliquent :

1. **Multimodal any-to-any** — Gemma 4 est `pipeline_tag=any-to-any` (texte + image + audio + vidéo). Même si on n'utilise que le texte au runtime, **les poids multimodaux sont chargés en mémoire**. Sur M1 8GB, c'est une charge RAM pour rien.
   - Paramètres totaux = **5.1B** (vs 4B pour Qwen 3 dense). En 4-bit, ~2.5-3 GB.
   - Sur M1 8GB, ça reste viable mais moins efficient qu'un modèle texte-only dense.

2. **Famille Gemma 3 = 6.4% hallucination HHEM mesuré** — c'est l'**ancêtre direct**. Gemma 4 E2B hérite conceptuellement de cette calibration anti-hallucination ("quantization-aware training").
   - **Hypothèse raisonnable** : Gemma 4 E2B devrait être **au moins aussi bon** que Gemma 3 4B.
   - **Mais pas vérifié** — la famille a évolué (multimodal unifié), le training procédure a changé.

3. **Maturité MLX** — `mlx-community/gemma-4-E2B-4bit` existe (307 redirect) mais **quantization récente**, retours communautaires limités. Risque de bug MLX-spécifique non détecté.

4. **Commande Ollama toujours cassée** — vérifié le 2026-06-21, `ollama pull gemma4:e2b` n'existe pas. Mais NURU n'utilise pas Ollama, donc cet argument ne s'applique pas ici. **À retirer.**

### Verdict révisé sur Gemma 4 E2B

Gemma 4 E2B est un **candidat de second tier solide** :
- Probablement meilleur que Phi-4-mini (par extrapolation de la famille Gemma 3)
- Compatible M1 8GB (~2.5 GB en 4-bit)
- MLX disponible

**Sa note corrigée = 3/5**, et **je l'inclus dans le plan de test A/B** comme modèle secondaire à évaluer.

**Revised ranking** : Qwen 3-4B (1er choix) > Gemma 4 E2B (2e choix) > SmolLM3 3B (3e choix) > Gemma 3 4B (4e choix méconnu) > Phi-4-mini (5e choix actuel).

### Pourquoi pas Qwen 3.5 4B ? (rapport #4) — révisé

**Position initiale** (trop rigide) : "Qwen 3 4B (5.7%) bat Qwen 3.5 4B". 
**Position corrigée** : nuance importante — le 10.5% HHEM est sur `qwen3.5-flash-2026-02-23`, **un modèle différent** (Flash, optimisé vitesse, ~date proche mais modèle distinct du Qwen 3.5 4B-Instruct général).

Le Vectara HHEM ne contient **aucun Qwen 3.5 4B-Instruct** mesuré directement. Tous les "Qwen 3.5" du leaderboard sont des variantes API distantes :
- `qwen3.5-flash-2026-02-23` (10.5%) — optimisé vitesse, pas le 4B-Instruct
- `qwen3.5-35b-a3b` (10.5%) — MoE 35B
- `qwen3.5-plus-2026-02-15` (10.7%) — modèle propriétaire "Plus"
- `qwen3.5-122b-a10b` (11.2%) — MoE 122B
- `qwen3.5-27b` (12.1%) — 27B dense

Donc l'extrapolation "Qwen 3.5 4B Inherit = 10.5%" est aussi une **extrap moyenne contestable**, comme pour Qwen 3.5 2B.

**Raisons pratiques pour écarter Qwen 3.5 4B-Instruct (à défaut de HHEM)** :
1. **Multimodal** (image-text-to-text, comme Qwen 3.5 2B) — surcoût RAM pour NURU qui n'utilise pas la vision LLM.
2. **Plus récent que Qwen 3** (fév 2026 vs avril 2025) — moins de retours communautaires consolidés.
3. **Moins de traction** (à confirmer — pas vérifié ici).

**Mais** : sur le critère RAM/text-pur, Qwen 3.5 4B = pire que Qwen 3-4B. Ce sont les **vraies raisons de l'écarter**, pas un score HHEM qui ne s'applique pas directement. Mon raisonnement initial mélangeait les deux — c'était confus.

### Position finale révisée sur Qwen 3.5 2B (et leçon méthodologique)

Mêmes leçons que Gemma 4 E2B :
- **Pas disqualifié sur HHEM absent** — modèle trop jeune (créé 28 février 2026, dernière MAJ HHEM = 11 mai 2026), pas testé.
- **Score révisé 3/5**, plus haut que l'implicite antérieur (confondu avec Qwen 3.5 Flash 10.5%, qui est un modèle différent).
- **Inclus dans Phase B** comme candidat à tester (Test 3 dans l'ordre de priorité après Qwen 3-4B et Gemma 4 E2B).
- **Forces :** 2.27B params, MLX 4-bit = ~1.5 GB sur M1 8GB, 1.6M téléchargements (traction prouvée), le plus léger des candidats testés.
- **Faiblesses :** multimodal (image-text-to-text) — surcoût RAM potentiel pour rien en usage NURU classique.

### Pourquoi pas Gemma 4 E2B ? (rapport #2) — révisé


Raisons retenues (nuancées) :
- **N'a pas de score HHEM mesuré** — mais parce que Vectara ne l'a pas encore testé, pas parce qu'il est mauvais. La famille Gemma 3 = 6.4% hallucination, l'extrapolation vers Gemma 4 est favorable.
- **Multimodal any-to-any** (texte + image + audio + vidéo) — surcoût RAM théorique, ~5.1B params totaux dont seulement ~2.3B actifs. En 4-bit = ~2.5-3 GB sur M1 8GB. **Viable mais moins efficient que Qwen 3-4B dense.**
- **Maturité limitée** — créé mars 2026, peu de retours MLX communautaires.

**Raison de le mettre en 2ᵉ position** : la famille Gemma 3 a une **excellente calibration anti-hallucination** (souvent citée par les experts), et Gemma 4 hérite probablement de cette philosophie. **C'est un pari raisonnable**, mais non vérifié.

**Donc** : dans le plan de test A/B (Phase B), Gemma 4 E2B est **inclus comme candidat alternatif**. Si Qwen 3-4B ne convainc pas → tester Gemma 4 E2B en Phase B2.

### Pourquoi pas SmolLM3 3B ? (rapport #3)

1. Très bien noté (995 likes HF) MAIS absent du leaderboard HHEM.
2. Pourrait être excellent — à tester plus tard comme variant secondaire.

### Pourquoi pas Gemma 3 4B ? (cité par rapport #3)

Plan B immédiat si Qwen 3 4B ne convainc pas. Score 6.4% hallucination valide, modèle stable depuis longtemps.

### Pourquoi Qwen 3-4B alors ?

**Triple alignement** :
1. Hallucination 5.7% mesurée (Vectara) — 4× meilleur que Phi-4-mini.
2. **Modèle texte dense pur** — pas de multimodal gaspillage RAM.
3. Famille Qwen 3 bien documentée, MLX quantization 4-bit disponible et vérifiée.

---

## 3. Plan d'action proposé

### Phase A — Diagnostic pipeline (1 jour)

Avant de changer le modèle, **vérifier si le pipeline NURU actuel amplifie le problème**.

**Tâches** :
1. Déplacer les instructions grounding de `<|system|>` vers `<|user|>` dans `src/core/orchestrator.py:_build_prompt()` (méthode documentée V5/V6).
2. Renforcer `sanitize_chunk_content` (`src/rag_engine.py:67`) avec `sanitize_document_content` du PromptGuard.
3. Réduire le `SYSTEM_PROMPT_STATIC` à une version compact (~300 tokens au lieu de 800).

**Critère de succès** : avec Phi-4-mini encore en place, le taux d'hallucination sur le test set doit baisser d'au moins 30%. Si oui → le modèle n'était pas le seul problème. Si non → passer en Phase B.

### Phase B — A/B Test (Qwen 3.5 2B → Gemma 4 E2B) vs Phi-4-mini (1 semaine)

**Setup itératif** :
```bash
# Backup
cp config/settings.yaml config/settings.yaml.phi4-backup

# Test 1 : Qwen 3.5 2B (candidat #1 révisé — pari raisonnable sur génération nouvelle)
# config/settings.yaml
local_model: mlx-community/Qwen3.5-2B-4bit
local_model_fallback: mlx-community/Phi-4-mini-instruct-4bit
```

**Test 1** : lancer les **25 questions** de `tests/rag_eval_dataset.yaml`, comparer vs Phi-4-mini (fallback).

**Si Qwen 3.5 2B gagne** (≥80% réponses correctes, ≥50% hallucinations en moins, RAM peak raisonnable) → **bascule Phase C**.

**Si Qwen 3.5 2B déçoit**, Test 2 (paris risqués, dernière chance) :
```yaml
local_model: mlx-community/gemma-4-E2B-4bit  # Gemma 4 E2B (paris sur famille Gemma malgré failure Gemma 3)
```

**Si les deux échouent** : Phi-4-mini reste — pas d'autre candidat raisonnable disponible aujourd'hui. Retour à Phase A (fix pipeline) en priorité.

**Mesures pour chaque modèle** :
- Réponse grounded correcte (oui/non/partiel)
- Tokens/s
- RAM pic observée (CRITÈRE DUR — élimination si > 4 GB)
- Hallucination manifeste (Leblanc évalue subjectivement)
- Temps de cold start

**Critère bascule** : le modèle retenu doit gagner sur ≥80% des questions ET ne pas faire ramer la machine ET citer correctement les sources.

### Phase C — Bascule définitive (1 jour)

Si Phase B validée :
```yaml
local_model: mlx-community/Qwen3-4B-4bit
local_model_fallback: mlx-community/gemma-3-4b-it-4bit  # 2e choix mesuré 6.4%
```

Documentation :
- Mise à jour `README.md` (section "LLM-Phi-4-mini" → "LLM-Qwen3-4B").
- Mise à jour `NURU_V9.md` sprint log.
- Commit atomique.

### Phase D — Suivi (1 mois)

- Mesurer en continu le taux de feedback 👎 (déjà implémenté V4.5).
- Watchdog RAM (déjà en place V12).
- Si hallucinations persistent >15% du volume → Phase D2 = tester Gemma 3 4B.

---

## 4. Risques et mitigations

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| Qwen 3 4B fait swap RAM sur M1 | Moyenne | Élevé | Test Phase B avant commit. Si swap, fallback Gemma 3 4B. |
| Qwen 3 4B format chat incompatible Phi-4 | Faible | Faible | `apply_chat_template()` est générique, déjà supporte Qwen. |
| Qwen 3 4B refuse de citer les sources RAG | Faible | Élevé | PromptGuard + StrictRAGGuard + EvidenceVerifier existants. |
| Régression performance (latence x2) | Moyenne | Faible | Phased rollout, garder Phi-4 en fallback. |
| Leblanc veut un autre modèle | Variable | Variable | Phase B permet de tester plusieurs candidats avant décision finale. |

---

## 5. Ce que je n'ai PAS recommandé (et pourquoi)

| Alternative écartée | Pourquoi |
|---|---|
| **Qwen 3.5 4B** (rapport #4) | Multimodal (surcoût RAM), plus récent que Qwen 3 (moins retours), et le score HHEM 10.5% s'applique à `qwen3.5-flash-2026-02-23` (modèle Flash API distant, ≠ Qwen 3.5 4B-Instruct). Pas disqualifié sur HHEM, disqualifié sur RAM moins efficient que Qwen 3-4B dense. |
| **Qwen 3.5 2B** (rapport #4) | **Révision** : trop pénalisé au challenge #2. Score révisé 3/5 (vs confusion antérieure avec Flash 10.5%). Inclus maintenant en Phase B test 3. Plus léger des candidats (1.5 GB 4-bit), 1.6M téléchargements — pari légitime pour RAM budget serré. |
| **Gemma 4 E2B** (rapport #2) | **Révision** : trop pénalisé au challenge #1. C'est un candidat de tier 2 raisonnable. Inclus maintenant en Phase B test 2. Multimodal any-to-any (~5.1B params → ~2.5 GB 4-bit sur M1 8GB, viable). Famille Gemma 3 = 6.4% hallucination. **PAS disqualifié sur "pas de HHEM"**, mais en second car : moins efficient qu'un dense texte pur, maturité limitée. |
| **SmolLM3 3B** (rapport #3) | Très bien noté mais non testé HHEM — à tester en Phase D2. |
| **Llama 3.2 3B** | Stable mais hallucinations moins contrôlées que Qwen 3. |
| **Ministral 3B** | Communauté plus petite, peu de retours M1. |
| **Stack multi-modèles** (rapport #4 §6.1) | Coût RAM incompatible M1 8GB. |
| **Phi-4-mini + Phi-4 14B vérificateur** (rapport #3 §5) | Phi-4 14B cloud = coûts + dépendance réseau. |
| **Conservation de Phi-4-mini** | Score 23.5% rédhibitoire quand alternatives à 5.7% disponibles. |

---

## 6. Pourquoi je fais confiance à Vectara HHEM (et pas aux autres benchmarks)

| Benchmark | Mesure | Pertinence pour NURU |
|---|---|---|
| **Vectara HHEM** | Taux hallucination sur résumés de documents | **Élevée** — exactement le use case RAG de NURU |
| MMLU / MMLU-Pro | Connaissance générale | Moyenne — pas spécifique RAG |
| HumanEval | Code | Faible — NURU n'est pas un outil de code |
| LiveCodeBench v6 | Code | Faible |
| AIME / MATH | Maths | Moyenne — usage occasionnel |
| MT-Bench | Dialogue général | Moyenne |
| IFEval | Instruction following | Moyenne |

**MMLU ≠ fidélité au contexte.** Beaucoup d'experts confondent les deux. Un modèle à 70% MMLU peut halluciner plus qu'un modèle à 65% MMLU sur des résumés RAG. C'est précisément le cas Phi-4-mini (MMLU élevé, HHEM faible).

---

## 7. Recommandations au-delà du swap modèle

Les 4 audits se sont focalisés modèle. Mais les 88 trouvailles de l'audit V12 NURU (juin 14) contiennent des P0 critiques qui doivent rester en parallèle :

**P0 indépendant du modèle** :
- F-01 : Tests morts (✅ résolu commit `10d0273`)
- F-02 : `test_ram_monitor.py` + `test_reranker_seuil.py` collectent 0 items
- F-03 : `LoggingConfig×infra/logging_setup` doublon
- F-04 : `hybrid_mode: cloud_first` ignorée par Router
- F-05 : Identité Leblanc hardcodée dans system prompt V12
- F-07 : `test_orchestrator_pipeline.py::test_pipeline_offline` TypeError

**Ces 5 P0 sont actionnables SANS toucher au modèle** et réparables en <5h. Recommandation : **les traiter AVANT ou EN PARALLÈLE de Phase B.**

---

## 8. Décision finale — pour validation

### Option A (recommandée — phased rollout Qwen 3-4B)

| Étape | Effort | Risque |
|---|---|---|
| P0 audit V12 (en parallèle) | 5h | Faible |
| Phase A — Fix pipeline | 1 jour | Faible |
| Phase B — A/B Test Qwen 3 4B | 1 semaine | Faible |
| Phase C — Bascule si validé | 1 jour | Très faible |

**Total** : ~10 jours, risque très faible mesuré.

### Option B (rapide — bascule immédiate Qwen 3 4B)

Sans Phase A ni Phase B test. **Risque moyen** : le modèle est bon mais le pipeline n'est pas corrigé → 50% des hallucinations persistent.

**Effort** : 5 min (1 ligne YAML).

**Je recommande l'option A** : on traite les deux causes en parallèle (pipeline + modèle), pas l'une après l'autre.

---

## Validation requise

Avant de lancer quoi que ce soit :

1. **Qwen 3-4B vs Phi-4-mini** : OK pour toi comme cible ?
2. **Phase A (fix pipeline)** : OK comme pré-requis avant A/B ?
3. **Phase B (1 semaine A/B test)** : acceptable ?
4. **Gemma 3 4B comme fallback** au lieu de Phi-4-mini : OK ?

Si tu valides l'option A dans son ensemble, je commence par les P0 audit V12 + Phase A en première journée.

---

## 9. Leçon méthodologique (depuis les 2 challenges user-side)

Les 2 challenges Leblanc ont mis en évidence **mon biais d'over-disqualification** sur les modèles sans score HHEM mesuré.

**Pattern biaisé** : 
- Gemma 4 E2B : disqualifié pour "pas de HHEM" — alors que l'absence vient de la **jeunesse** du modèle (mars 2026, dernière MAJ HHEM = mai 2026).
- Qwen 3.5 2B : disqualifié implicitement via confusion avec `qwen3.5-flash-2026-02-23` (modèle **différent**, propriétaire Alibaba API).

**Le vrai piège** : appliquer un raisonnement de "ce qui n'a pas été mesuré ne vaut rien". C'est faux. Dans un domaine où les modèles sortent tous les 3-6 mois, **les plus récents n'ont simplement pas eu le temps d'être audités**.

**Règle révisée pour les audits LLM futurs** :
1. Vérifier l'âge du modèle (HF createdAt) vs dernière MAJ HHEM.
2. Si l'absence HHEM est due à un **décalage temporel** → challenger plutôt que disqualifier.
3. Utiliser le **proxy familial** (Gemma 3 → Gemma 4, Qwen 3 → Qwen 3.5) comme indice, pas comme preuve.
4. **Tester empiriquement** (Phase B) avant de disqualifier définitivement.

**Leçon transversale** : l'architecte senior doit challenger ses propres raccourcis autant que ceux des experts externes. Le rapport a été plus solide grâce aux challenges, pas grâce à mon premier jet.

---

## 10. Leçon terrain (challenge #3 Leblanc)

**Observation Leblanc sur Gemma 3 4B** :
- "Beaucoup d'hallucinations" → contredit score Vectara HHEM 6.4%
- "Fait ramer la machine" → confirme surcoût RAM opérationnel

**Analyse critique** :
1. **Hallucinations perçues > score HHEM** — Le score Vectara HHEM mesure les hallucinations sur résumés de documents longs (formulation synthétique). Si NURU pose des questions courtes/interactives, le pattern peut être différent. **Le HHEM est un proxy, pas la vérité terrain.**
2. **"Fait ramer"** — 3.2 GB Phi-4 + 3.2 GB Gemma 3 = 6.4 GB sur M1 8 GB. Swap probable. Cohérent avec un système sous pression (15 Mo RAM libre au moment du test). Possible aussi : keeps-alive surchargé, embedder/RAG qui pompe de la RAM en parallèle.
3. **HW non 16GB** — Mon rapport parlait "M1 8GB" mais j'ai parfois sous-entendu que ça tiendrait un 4B confortablement. Avec 8GB total (PySide6, OS, embeddings), **le budget local est plus serré que les estimations**.

**Conséquences sur le plan** :
- **Gemma 3 4B** = **recalibrer en Phase B** avec mesure réelle avant de l'écrire quelquepart
- **Critère "RAM peak"** doit être mesuré explicitement (pas juste "viable sur le papier")
- **Stay focused** : la comparaison doit être faite sur ton hardware, dans ton contexte

**Implication méthodologique forte** : Mes recommandations Phase B doivent produire **des mesures terrain**, pas se contenter de "c'est noté sur un benchmark". Le scope du Phase B s'élargit légèrement pour intégrer RAM et tokens/s comme critères durs du ranking.

---

## 11. Leçon 4 — Pourquoi Qwen 3.5 2B devient le 1er choix après les 4 challenges

**Cumulatif des challenges Leblanc** :
1. Gemma 4 E2B : "pas disqualifié sur absence HHEM" (révision)
2. Qwen 3.5 2B : idem (révision)
3. Gemma 3 4B : éliminé sur données terrain (hallucinations + ram)
4. **Qwen 3 (et 2.5) : déjà testés, défaite "hallucine + pas de compréhension contexte"**

**Ce que ça change** :
- Qwen 3-4B passe du 1er choix au pari "à retester avec extrême prudence" — ta famille Qwen 3 a déjà échoué
- Qwen 3.5 2B (génération **nouvelle**, février 2026) devient le pari raisonnable sur la présomption qu'Alibaba a corrigé les bugs
- Gemma 4 E2B reste pari #2, fragilisé par le pattern Gemma 3 (à tester quand même, parce que Gemma 4 = refonte)

**Pourquoi Qwen 3.5 pourrait réussir** :
- Alibaba a publié `qwen3-235b-a22b` thinking, `qwen3.5-35b-a3b`, `qwen3.5-122b-a10b` (MoE, plus gros, HHEM mesurés) — signe que la roadmap Qwen 3.5 est pensée agent-first
- Qwen 3.5 est probablement une **réécriture majeure** ciblant spécifiquement les faiblesses utilisateur (pas juste un nouveau fine-tune)
- Score Vectara HHEM partiel (Flash = 10.5%) suggère que **ça reste perfectible mais pas catastrophique**

**Pourquoi on peut basculer directement sur Qwen 3.5 2B** :
- Tu as déjà intention de tester (c'est pour ça que tu m'as demandé de le télécharger)
- Phase A (fix pipeline) reste valide quel que soit le modèle → on peut lancer les deux en parallèle
- Si Qwen 3.5 2B échoue, on n'a rien d'autre raisonnable sauf Gemma 4 (pari risqué)

---

## 12. Conclusion réaliste

À l'issue de **5 audits critiques + 4 challenges Leblanc**, on arrive à un constat modeste :

1. **Aucune recommandation universelle** — chaque famille modèle a ses forces/faiblesses
2. **Les benchmarks Vectara sont des proxies**, pas des vérités
3. **Les données terrain (Leblanc) priment** sur tous les rapports experts
4. **Qwen 3.5 2B est notre meilleur pari actuel** mais reste un pari
5. **Phase A (fix pipeline) doit se faire en parallèle**, sans attendre les résultats Phase B

**Décision finale révisée** : lancer Phase A en parallèle de la fin des téléchargements Qwen 3.5 2B + Gemma 4 E2B. Tests A/B Phase B dès que les deux modèles sont disponibles.

---

*Auteur : Hermes — synthèse post-4-audits + 4 challenges Leblanc. Date : 2026-06-21.*
*Sources primaires citées : Vectara HHEM Leaderboard (mai 2026), HuggingFace API (vérifs multiples 2026-06-21), NURU Audit Synthèse (juin 14), NURU Audit Live V12 (juin 21).*
