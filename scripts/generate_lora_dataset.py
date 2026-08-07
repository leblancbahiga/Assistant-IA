"""Génère dataset LoRA RAG structuré depuis l'index nuru.db.

Produit train.jsonl (84+ exemples) + valid.jsonl (9-10) au format Phi-4 ChatML.
Inclut des exemples piège (contexte sans réponse) pour apprendre à dire "je ne trouve pas".

Usage:
    cd /path/projet && PYTHONPATH="" .venv/bin/python scripts/generate_lora_dataset.py
"""
import json
import random
import sqlite3
import re
import os
from pathlib import Path

# ── Config ──
DB_PATH = "indexes/nuru.db"
OUT_DIR = "data/adapters/rag"
TRAIN_COUNT = 400
VALID_COUNT = 40
PIEGE_RATIO = 0.18  # ~15-20% d'exemples piège
MAX_CHUNK_WORDS = 180  # ~200-250 tokens par chunk
MIN_CHUNK_WORDS = 10   # ignorer les fragments trop courts

SYSTEM_PROMPT = (
    "Tu es NURU, assistant IA spécialisé en agronomie et chaînes de valeur agricoles.\n"
    "Tu réponds UNIQUEMENT à partir des documents fournis ci-dessous.\n"
    "Tu cites tes sources avec [Source: nom_fichier].\n"
    "Si l'information n'est pas dans les documents, tu dis que tu ne trouves pas.\n"
    "Tu es concis et tu vas droit au but."
)

random.seed(42)

# ── Extraction des chunks ──
def extract_chunks(db_path: str) -> list[dict]:
    """Extrait les chunks de l'index RAG, groupés par document."""
    db = sqlite3.connect(db_path)
    cur = db.cursor()

    # Récupérer les chunks via FTS (contenant le texte)
    cur.execute("""
        SELECT cfts.rowid, ch.content, ch.source
        FROM chunks_fts cfts
        JOIN chunk_hierarchy ch ON cfts.rowid = ch.chunk_id
        WHERE LENGTH(ch.content) > ?
        ORDER BY ch.source, cfts.rowid
    """, (MIN_CHUNK_WORDS * 2,))  # ~2 chars/word avg for French

    chunks_by_doc: dict[str, list[dict]] = {}
    for rowid, content, source in cur.fetchall():
        words = len(content.split())
        if words > MAX_CHUNK_WORDS * 2:  # trop long, tronquer
            words_trunc = content.split()[:MAX_CHUNK_WORDS]
            content = " ".join(words_trunc)

        doc_name = Path(source).stem if source else f"doc_{rowid}"
        doc_name = re.sub(r'[_\s]+', ' ', doc_name)[:60]

        if doc_name not in chunks_by_doc:
            chunks_by_doc[doc_name] = []
        chunks_by_doc[doc_name].append({
            "rowid": rowid,
            "content": content.strip(),
            "source": doc_name,
            "words": len(content.split()),
        })

    db.close()

    # Filtrer les docs avec assez de contenu
    valid_docs = {k: v for k, v in chunks_by_doc.items() if len(v) >= 2}
    print(f"Extrait: {sum(len(v) for v in chunks_by_doc)} chunks "
          f"de {len(chunks_by_doc)} documents "
          f"({len(valid_docs)} utilisables)")

    return valid_docs

# ── Génération Q/R ──
def make_context(chunks: list[dict], n: int = 3) -> tuple[str, list[dict]]:
    """Sélectionne n chunks aléatoires et construit le contexte."""
    selected = random.sample(chunks, min(n, len(chunks)))
    lines = []
    for i, c in enumerate(selected, 1):
        lines.append(f"[Document {i}] {c['content']}")
    return "\n\n".join(lines), selected

def pick_question(chunk: dict) -> str:
    """Génère une question à partir d'un extrait de chunk."""
    c = chunk["content"]

    # Stratégies : extraire un nom propre, un chiffre, ou un sujet
    patterns = [
        r"(?:projet|programme|initiative)\s+(\w[\w\s-]{3,40}\w)",
        r"(?:M(?:r|me|onsieur|adame)?\.?\s*)?(\w+(?:\s+\w+){1,4})\s+(?:a\s+)?(?:proposé|souligné|indiqué|mentionné|travaillé|dirigé|réalisé|coordonné)",
        r"(\d+(?:[,.]\d+)?\s*(?:%|millions|milliers|euros|dollars|USD|hectares|tonnes|kg|m²))",
        r"(?:filère|secteur|domaine)\s+(\w[\w\s-]{2,30}\w)",
    ]

    for pattern in patterns:
        m = re.search(pattern, c, re.IGNORECASE)
        if m:
            subject = m.group(1).strip()
            if len(subject) > 3:
                return f"Que contient le document sur {subject} ?"

    # Fallback : première phrase
    first_sentence = c.split(".")[0].strip()
    if len(first_sentence) > 10:
        words = first_sentence.split()
        subject = " ".join(words[:5]) if len(words) > 5 else first_sentence
        return f"Que dit le document à propos de {subject} ?"

    return f"Quelles informations trouve-t-on dans ce document ?"

