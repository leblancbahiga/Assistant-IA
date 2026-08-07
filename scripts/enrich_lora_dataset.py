"""Améliore le dataset LoRA RAG : enrichit les 84 exemples avec du contexte documentaire.

Stratégie :
1. Conserve les Q/R originales (propres, bien formées)
2. Ajoute le contexte RAG (chunks du document source) dans le prompt user
3. Crée des exemples piège en mélangeant contexte et question de documents différents
4. Garde le format Phi-4 ChatML

Usage:
    cd /path/projet && PYTHONPATH="" .venv/bin/python scripts/enrich_lora_dataset.py
"""
import json
import random
import sqlite3
import re
import os

random.seed(42)

DB_PATH = "indexes/nuru.db"
ORIG_TRAIN = "data/adapters/rag/train.jsonl"
ORIG_VALID = "data/adapters/rag/valid.jsonl"
OUT_DIR = "data/adapters/rag"
TRAIN_TARGET = 84
VALID_TARGET = 9
PIEGE_RATIO = 0.18  # ~15 exemples piège

TOP_K_CHUNKS = 3        # nombre de chunks à injecter comme contexte
MAX_CHUNK_CHARS = 500   # max caractères par chunk dans le contexte

# ── Extraction des chunks nettoyés ──
def load_chunks_by_source(db_path: str) -> dict[str, list[str]]:
    """Charge les chunks FTS, nettoyés, groupés par nom de source."""
    db = sqlite3.connect(db_path)
    cur = db.cursor()
    cur.execute("""
        SELECT cfts.content, ch.source
        FROM chunks_fts cfts
        JOIN chunk_hierarchy ch ON cfts.rowid = ch.chunk_id
        WHERE LENGTH(cfts.content) > 40
          AND ch.source NOT LIKE '%checkpoint%'
    """)

    sources: dict[str, list[str]] = {}
    for content, source in cur.fetchall():
        # Nettoyage
        clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', content)
        clean = re.sub(r'\s+', ' ', clean).strip()
        if len(clean) < 30:
            continue
        # Nom de source court
        src_name = re.sub(r'[_\s]+', ' ', os.path.splitext(os.path.basename(source))[0])
        src_name = src_name[:60]
        if src_name not in sources:
            sources[src_name] = []
        sources[src_name].append(clean)

    db.close()
    # Filtrer les sources avec assez de contenu
    sources = {k: v for k, v in sources.items() if len(v) >= TOP_K_CHUNKS}
    print(f"📚 {sum(len(v) for v in sources)} chunks nettoyés, "
          f"{len(sources)} sources utilisables")
    return sources

def pick_chunks_for_context(source_chunks: dict[str, list[str]],
                            target_source: str) -> tuple[str, str]:
    """Sélectionne TOP_K_CHUNKS chunks d'une source pour construire le contexte.
    Retourne (contexte_formatte, nom_source_nettoye)."""
    if target_source not in source_chunks:
        # Fallback: source aléatoire
        target_source = random.choice(list(source_chunks.keys()))

    chunks = source_chunks[target_source]
    selected = random.sample(chunks, min(TOP_K_CHUNKS, len(chunks)))

    lines = []
    for i, chunk in enumerate(selected, 1):
        trunc = chunk[:MAX_CHUNK_CHARS]
        lines.append(f"[Document {i}] {trunc}")
    return "\n\n".join(lines), target_source

def source_for_answer(answer: str, all_sources: list[str]) -> str | None:
    """Trouve le nom de source mentionné dans la réponse."""
    for src in all_sources:
        short = os.path.splitext(os.path.basename(src))[0][:40]
        if short in answer:
            return src
    return None

def format_example(context: str, question: str, answer: str) -> str:
    user_msg = f"{context}\n\nQuestion : {question}"
    return (
        f"<|im_start|>system\nTu es NURU, assistant IA spécialisé en agronomie "
        f"et chaînes de valeur agricoles. Tu réponds UNIQUEMENT à partir des "
        f"documents fournis ci-dessous. Tu cites tes sources avec "
        f"[Source: nom_fichier]. Si l'information n'est pas dans les documents, "
        f"tu dis que tu ne trouves pas. Tu es concis et tu vas droit au but."
        f"<|im_end|>\n"
        f"<|im_start|>user\n{user_msg}<|im_end|>\n"
        f"<|im_start|>assistant\n{answer}<|im_end|>"
    )

# ── Extraction des questions/réponses originales ──
def parse_examples(path: str) -> list[tuple[str, str]]:
    """Extrait (question, réponse) du JSONL original au format ChatML."""
    examples = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            text = data.get("text", "")
            # Extraire la question (entre <|im_start|>user et <|im_end|>)
            m_q = re.search(r"<\|im_start\|>user\n(.*?)<\|im_end\|>", text, re.DOTALL)
            # Extraire la réponse (entre <|im_start|>assistant et <|im_end|>)
            m_a = re.search(r"<\|im_start\|>assistant\n(.*?)<\|im_end\|>", text, re.DOTALL)
            if m_q and m_a:
                question = m_q.group(1).strip()
                answer = m_a.group(1).strip()
                # Nettoyer les "Question :" préfixés
                question = re.sub(r'^Question\s*:\s*', '', question)
                examples.append((question, answer))
    return examples

