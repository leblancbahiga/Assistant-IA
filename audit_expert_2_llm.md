# Audit critique — Rapport expert LLM #2

> Source : 2ᵉ rapport envoyé par Leblanc BC, suite hallucinations NURU.
> Auditeur : architecte senior (Hermes).
> Date : 2026-06-21.

---

## TL;DR

**Ce rapport est MEILLEUR que le #1** (vraies données Vectara HHEM, sources identifiables, alternatives concrètes testables). Mais **il reste 5 problèmes méthodologiques**, dont 1 bloque la décision finale **maintenant**.

**Net :** on a maintenant **deux signaux convergents** —
- Phi-4-mini score 23.5% hallucination sur Vectara HHEM (3ᵉ source désormais)
- Ses alternatives (Qwen 3 4B = 5.7%, Gemma 3 4B = 6.4%) sont 4× meilleures

Mais la décision reste **bloquée par 4 inconnues** qu'il faut lever avant de basculer.

---

## ✅ PROGRÈS vs rapport #1

| Aspect | Rapport #1 | Rapport #2 |
|--------|-----------|-----------|
| Sources citées | Vague ("SitePoint 2026", "XDA") | Concrètes (Vectara HHEM leaderboard, Ollama, MicroCenter, BentoML) |
| Score hallucination Phi-4 | Pas de chiffre | **23.5%** — mesuré sur HHEM |
| Famille Gemma score | N/A | 6.4% (Gemma 3 4B) |
| Famille Qwen 3 score | N/A | 5.7% (Qwen 3 4B) |
| Reconnaissance cause | "Phi-4 mini mal optimisé" | "Microsoft a sacrifié la fidélité pour MMLU" |

**C'est suffisant pour prioriser.** Le rapport #2 reconnaît explicitement que Phi-4-mini est un **outlier** sur Vectara HHEM (pire que Nemotron 30B, plus halluciné que les grands).

---

## 🔴 PROBLÈME 1 — Commande Ollama fournie ne marche PAS

L'expert recommande :
```bash
ollama run gemma4:e2b
ollama run qwen3.5:2b
```