def make_answer(chunks: list[dict], source_name: str) -> str:
    """Construit la réponse sourcée."""
    lines = []
    for c in chunks:
        snippet = c["content"][:200].strip()
        lines.append(f"[Source: {source_name}] {snippet}")
    return "\n\n".join(lines)

def make_piege_answer() -> str:
    """Réponse pour les exemples piège."""
    variants = [
        "Je ne trouve pas l'information demandée dans les documents fournis.",
        "Les documents fournis ne contiennent pas cette information.",
        "D'après les documents disponibles, cette information n'est pas présente.",
    ]
    return random.choice(variants)

def format_example(context: str, question: str, answer: str) -> str:
    """Formate en Phi-4 ChatML."""
    user_msg = f"{context}\n\nQuestion : {question}"
    return (
        f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\n{user_msg}<|im_end|>\n"
        f"<|im_start|>assistant\n{answer}<|im_end|>"
    )

# ── Pipeline principal ──
def generate_dataset(docs: dict[str, list[dict]], train_count: int, valid_count: int):
    """Génère les datasets d'entraînement et validation."""
    doc_names = list(docs.keys())
    examples_avec = []  # exemples avec réponse
    examples_piege = []  # exemples piège

    # 1. Générer exemples AVEC réponse
    for doc_name, chunks in docs.items():
        for _ in range(max(3, train_count // len(docs) + 2)):
            if len(examples_avec) >= train_count * 2:
                break

            context, selected = make_context(chunks)
            question = pick_question(random.choice(selected))
            answer = make_answer(selected, doc_name)
            examples_avec.append(format_example(context, question, answer))

    random.shuffle(examples_avec)

    # 2. Générer exemples PIÈGE (contexte d'un doc, question d'un autre)
    if len(doc_names) >= 2:
        for _ in range(120):
            if len(examples_piege) >= 100:
                break

            doc_a = random.choice(doc_names)
            doc_b = random.choice([d for d in doc_names if d != doc_a])

            context, _ = make_context(docs[doc_a])
            # Question sur doc_b
            question = pick_question(random.choice(docs[doc_b]))
            answer = make_piege_answer()
            examples_piege.append(format_example(context, question, answer))

    random.shuffle(examples_piege)

    # 3. Répartir train/valid
    n_avec_train = train_count - int(train_count * PIEGE_RATIO)
    n_piege_train = int(train_count * PIEGE_RATIO)

    n_avec_valid = valid_count - int(valid_count * PIEGE_RATIO)
    n_piege_valid = int(valid_count * PIEGE_RATIO)

    train = examples_avec[:n_avec_train] + examples_piege[:n_piege_train]
    valid = examples_avec[n_avec_train:n_avec_train + n_avec_valid] + examples_piege[n_piege_train:n_piege_train + n_piege_valid]

    random.shuffle(train)
    random.shuffle(valid)

    return train, valid

# ── Diversité des tokens ──
def analyze_dataset(examples: list[str], label: str):
    """Analyse la diversité et qualité du dataset."""
    total_tokens = sum(len(ex.split()) for ex in examples)
    avg_tokens = total_tokens / len(examples) if examples else 0
    piege_count = sum(1 for ex in examples if "ne trouve pas" in ex.lower())
    has_context = sum(1 for ex in examples if "Document 1]" in ex or "Document 2]" in ex)

    print(f"\n📊 {label} ({len(examples)} exemples):")
    print(f"   Longueur: {avg_tokens:.0f} mots/ex (~{avg_tokens*1.3:.0f} tokens)")
    print(f"   Piège: {piege_count} ({piege_count*100//len(examples)}%)")
    print(f"   Avec contexte RAG: {has_context}/{len(examples)}")
    print(f"   Sources fictives OK" if avg_tokens > 50 else "   ⚠️  Contextes courts")

# ── Main ──
def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print("🔍 Extraction des chunks depuis l'index RAG...")
    docs = extract_chunks(DB_PATH)

    if len(docs) < 2:
        print("❌ Pas assez de documents pour générer des pièges.")
        return

    print(f"📝 Génération du dataset...")
    train, valid = generate_dataset(docs, TRAIN_COUNT, VALID_COUNT)

    # Écrire
    train_path = os.path.join(OUT_DIR, "train.jsonl")
    valid_path = os.path.join(OUT_DIR, "valid.jsonl")

    with open(train_path, "w", encoding="utf-8") as f:
        for ex in train:
            f.write(json.dumps({"text": ex}, ensure_ascii=False) + "\n")

    with open(valid_path, "w", encoding="utf-8") as f:
        for ex in valid:
            f.write(json.dumps({"text": ex}, ensure_ascii=False) + "\n")

    # Analyse
    analyze_dataset(train, "Train")
    analyze_dataset(valid, "Valid")

    # Sample
    print(f"\n📄 Échantillon train.jsonl (1er exemple) :")
    print(train[0][:600])
    print("...")

    print(f"\n📄 Échantillon piège (si présent) :")
    for ex in train:
        if "ne trouve pas" in ex.lower():
            print(ex[:500])
            break

    print(f"\n✅ Dataset généré: {train_path} ({len(train)} ex), {valid_path} ({len(valid)} ex)")

if __name__ == "__main__":
    main()
