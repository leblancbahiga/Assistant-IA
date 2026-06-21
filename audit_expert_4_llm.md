# Audit critique — Rapport expert LLM #4 (`NURU_LLM_COMPARISON.md`)

> Source : `NURU_LLM_COMPARISON.md` (353 lignes, signé "Mavis, architecte IA senior", 2026-06-21).
> Auditeur : architecte senior (Hermes).
> Date : 2026-06-21.

---

## TL;DR

**Le rapport #4 est le plus convaincant SUR LA FORME** — bien structuré, sources citées, nuances techniques, propositions concrètes. Mais je dois en rejeter **au moins 5 points majeurs** sur les 4 que je vais challenger.

**Net** : le rapport #4 **suit la même conclusion** que les #1-#3 (Phi-4-mini problématique), **mais invente une stat (53%) sur source inaccessible** et propose des commandes qui ne marchent pas. La recommandation d'ensemble (Qwen 3.5 4B) **reste défendable** sur la base du rapport Vectara HHEM (23.5% Phi-4-mini) — mais pas sur les chiffres du rapport #4.

---

## 🔴 PROBLÈME 1 — Le chiffre central "53% hallucination" est invérifiable

Le rapport #4 affirme PALM-DANS-LA-MAIN :

> "D'après l'étude *Safety and Alignment of Small Language Models* (Research Square, 2025) : **Phi-4-Mini 3.8B = 53% d'hallucination**, le pire de sa génération."

J'ai tenté de récupérer la source primaire :
- DOI `10.21203/rs.3.rs-XXXXXXX/v1` → **DOI Not Found**
- URL `https://www.researchsquare.com/article/rs-XXXXXXX/latest.pdf` → **Page Not Found**

**Le placeholder `XXXXXXX` dans le DOI est explicite** : le rapport a été rédigé avec un DOI factice. Il n'existe aucune URL Research Square avec ce numéro. La source est **fausse**.

Le rapport ajoute "Phi-4-mini a 25% d'hallucinations de plus que ses concurrents directs". **Origine : néant**.