**Vérification Ollama API (2026-06-21)** :
- `gemma4:e2b` → **n'existe pas dans Ollama**
- `gemma4` disponible uniquement en `gemma4:31b` (62 Go ! énorme)
- `qwen3.5:2b` → **n'existe pas**, seul `qwen3.5:397b` est listé
- Phi-4-mini n'apparaît même pas dans la liste Ollama
- `nemotron-3-nano:30b` est dans Ollama (mais c'est le grand, pas le 4B demandé)

**Conclusion** : La commande proposée ne fonctionnera pas chez Leblanc. Si on prend le conseil à la lettre, on arrive sur un `pull` vide. C'est bloquant.

**Bonne nouvelle** : sur HuggingFace, en MLX (format que NURU utilise),
- `mlx-community/gemma-4-E2B-4bit` ✅ existe (307 redirect = existe)
- `mlx-community/Qwen3.5-2B-4bit` ✅ existe (200)
- `mlx-community/Qwen3-4B-4bit` ✅ existe (200)
- `mlx-community/SmolLM3-3B-4bit` ✅ existe (200)

Donc les modèles existent **mais il faut passer par HF + mlx-lm**, pas Ollama. Le rapport n'a pas intégré ce détail — critique car NURU utilise MLX.

---

## 🔴 PROBLÈME 2 — Gemma 4 E2B = multimodal, pas focalisé text+tool

Vérification HF API : `google/gemma-4-E2B`
- `pipeline_tag` = **`any-to-any`** (modèle unifié multimodal)
- `architectures` = `Gemma4ForConditionalGeneration`
- Famille `gemma4_unified`

C'est comparable à un mini-GPT-4o. **Excellent en théorie mais deux problèmes :**

1. **Multimodal = surcoût RAM** au runtime (les poids multimodaux sont chargés même si on n'utilise que texte).
2. **Pour un assistant RAG où le problème = hallucinations texte**, un modèle unifié audio+image+texte **n'est pas optimal** vs un modèle texte-only dense (type Qwen3 dense).

Le rapport vante "Audio natif" comme atout. Pour NURU aujourd'hui, audio = pipeline séparé `src/audio.py` (mlx-whisper pour STT, Piper pour TTS). **L'audio dans le LLM principal n'apporte rien** — il faudrait tout réécrire.

---

## 🟠 PROBLÈME 3 — "RAG Grounding 50%" non sourcé

Le rapport cite pour Gemma 4 E2B :
- **RAG Grounding : 50%** (vs 33.3% pour le modèle précédent, +17 points)
- **Function Calling : 80%**
- **Multi-turn : 70%** (le score le plus haut de toute la famille Gemma 4, battant ses propres grands frères)

**Ces chiffres ne sortent pas de nulle part — le rapport évoque "un benchmark Reddit détaillé r/LocalLLaMA"**. Mais le rapport ne donne **aucun lien, aucune date, aucune méthodologie**.

C'est d'autant plus louche que :
- "Multi-turn 70% meilleur que 12B/26B/31B" est **biens statistiquement invraisemblable** : les modèles 12B+ battent rarement leurs petits frères sur ce genre de tâche.
- "RAG Grounding 50%" — Benchmarks Vectara HHEM **ne sort pas ce score** en l'état. Le HHEM mesure le taux d'hallucination, pas un "grounding %" brut.

**Probabilité de chiffres manipulés/trop jolis** : ÉLEVÉE.

---

## 🟠 PROBLÈME 4 — Qwen 3.5 2B est multimodal aussi

Vérification `Qwen/Qwen3.5-2B` HF API :
- `pipeline_tag` = `image-text-to-text`
- `architectures` = `Qwen3_5ForConditionalGeneration`
- multimodal natif

Même remarque que Gemma 4 E2B : **le texte-only dense (Qwen3-4B) sera probablement plus efficient pour NURU aujourd'hui**.

Qwen3-4B (`Qwen/Qwen3-4B`) = **text-generation pur** (pas multimodal), 200 OK sur HF.

---

## 🟠 PROBLÈME 5 — Commande de téléchargement donnée pour GGUF/ollama

Rapport 2 commande :
```bash
huggingface-cli download bartowski/Qwen_Qwen3.5-2B-GGUF \
  --include "Qwen_Qwen3.5-2B-Q4_K_M.gguf"
```

Format **GGUF (llama.cpp / ollama)**. NURU utilise `mlx_lm` (commit V4.5 + V12). Incompatibilité directe — il faudrait basculer `src/llm_local.py` de MLX vers llama.cpp ou transformer le pipeline de chargement.

Effort estimé : **1-2 jours de refactoring** non mentionné dans le rapport.

---

## ✅ POINTS VALIDÉS

| Point | Validé ? | Source |
|-------|----------|--------|
| Phi-4-mini = 23.5% hallucination HHEM | **OUI** | Vectara HHEM 2025 leaderboard |
| Qwen 3 4B = 5.7% hallucination | **OUI** | Vectara HHEM 2025 leaderboard |
| Gemma 3 4B = 6.4% hallucination | **OUI** | Vectara HHEM 2025 leaderboard |
| Gemma 4 E2B existe HF | **OUI** | HF data, créé 2026-06-03 |
| SmolLM3-3B existe HF | **OUI** | HF data, créé 2025-09 |
| Qwen3-4B existe MLX | **OUI** | mlx-community 200 OK |

---

## 🎯 Verdict senior sur ce rapport #2

| Question | Réponse |
|----------|---------|
| Le signal "Phi-4-mini est mauvais en RAG" est-il confirmé ? | **OUI** par 2 sources (rapport #1, rapport #2) |
| Le remplacement est-il actionnable aujourd'hui ? | **NON** — commande Ollama cassée, format GGUF/MLX incompatible |
| Le choix Gemma 4 E2B est-il le bon ? | **Risqué** — multimodal, scores invérifiés |
| Faut-il tester Qwen 3 4B plutôt ? | **OUI** — text-generation pur, MLX dispo, hallucination mesurée 5.7% |

---

## Recommandation opérationnelle

**Étape 1 — diagnostic (1 jour)** : confirmer que c'est bien le modèle, pas le pipeline.

```bash
# Tester le fallback ACTUEL déjà chargé
# Change config/settings.yaml: local_model: mlx-community/Qwen2.5-1.5B-Instruct-4bit
# Redémarrer dashboard, lancer 10-20 requêtes RAG identiques
# Comparer manuellement les hallucinations
```

**Étape 2 — test A/B élargi (1-2 jours)** :
```yaml
# config/settings.yaml — variantes à tester une par une
local_model: mlx-community/Qwen3-4B-4bit           # Qwen 3 4B (5.7% hallu)
local_model: mlx-community/Qwen3.5-2B-4bit         # Qwen 3.5 2B (multimodal)
local_model: mlx-community/gemma-4-E2B-4bit        # Gemma 4 E2B (recommandé expert)
local_model: mlx-community/SmolLM3-3B-4bit         # SmolLM3 (995 likes HF!)
```

**Étape 3 — mesure comparative** : pour chaque modèle, lancer les 25 questions du `tests/rag_eval_dataset.yaml`, mesurer :
- Taux réponse correcte grounded
- Tokens/s
- RAM pic
- Hallucination manifeste

**Décision finale** : on tranche une fois les chiffres en main, pas avant.

Veux-tu que j'engage ce protocole de test sur ta machine, ou tu veux d'abord chercher un 3ᵉ rapport ?
