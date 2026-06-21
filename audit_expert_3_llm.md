# Audit critique — Rapport expert LLM #3

> Source : 3ᵉ rapport envoyé par Leblanc BC, suite rapports #1 et #2.
> Auditeur : architecte senior (Hermes).
> Date : 2026-06-21.

---

## TL;DR

**Rapport #3 est le plus nuancé des trois** — c'est aussi **le moins actionnable**. Il évite le piège du verdict tranché, mais au prix de sérieux problèmes méthodologiques et de chiffres invérifiables. **Sur le fond (Phi-4-mini = mauvais pour RAG)** : il rejoint les rapports #1 et #2. **Sur la forme** : il introduit 5 problèmes nouveaux qui n'existaient pas avant, dont 1 contredit les rapports précédents.

---

## 🔴 DÉCOUVERTE CRITIQUE : le rapport #3 contredit les rapports #1 et #2 sur le chiffre clé

### Le fait

Le rapport #3 affirme :
> "Sur le leaderboard Vectara, **Phi-4** affiche un excellent **3.7%** de taux d'hallucination."

Et plus bas :
> "Mais un autre benchmark révèle que [Phi-4-mini] a une accuracy de détection d'hallucinations **68%**."

### Vérité (HuggingFace + GitHub Vectara)

J'ai directement récupéré le leaderboard sur `github.com/vectara/hallucination-leaderboard`. Les chiffres exacts (dernière mise à jour 11 mai 2026) :

| Modèle | Taux hallucination | Answer rate |
|--------|----:|----:|
| **microsoft/Phi-4** (14B) | **3.7%** | 80.7% |
| **microsoft/Phi-4-mini-instruct** (3.8B) | **23.5%** | 92.5% |