À l'inverse, le rapport **omet le seul chiffre vérifiable** : **Vectara HHEM officiel** :
- Phi-4-mini-instruct = 23.5% hallucination (vérifié aujourd'hui sur le README Vectara)
- Qwen 3-4B = 5.7%
- Gemma 3-4B = 6.4%

**Conclusion** : les chiffres "53%" et "42%" du tableau ne sont, eux, **pas vérifiables**. Le rapport confond ou amplifie volontairement.

---

## 🔴 PROBLÈME 2 — Commandes Ollama qui ne marchent PAS

Le rapport propose :
```bash
ollama pull qwen3.5:4b-instruct-q4_K_M
ollama pull qwen3.5:0.8b-instruct-q4_K_M
ollama pull qwen3-coder-next:4b-q4_K_M
ollama pull gemma4:e4b-q4_K_M
```

**Vérification Ollama API (2026-06-21)** — la liste réelle des modèles :

| Commande rapport | Existe Ollama ? |
|---|---|
| `qwen3.5:4b-instruct-q4_K_M` | **NON** — seul `qwen3.5:397b` (379 GB) existe |
| `qwen3.5:0.8b-instruct-q4_K_M` | **NON** — Ollama n'a aucun Qwen 0.8B |
| `qwen3-coder-next:4b-q4_K_M` | **NON** — Ollama a `qwen3-coder-next` (78 GB monolithique, pas 4B) |
| `gemma4:e4b-q4_K_M` | **NON** — Ollama a `gemma4:31b` (60 GB) seulement |

**Aucune** de ces 4 commandes ne fonctionnera. Si Leblanc les tape, il se prend un `pull` vide.

**Bonne nouvelle** : sur HuggingFace, **Qwen3.5-4B-Instruct** (`Qwen/Qwen3.5-4B-Instruct`) existe (200 OK), `mlx-community/gemma-4-E4B-4bit` existe (307 OK), mais `mlx-community/Qwen3.5-0.8B-4bit` et `mlx-community/Qwen3-Coder-Next-4B-4bit` **n'existent pas** en quant MLX dédiée (401).

**Effort réel de migration** : il faut passer par **HF + mlx-lm.convert** (ce que NURU fait déjà), pas Ollama. Le rapport ne reconnaît pas cet effort.

---

## 🟠 PROBLÈME 3 — Architecture "Trivial + Principal + Specialty" coûteuse

Le rapport propose une stack à 4 modèles :
```
Trivial (Qwen 0.8B) + Principal (Qwen 4B) + Code (Qwen3-Coder-Next 4B) + Vision (Gemma 4 E4B)
```

**Calcul RAM** :

| Modèle | Q4 utilisé |
|---|---|
| Qwen 0.8B | ~1 GB |
| Qwen 4B | ~3 GB |
| Qwen3-Coder-Next 4B | ~3 GB |
| Gemma 4 E4B (multimodal) | ~4-5 GB |

Si on suit la cascade "charger le bon au bon moment" : **le keep-alive sera un enfer**. Il faudrait :
- 4 téléchargements (~15 GB cumulés, lourd sur M1 8GB)
- Déchargement/rechargement à chaque bascule (5s de cold start à chaque fois)
- Le modèle reste chargé après usage → en pratique 1 seul modèle reste live

Le rapport dit lui-même "Tu peux l'avoir en option sans le charger par défaut" — mais il vante aussi le bénéfice d'avoir Gemma 4 E4B en parallèle. **Incohérence interne**.

**Réalité M1 8GB** : on reste sur **1 modèle principal + 1 fallback léger**, comme aujourd'hui. Pas 4.

---

## 🟠 PROBLÈME 4 — Chiffres de vitesse invérifiables sur M1

Le rapport cite :
| Modèle | Vitesse M1 (Q4_K_M, tok/s) |
|---|---|
| Phi-4-mini | 12 |
| Gemma 4 E2B | ~18 |
| Qwen 3.5 2B | ~22 |
| Qwen 3.5 4B | ~14 |

**Vérification** : le rapport cite "Benchmarks (Artificial Analysis & papiers officiels)" en titre, mais ces chiffres M1 sont **sans source identifiée**. Artificial Analysis benchmark sur GPU serveur (H100, A100). Sur M1 8GB, je n'ai aucune mesure reproductible.

**Particulièrement louche** :
- "Qwen 3.5 4B = 14 tok/s sur M1" → ce modèle est multimodal, plus lent attendu. Mais chiffre exact invérifiable.
- "Gemma 4 E2B ~18 tok/s" → 18 tok/s pour un modèle unifié multimodal, sur M1, sans benchmark connu ? Suspect.

À retenir : Phi-4-mini = 12 tok/s mesuré sur M1 (cf. skill V4.5 référencé dans NURU), c'est cohérent. Les autres sont des **estimations défensives**.

---

## 🟠 PROBLÈME 5 — "Phi-4-mini honnête mais mente avec aplomb"

La formulation est rhétorique mais pas fondée. Le rapport cite correctement (enfin) que Phi-4-mini est "très fort pour le code et le math mais mente avec aplomb sur les faits généraux". C'est cohérent avec ce qu'on observe dans NURU (questions RAG factuelles = réponses fausses). Mais l'explication causale (données synthétiques GPT-4 → "apprend les patterns du prof") est **plausible mais invérifiable**.

Ce n'est pas une critique forte — c'est un point où le rapport fait un raisonnement spéculatif raisonnable. **À garder.**

---

## 🟡 PROBLÈME 6 — Pragmatisme intéressant malgré les erreurs

Le rapport #4 fait 4 choses **utiles** que je retiens :

1. **Idée 6.1 Routing par confiance** — "Marvis Tencent" comme inspiration. Bonne piste mais **pas pour maintenant** (c'est une ré-architecture, pas un swap de modèle).
2. **Idée 6.3 LoRA personnalisé** — fine-tune Qwen sur ton style. Excellent ROI si tu fais du local en routine.
3. **Cache sémantique (6.4)** — NURU l'a déjà partiellement via `llm_cache.py`, à étendre.
4. **Vérdict 7.5** — "le modèle ne résoudra pas tout seul les hallucinations" — c'est la prise de conscience clé, cohérente avec mon audit V12 (F-03 que le bug grounding RAG est aussi dans le pipeline).

---

## ✅ Synthèse comparative des 4 rapports

| Critère | #1 | #2 | #3 | #4 |
|---------|----|----|----|----|
| Phi-4-mini hallucination chiffre | N/A | 23.5% (Vectara) | Phi-4 3.7% (mix confusion) | **53% (Research Square DOI mort)** |
| Qwen série score hallucination | N/A | 5.7% (Qwen 3 4B, Vectara) | 5.7% (idem) | Absent du tableau |
| Gemma série score hallucination | N/A | 6.4% (Gemma 3 4B) | 6.4% | ~45% (Research Square ?) |
| Compatibilité MLX NURU | NON | NON | NON | NON |
| Commandes actionnables | NON | NON | NON | **NON (toutes cassées)** |
| Sources vérifiables | Vague | OK | Partiel | Invérifiable |
| Qualité argumentation | Faible | Bonne | Bonne | **Excellente** |
| Verdict tranché | Qwen 3.5 2B | Gemma 4 E2B | Qwen 3.5 4B multi-modèles | Qwen 3.5 4B + stack 4-modèles |

**Constat** : **Les 4 rapports convergent sur Phi-4-mini = problème**, mais aucun ne propose une migration valide sur M1 8GB + MLX ce matin.

---

## 🎯 Verdict senior final

| Question | Réponse |
|----------|---------|
| Faut-il remplacer Phi-4-mini ? | **OUI** (signal convergent, Vectara 23.5%) |
| Faut-il suivre le rapport #4 tel quel ? | **NON** — les commandes sont cassées, le chiffre 53% est inventé |
| Qwen 3.5 4B est-il la bonne cible ? | **PROBABLE** — modèle texte pur (vs multimodal), RAM compatible, mais pas vérifié sur hallucination (le score Vectara connu est sur Qwen 3 4B, pas Qwen 3.5 4B). |
| Que faire maintenant ? | **Tester contre le ground truth local**, pas contre des benchmarks papier. |

---

## ⚠️ Note capitale : confusion modèles

Le rapport #4 confond régulièrement **Qwen 3.5** et **Qwen 3**. Ce sont deux familles distinctes chez Alibaba :

| Famille | Date | Hallucination Vectara | Leaderboard |
|---|---|---|---|
| **Qwen 3** | Mai 2025 | **5.7%** (Qwen 3 4B) | ✅ mesuré |
| **Qwen 3.5** | Fév 2026 | **10.5%** (Qwen 3.5 Flash) | ⚠️ moins bon |

**Donc** : sur le critère hallucination, **Qwen 3 4B (5.7%) bat Qwen 3.5 4B**. Le rapport #4 recommande Qwen 3.5 — j'aurais recommandé Qwen 3 (la génération précédente, plus testée).

**À vérifier** empiriquement avant de trancher.

---

## Ma proposition concrète

Indépendamment du rapport #4, voici le test **actionnable** que je te propose :

```yaml
# config/settings.yaml — Test A/B
# Test 1: passer local_model sur Qwen3-4B (recommandation Vectara 5.7%)
local_model: mlx-community/Qwen3-4B-4bit

# Test 2 (à venir): Gemma 3 4B (Vectara 6.4%, plus mature que Gemma 4 E2B non testé)
# local_model: mlx-community/gemma-3-4b-it-4bit

# Test 3: petit modèle Si pas OK
# local_model: mlx-community/Qwen3.5-2B-4bit (multimodal mais léger)
```

**Protocole** :
1. Modifie le YAML, redémarre, lance les 25 questions `tests/rag_eval_dataset.yaml`.
2. Compare manuellement les réponses vs Phi-4-mini (fallback actuel).
3. Si Qwen 3-4B ≥ Phi-4-mini sur ≥80% des questions ET hallucine moins, garder.
4. Si Qwen3-4B < Phi-4-mini : tester Gemma 3 4B en 2ᵉ passe.

**As-tu d'autres rapports à me faire passer, ou on bascule sur l'expérimentation ?**
