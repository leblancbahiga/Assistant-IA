#!/usr/bin/env python3
"""Génère des RÉPONSES LONGUES (300-500 mots) pour le dataset LoRA via le cloud.

Lit le dataset existant (context + question déjà bons), régénère UNIQUEMENT
la réponse assistant via le LLM cloud, avec citations [Source: ...] et
structure (titres/listes). Recommandé par les audits V17 (_5, (1).md).

Usage: python scripts/generate_long_answers.py [--limit N] [--resume]
Sortie: data/adapters/rag/train.jsonl + valid.jsonl (écrasés)
"""

import json, os, sys, time, random
from pathlib import Path

# Ajouter la racine du projet au path (sinon 'from src...' échoue)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

random.seed(42)
OUT_DIR = Path("data/adapters/rag")
CHECKPOINT = OUT_DIR / "_long_answers_progress.json"

PROMPT_TEMPLATE = """À partir du CONTEXTE documentaire ci-dessous, rédige une réponse DÉTAILLÉE de 300 à 500 mots à la QUESTION posée.

Règles :
1. Réponds UNIQUEMENT à partir du contexte fourni — jamais d'invention.
2. Structure ta réponse : une introduction, 2-4 sections avec titres, une conclusion.
3. Utilise des listes à puces quand c'est pertinent.
4. Cite la source après chaque information importante : [Source: nom_fichier].
5. Si l'information demandée n'est pas dans le contexte, dis-le clairement.
6. Rédige en français, de manière professionnelle et fluide.

## CONTEXTE
{context}

## QUESTION
{question}

## RÉPONSE DÉTAILLÉE"""

PIEGE_ANSWER = (
    "Je ne trouve pas l'information demandée dans les documents fournis. "
    "Le contexte ne contient pas d'éléments permettant de répondre à cette question. "
    "Si vous pouvez préciser votre demande ou fournir un document complémentaire, "
    "je pourrai vous aider plus efficacement."
)


def load_dataset():
    """Charge train + valid actuels."""
    exemples = []
    for fname in ("train.jsonl", "valid.jsonl"):
        path = OUT_DIR / fname
        if not path.exists():
            continue
        with open(path) as f:
            for line in f:
                ex = json.loads(line)
                if "messages" in ex:
                    exemples.append(ex)
                else:
                    # Ancien format {"text": ...} → skip
                    continue
    return exemples


def extract_user_parts(user_content: str):
    """Extrait (contexte, question) du message user."""
    if "Question :" in user_content:
        ctx, q = user_content.split("Question :", 1)
        return ctx.strip(), q.strip()
    return user_content, user_content


def generate_long_answer(cloud, context: str, question: str) -> str:
    """Appelle le cloud pour une réponse longue et structurée.

    V17.3 : retries ×3 avec backoff — le provider free est instable après
    ~20 appels consécutifs (timeouts/SSL). En cas d'échec répété, retourne "".
    """
    prompt = PROMPT_TEMPLATE.format(
        context=context[:3500], question=question
    )
    last_err = None
    for attempt in range(3):
        try:
            resp = cloud.generate(prompt, timeout=45.0)
            if resp and len(resp.strip()) >= 200:
                return resp.strip()
            print(f"  ↪️ réponse trop courte ({len(resp or '')} chars), retry")
        except Exception as e:
            last_err = e
            print(f"  ↪️ retry {attempt+1}: {type(e).__name__}")
            time.sleep(2 * (attempt + 1))  # backoff
    print(f"  ⚠️ cloud error après 3 tentatives: {last_err}")
    return ""


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    from src.llm_cloud import CloudLLM
    cloud = CloudLLM()

    exemples = load_dataset()
    print(f"📚 {len(exemples)} exemples chargés")

    # Reprise : progression sauvegardée
    done = set()
    if CHECKPOINT.exists():
        try:
            done = set(json.loads(CHECKPOINT.read_text()))
            print(f"↩️  Reprise : {len(done)} déjà générées")
        except Exception:
            pass

    generated = 0
    for i, ex in enumerate(exemples):
        if limit and generated >= limit:
            break
        msgs = ex["messages"]
        # Ne régénère pas les pièges (la réponse de refus est standardisée)
        if msgs[2]["content"].startswith("Je ne trouve pas"):
            continue

        key = str(i)
        if key in done:
            continue

        ctx, q = extract_user_parts(msgs[1]["content"])
        if not q:
            continue

        answer = generate_long_answer(cloud, ctx, q)
        if not answer:
            continue

        msgs[2]["content"] = answer
        done.add(key)
        generated += 1
        if generated % 10 == 0:
            CHECKPOINT.write_text(json.dumps(sorted(done)))
            print(f"  … {generated} réponses générées")
        time.sleep(0.3)  # léger délai pour ne pas saturer

    CHECKPOINT.write_text(json.dumps(sorted(done)))
    print(f"✅ {generated} réponses longues générées ({len(done)} total)")

    # Sauvegarder
    train = [e for e in exemples[:456]]
    valid = exemples[456:472] if len(exemples) >= 472 else []
    # Répartir les pièges restants
    random.shuffle(train)
    with open(OUT_DIR / "train.jsonl", "w", encoding="utf-8") as f:
        for ex in train:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    with open(OUT_DIR / "valid.jsonl", "w", encoding="utf-8") as f:
        for ex in valid:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"📝 train.jsonl: {len(train)} | valid.jsonl: {len(valid)}")


if __name__ == "__main__":
    main()