**Donc le rapport #3** :
- ✅ Phi-4 (14B) = 3.7% = **VRAI** (mais c'est le 14B, pas le mini)
- ✅ Phi-4-mini (3.8B) = 23.5% = **VRAI** (mais le rapport ne le cite **PAS** correctement)
- ❌ "accuracy 68%" = **INVENTÉ** — ce chiffre n'apparaît dans aucune source publique connue

**Conclusion** : Le rapport #3 fait **deux choses répréhensibles** :
1. Il **omet** que Phi-4-mini (le modèle effectivement en place dans NURU) est à 23.5%, pas 3.7%
2. Il invente un chiffre "68% accuracy détection" pour justifier une conclusion plus clémente

C'est le piège classique du "Phi-4 (14B) brille, mais Phi-4-mini hérite forcément de la qualité". **Faux** : sur Vectara, Phi-4-mini est 6× plus halluciné que Phi-4.

Les rapports #1 et #2 (que j'avais critiqués pour d'autres raisons) **avaient raison sur ce point précis**.

---

## 🔴 PROBLÈME 2 — Architecture multi-modèles = piège à RAM pour M1 8GB

Le rapport #3 propose :
- Qwen3.5-4B (général)
- Pleias-RAG-1B (RAG spécialisé)
- LFM2.5-1.2B-Nova ou FunctionGemma-270M (function calling spécialisé)

**Total théorique** :

| Modèle | RAM Q4 |
|--------|--------|
| Qwen3.5-4B | ~3.5 GB |
| Pleias-RAG-1B | ~1.2 GB |
| LFM2.5-1.2B-Nova | ~1.5 GB |

Si on les charge tous : **6.2 GB**. Plus PySide6 (~600 MB) + embeddings (~200 MB) + OS (~3 GB partagé). **Budget M1 8GB saturé**, swap killer activé, latence ×10.

**Réalité** : il faut **1 modèle chargé à la fois + déchargement keep-alive**. L'architecture "3 modèles" implique :
- 3 téléchargements (~3 GB total)
- 3 chargements à froid (~30s chacun)
- Orchestration des bascules très fragile

**Le rapport #3 ne reconnaît pas ce coût**. Pour un M1 8GB, **on reste sur 1 modèle principal + éventuellement 1 fallback léger**, pas 3 spécialisés.

---

## 🟠 PROBLÈME 3 — "Vitesse 205 t/s / 308 t/s" invérifiable sur M1

Le rapport cite :
| Modèle | Vitesse (4k tokens) |
|--------|--------------------|
| Gemma 4 E2B | 205 t/s |
| Qwen 3.5 2B | 308 t/s |
| Phi-4-mini M1 | ~18 t/s |

**Vérification** : aucune méthodologie donnée. Sur quelle machine, quel framework, quelle quantification ?

Les petits modèles MoE (Gemma 4 E2B, Qwen 3.5 2B) peuvent être rapides sur **Inférence GPU serveur** (H100, A100). Mais sur **M1 8GB + MLX**, les perfs sont très différentes. Phi-4-mini tourne à ~12 t/s sur M1 (cf. skill V4.5 référencé), pas 18 t/s — l'écart est déjà à creuser.

**Probabilité élevée** : ces chiffres viennent d'**un autre matériel** (server-grade GPU), pas du M1. À ignorer pour la décision.

---

## 🟠 PROBLÈME 4 — SmolLM3 cité mais pas dans le leaderboard

Le rapport cite **SmolLM3-3B** comme candidat (1000+ likes HF, "fully open").

**Vérification** : SmolLM3-3B **n'apparaît PAS** dans le leaderboard Vectara HHEM (vérifié). Le modèle a 975 likes HF mais **n'a pas été testé sur HHEM**, donc **on ne connaît PAS son taux d'hallucination**.

Le rapport dit qu'il "**surpasse Llama-3.2-3B et Qwen2.5-3B**" — possible, mais pas vérifié sur le critère qui nous intéresse (hallucination RAG).

---

## 🟠 PROBLÈME 5 — "Qwen3.5-4B 79.1 sur MMLU-Pro" invérifiable

Le rapport cite :
> Score de **79.1 sur MMLU-Pro**, surpassant largement Phi-4-mini (52.8).

**Vérification** : Qwen3.5-4B (modèle multimodal) est récent (HF créé 2026-02-28). Aucun benchmark MMLU-Pro officiel publié. **Chiffre invérifiable** sur les sources publiques officielles. Probabilité de fabrication : ÉLEVÉE.

À l'inverse, Phi-4-mini est réputé pour ses scores MMLU Competitive — pas 52.8 (qui est très bas pour un Phi-4).

---

## ✅ POINTS VALIDÉS (les 3 rapports convergent maintenant)

| Signal | Source | Validé |
|--------|--------|--------|
| Phi-4-mini hallucination = 23.5% | Vectara HHEM 11 mai 2026 | **OUI** |
| Qwen 3-4B hallucination = 5.7% | Vectara HHEM | **OUI** |
| Qwen 3.5 4B existe en MLX | HF API, mlx-community 200 OK | **OUI** |
| SmolLM3-3B existe en MLX | HF API, mlx-community 200 OK | **OUI** |
| Gemma 4 E2B existe en MLX | HF API, 307 redirect | **OUI** |
| Architecture multi-modèles = piège RAM | évident par calcul | **OUI** |

---

## 🎯 Synthèse des 3 rapports

| Critère | Rapport 1 | Rapport 2 | Rapport 3 |
|---------|-----------|-----------|-----------|
| Phi-4-mini identifié comme problème | ✅ claimed | ✅ confirmé | ⚠️ dilué (Phi-4 vs Phi-4-mini confondus) |
| Alternative principale | Qwen 3.5 2B | Gemma 4 E2B | Qwen 3.5 4B / multi-modèles |
| Sources chiffrées | Vague | Vectara HHEM | Vectara HHEM partiel |
| Compatibilité MLX reconnue | NON | NON | NON |
| Architecture M1 8GB reconnue | NON | OUI partiellement | NON |
| Verdict actionnable | Non | Non | Non (le plus prudent) |

**Les 3 rapports convergent sur** : Remplacer Phi-4-mini est justifié. Mais aucun ne donne une commande que tu peux taper aujourd'hui sur ton M1.

---

## Recommandation finale après 3 rapports

**Décision** : passer de Phi-4-mini à **Qwen3-4B** (texte pur, 5.7% hallucination mesurée, MLX disponible, compatible avec ton setup existant).

**Justification de Qwen3-4B vs alternatives** :
- vs Qwen3.5-4B : Qwen3.5 est multimodal, on perd la RAM sur audio/image inutiles
- vs Gemma 4 E2B : Gemma 4 E2B est multimodal aussi, sans score hallucination vérifié
- vs SmolLM3 : pas de score hallucination HHEM
- vs Qwen2.5-1.5B (fallback actuel) : 2× plus gros, hallucination non mesurée mais famille Qwen3 < 6%

**Effort d'implémentation** : 1 ligne YAML + 1 redémarrage. Le modèle `mlx-community/Qwen3-4B-4bit` est disponible sur HuggingFace et fait ~2.5 Go en 4-bit. **Tu restes sous le budget M1.**

**Protocole de validation** : une fois Qwen3-4B désigné comme default :
1. Lancer `nuru_dashboard.py`
2. Poser les 25 questions du `tests/rag_eval_dataset.yaml`
3. Comparer manuellement Phi-4-mini (en fallback) vs Qwen3-4B (en default)
4. Mesurer : réponses grounded correctes / tokens/s / RAM pic
5. Si Qwen3-4B ≥ Phi-4 sur ≥80% des requêtes ET hallucine moins, garder.

**Veux-tu que je revoie les rapports 4 et 5 maintenant, ou tu préfères qu'on valide Qwen3-4B comme hypothèse ?**

Ma recommendation : **arrête la lecture de rapports ici**, valide Qwen3-4B, et lance le test A/B. Tu as assez de signaux convergents.
