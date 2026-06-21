# Audit critique — Rapport expert LLM (`rapport_expert_1.md`)

> Source : rapport envoyé par Leblanc BC, post-hallucinations NURU.
> Auditeur : architecte senior (Hermes).
> Date : 2026-06-21.

---

## TL;DR

**Je ne peux PAS valider ce rapport en l'état.** Il y a au moins **6 problèmes méthodologiques graves** qui invalident partiellement le verdict, dont 1 potentiellement fabricatrice.

Le résultat net : **on ne change PAS le modèle sur la base de ce rapport seul**, mais on peut retenir *certains* signaux si on les vérifie.

---

## 1. Hallucinations sur les noms et dates (drapeau rouge critique)

L'expert recommande **Qwen 3.5 2B** et invoque un repo `bartowski/Qwen_Qwen3.5-2B-GGUF`. Vérification HuggingFace API (2026-06-21) :

- **`Qwen/Qwen3.5-2B`** ✅ existe, créé 2026-02-28, ~2.3B params BF16, modèle multimodal.
- **`bartowski/Qwen_Qwen3.5-2B-GGUF`** ✅ existe (200 OK).

Mais voici le problème : **le modèle "Qwen 3.5" est un modèle multimodal** (pipeline_tag = `image-text-to-text`, famille `qwen3_5`). Ce n'est PAS un modèle texte+tools pur. Le rapport le présente comme tel. Pas rédhibitoire, mais incohérent.

Et l'expert cite **"Ministral-3-3B"** — je ne trouve rien qui valide. Mistral a sorti Mistral Small 3 fin 2025 + Ministral 3B début 2025, mais **"Ministral-3-3B"** n'apparaît pas comme nom officiel. Probable confusion.

Et **"Nemotron Cascade 2 (30B), 54 t/s sur RTX 4060"** — invérifiable, RTX 4060 = laptop GPU 8 Go, faire tourner 30B à 54 t/s est **physiquement improbable**. À 4-bit, 30B = ~16 Go, ne tient pas sur 8 Go. Sans parler de 54 t/s.

**Probabilité d'écart matériel/fabrication** : ÉLEVÉE.

## 2. Les benchmarks "papier" ne disent rien sur ton problème

Le tableau cite :
- MMLU ~62-68.5
- HumanEval ~55-64
- MT-Bench ~7.0-7.4

**Aucun de ces benchmarks ne mesure les hallucinations en tool calling.** Ce sont des scores de connaissance générale (MMLU), de code (HumanEval), de dialogue (MT-Bench). Le problème de NURU est précis : **hallucination dans les réponses RAG grounded** ("3-10 ans d'expérience" sur un document qui ne le dit pas). Aucun benchmark ne capture ça.

L'écart MMLU de 5 points (62 vs 68) entre Gemma 4 E2B et Phi-4-mini **ne prédit pas** une réduction d'hallucination RAG. C'est une corrélation invérifiée.

**Conclusion** : la justification scientifique du remplacement est **faible**.

## 3. ✗ Le diagnostic "Phi-4 mini = coupable" est contestable

L'expert affirme :
> "Phi-4 mini est probablement le coupable de tes hallucinations"

C'est **au mieux une hypothèse**, pas un fait. Trois causes alternatives plus probables dans NURU (audit V12 du 21 juin) :

1. **Le contexte RAG est mal injecté** — Phi-4-mini ignore les instructions dans `<|system|>` quand le contexte est dans `<|user|>` (bug documenté, fixé en V5 puis re-cassé en V6+).
2. **Le `PromptGuard` n'est pas appliqué à 100% des chemins** — vu dans `rag_engine.py`, le sanitize local est perfectible (`sanitize_chunk_content` ligne 67).
3. **Le `system prompt` dur injecté en post-prompt est trop bavard** — il consomme 800+ tokens de budget contexte, ce qui réduit la place pour le vrai contexte.

Basculer sur Qwen 2B ou Gemma 4 E2B ne résout aucun de ces 3 problèmes.

## 4. ✗ MLX / M1 8 Go non traité

**Aucun mot sur MLX** dans le rapport. Or, NURU tourne sur :
- **Apple Silicon (M1)**
- **8 Go de RAM unifiée**
- Modèle chargé via `mlx-lm` (commit `0ab694e`/`2259ebc`)

L'expert recommande `Qwen3.5-2B-GGUF` (format GGUF = llama.cpp). **GGUF ≠ MLX.** Si on prend `bartowski/Qwen_Qwen3.5-2B-GGUF`, on doit réécrire `src/llm_local.py` qui utilise `mlx_lm.load`. Effort non mentionné.

Alternative : `mlx-community/Qwen3.5-2B-4bit` (qui n'a pas été vérifié). Il faut vérifier son existence avant tout.

## 5. ✗ Tool calling survendu

"Tool calling natif excellent (intégré Qwen-Agent)" — pour Qwen **2.5** c'est vrai. Pour **Qwen 3.5** je n'ai aucune confirmation dans le rapport.

Surtout : **NURU n'utilise pas de tool calling structuré.** L'Agent Loop est en cours (Phase 1 roadmap V12), et le `ToolRegistry` est jeune (commits `0ab694e`, `06d9a9d`). Les hallucinations dont parle Leblanc sont **sur les réponses RAG / chat**, pas sur des appels de tools.

L'argument principal du rapport (Qwen 3.5 = meilleur tool calling) **ne s'applique pas** au problème de Leblanc aujourd'hui.

## 6. ✓ Points positifs à retenir

Même si le rapport est globalement contestable :

- **Qwen2.5 1.5B-Instruct-4bit** est déjà chargé comme fallback dans NURU (`local_model_fallback`). Si Phi-4 hallucine, tester Qwen2.5-1.5B est trivial (une ligne config).
- **Qwen3-1.7B** existe, plus récent, plus petit encore. Pourrait être testé.
- **Quantization Q5 vs Q4** — vrai signal sur les hallucinations (cf. recherche OWASP sur quantization). À tester.
- **Présence penalty = 2.0** — vrai levier anti-hallucination, applicable aujourd'hui.

---

## Verdict senior

| Question | Réponse |
|----------|---------|
| Le rapport est-il fiable ? | **Non.** Plusieurs signaux faibles / fabrications. |
| Faut-il remplacer Phi-4 mini ? | **Pas sur cette base.** D'abord diagnostiquer les vraies causes (RAG, prompt, grounding). |
| Faut-il quand même tester un autre modèle ? | **Oui**, mais sur critères vérifiables, pas papier. |
| Faut-il faire confiance à l'expert pour les prochains rapports ? | **Avec prudence.** Challenger chaque assertion. |

## Recommandations opérationnelles

1. **Test A/B local avant décision** : faire tourner 20-30 requêtes RAG sur Phi-4-mini vs Qwen2.5-1.5B vs Qwen3-1.7B, mesurer hallucinations grounded.
2. **Vérifier en priorité le pipeline**, pas le modèle. Le bug documenté (`instruction dans <|system|>` ignorée par Phi-4-mini) est documenté vivace mais **jamais confirmé corrigé dans le code actuel**. Le vérifier empiriquement.
3. **Demander à l'expert des sources** : URL des benchmarks cités, snapshots Kaggle/HF Leaderboard, commandes de reproduction.
4. **Si l'expert persiste avec ses sources**, accepter le rapport 2 s'il est meilleur calibré.