# ── Pipeline ──
def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print("🔍 Chargement des chunks FTS...")
    sources = load_chunks_by_source(DB_PATH)
    all_source_names = list(sources.keys())

    if len(all_source_names) < 2:
        print("❌ Pas assez de sources pour générer des pièges.")
        return

    print(f"📖 Parsing des questions/réponses originales...")
    train_qas = parse_examples(ORIG_TRAIN)
    valid_qas = parse_examples(ORIG_VALID)
    print(f"   Train: {len(train_qas)} Q/R, Valid: {len(valid_qas)} Q/R")

    if not train_qas:
        print("❌ Aucune Q/R extraite.")
        return

    # 1. Générer exemples AVEC contexte pertinent
    train_avec = []
    valid_avec = []
    all_qas = train_qas + valid_qas

    for q, a in all_qas:
        # Trouver la source de la réponse
        src = source_for_answer(a, all_source_names)
        if not src:
            src = random.choice(all_source_names)

        context, _ = pick_chunks_for_context(sources, src)
        full_context = f"Voici les documents pertinents :\n\n{context}"
        formatted = format_example(full_context, q, a)

        if len(train_avec) < len(train_qas):
            train_avec.append(formatted)
        else:
            valid_avec.append(formatted)

    random.shuffle(train_avec)
    random.shuffle(valid_avec)

    # 2. Générer exemples PIÈGE
    train_piege = []
    valid_piege = []
    n_piege_needed = int(TRAIN_TARGET * PIEGE_RATIO)

    for q, a in all_qas:
        if len(train_piege) + len(valid_piege) >= n_piege_needed + 2:
            break

        # Source DIFFÉRENTE de celle de la réponse
        src = source_for_answer(a, all_source_names)
        other_sources = [s for s in all_source_names if s != src]
        if not other_sources:
            continue
        wrong_src = random.choice(other_sources)
        context, _ = pick_chunks_for_context(sources, wrong_src)
        full_context = f"Voici les documents pertinents :\n\n{context}"

        answer_piege = random.choice([
            "Je ne trouve pas l'information demandée dans les documents fournis.",
            "Les documents fournis ne contiennent pas cette information.",
            "D'après les documents disponibles, cette information est absente.",
        ])
        formatted = format_example(full_context, q, answer_piege)

        if len(train_piege) < n_piege_needed - 1:
            train_piege.append(formatted)
        else:
            valid_piege.append(formatted)

    # 3. Assemblage final
    n_avec_train = TRAIN_TARGET - len(train_piege)
    n_avec_valid = VALID_TARGET - len(valid_piege)

    train = train_avec[:n_avec_train] + train_piege
    valid = valid_avec[:n_avec_valid] + valid_piege
    random.shuffle(train)
    random.shuffle(valid)

    # 4. Écriture
    train_path = os.path.join(OUT_DIR, "train.jsonl")
    valid_path = os.path.join(OUT_DIR, "valid.jsonl")

    with open(train_path, "w", encoding="utf-8") as f:
        for ex in train:
            f.write(json.dumps({"text": ex}, ensure_ascii=False) + "\n")

    with open(valid_path, "w", encoding="utf-8") as f:
        for ex in valid:
            f.write(json.dumps({"text": ex}, ensure_ascii=False) + "\n")

    # 5. Stats
    word_counts = [len(ex.split()) for ex in train]
    piege_count = sum(1 for ex in train if "ne trouve pas" in ex.lower())
    print(f"\n📊 Train ({len(train)} ex):")
    print(f"   Longueur: min={min(word_counts)} max={max(word_counts)} "
          f"moy={sum(word_counts)/len(word_counts):.0f} mots "
          f"(~{int(sum(word_counts)/len(word_counts)*1.3)} tokens)")
    print(f"   Piège: {piege_count}/{len(train)} "
          f"({piege_count*100//len(train)}%)")
    print(f"   Contexte RAG: 100%")

    word_counts_v = [len(ex.split()) for ex in valid]
    piege_count_v = sum(1 for ex in valid if "ne trouve pas" in ex.lower())
    print(f"\n📊 Valid ({len(valid)} ex):")
    print(f"   Longueur: min={min(word_counts_v)} max={max(word_counts_v)} "
          f"moy={sum(word_counts_v)/len(word_counts_v):.0f} mots")
    print(f"   Piège: {piege_count_v}/{len(valid)} "
          f"({piege_count_v*100//len(valid)}%)")

    print(f"\n📄 Échantillon normal:")
    for ex in train:
        if "ne trouve pas" not in ex.lower():
            print(ex[:600])
            break

    print(f"\n📄 Échantillon piège:")
    for ex in train:
        if "ne trouve pas" in ex.lower():
            print(ex[:500])
            break

    print(f"\n✅ Dataset enrichi: {train_path} ({len(train)} ex), "
          f"{valid_path} ({len(valid)} ex)")

if __name__ == "__main__":
    main()
