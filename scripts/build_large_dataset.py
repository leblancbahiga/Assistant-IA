#!/usr/bin/env python3
"""Génère un dataset d'entraînement LoRA à partir des chunks RAG indexés.

Méthode: bulk generation — crée des paires Q/R à partir des chunks,
avec 18% de questions piège (contexte A + question B → refus).
Sortie: train.jsonl (384 ex) + valid.jsonl (16 ex) au format ChatML.
Voir skill mlx-lora-training → references/bulk-dataset-generation.md
"""

import json, os, re, random, sqlite3
from pathlib import Path

SEED = 42
TARGET_TRAIN = 384
TARGET_VALID = 16
PIEGE_RATIO = 0.18
MIN_CHUNK_CHARS = 80
MAX_CHUNK_CHARS = 2000
INDEX_DB = "indexes/nuru.db"
OUT_DIR = "data/adapters/rag"

random.seed(SEED)

QUESTION_TEMPLATES = {
    "definition": [
        "Qu'est-ce que {sujet} exactement ?",
        "Comment définir {sujet} ?",
        "Que comprend le concept de {sujet} ?",
    ],
    "person": [
        "Qui est {sujet} ?",
        "Peux-tu présenter {sujet} ?",
        "Quelles sont les compétences de {sujet} ?",
    ],
    "organization": [
        "Qu'est-ce que {sujet} ?",
        "Comment fonctionne {sujet} ?",
        "Quel est le rôle de {sujet} ?",
    ],
    "procedure": [
        "Comment {sujet} ?",
        "Quelle est la procédure pour {sujet} ?",
        "Quelles sont les bonnes pratiques pour {sujet} ?",
    ],
    "number": [
        "Quel est le {sujet} ?",
        "Combien de {sujet} ?",
        "Quels sont les chiffres concernant {sujet} ?",
    ],
    "date": [
        "Quand {sujet} ?",
        "À quelle date {sujet} ?",
        "À quel moment {sujet} ?",
    ],
    "location": [
        "Où {sujet} ?",
        "Dans quelle région {sujet} ?",
        "Où se déroule {sujet} ?",
    ],
    "general": [
        "Que dit le document sur {sujet} ?",
        "Peux-tu résumer les informations concernant {sujet} ?",
        "Quels sont les points clés à retenir sur {sujet} ?",
    ],
}

PATTERNS = {
    "definition": re.compile(r'\b(?:défini|concept|notion|terme|s\'agit|est un|est une)\b', re.I),
    "person": re.compile(r'\b(?:né[e]?\s+(?:en|à|le)|diplômé|CV|poste|responsable|consultant|expert)\b', re.I),
    "organization": re.compile(r'\b(?:société|institution|ministère|programme|projet|bureau)\b', re.I),
    "procedure": re.compile(r'\b(?:étape|procédure|processus|méthode|protocole|marche\s+à\s+suivre)\b', re.I),
    "number": re.compile(r'\b(?:%|\d+[.,]\d+\s*(?:%|million|kg|tonne|ha|FCFA|EUR|\$))'),
    "date": re.compile(r'\b(?:20\d\d|janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre|période|calendrier)\b', re.I),
    "location": re.compile(r'\b(?:région|ville|province|pays|localité|situé|basé|département)\b', re.I),
}

SYSTEM_PROMPT = (
    "Tu es NURU, assistant IA spécialisé en agronomie et chaînes de valeur agricoles.\n"
    "Tu réponds UNIQUEMENT à partir des documents fournis ci-dessous.\n"
    "Tu cites tes sources avec [Source: nom_fichier].\n"
    "Si l'information n'est pas dans les documents, tu dis que tu ne trouves pas.\n"
    "Tu es concis et tu vas droit au but."
)

PIEGE_ANSWER = (
    "Je ne trouve pas l'information demandée dans les documents fournis."
)


def clean_chunk(text: str) -> str:
    """Nettoie les artefacts OCR et formatage."""
    text = re.sub(r'\n{3,}', '\n\n', text)
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        line = line.strip()
        if len(line) < 3 and line and not line.isdigit():
            continue
        if re.match(r'^[\s_\-|+]+$', line):
            continue
        if re.match(r'^\d+\s*$', line):
            continue
        line = re.sub(r'[^\x20-\x7EÀ-ÿœŒæÆ\s]', '', line)
        cleaned.append(line)
    return '\n'.join(cleaned).strip()


def classify_chunk(text: str) -> str:
    """Détecte le type de contenu du chunk."""
    for ctype, pattern in PATTERNS.items():
        if pattern.search(text):
            return ctype
    return "general"


def expand_sujets(chunk_text: str) -> list[str]:
    """Extrait 1-3 sujets (noms propres/termes techniques) d'un chunk."""
    sujets = []
    lines = chunk_text.strip().split('\n')
    for line in lines[:5]:
        line = line.strip()
        if not line:
            continue
        words = re.findall(r'\b[A-Z][a-zéèêëâàùûüôöîïç]+(?:\s+[A-Z][a-zéèêëâàùûüôöîïç]+)*\b', line)
        if words:
            s = ' '.join(words[:4])
            if len(s) > 15:
                sujets.append(s[:80])
    return sujets


def generate_answer(chunk_text: str, source_name: str) -> str:
    """Génère une réponse à partir du chunk — complète, sans marqueur de troncature."""
    text = chunk_text.strip()
    # V17.2: reponse complete (jusqu'a 5 phrases), PAS de marqueur '[...]'
    if len(text) > 2000:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        answer = ' '.join(sentences[:5])
    else:
        answer = text
    source_clean = source_name.replace('_', ' ').replace('-', ' ')
    return f"Selon le document '{source_clean}': {answer}"


def build_chatml(system: str, context_chunks: list[tuple[str, str]],
                 question: str, answer: str) -> str:
    """Construit un exemple au format messages (support mask_prompt)."""
    user_lines = []
    for i, (content, source) in enumerate(context_chunks, 1):
        clean = clean_chunk(content)[:1200]
        user_lines.append(f"[Document {i}] (Source: {source})\n{clean}")
    user_lines.append(f"\nQuestion : {question}")
    user_msg = "\n".join(user_lines)
    
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
        {"role": "assistant", "content": answer},
    ]
    return json.dumps({"messages": messages}, ensure_ascii=False)


def main():
    conn = sqlite3.connect(INDEX_DB)
    
    # 1. Charger tous les chunks avec leurs sources
    rows = conn.execute("""
        SELECT cfts.rowid, cfts.content, ch.source
        FROM chunks_fts cfts
        JOIN chunk_hierarchy ch ON cfts.rowid = ch.chunk_id
        WHERE ch.source IS NOT NULL AND length(cfts.content) > ?
        ORDER BY ch.source, cfts.rowid
    """, (MIN_CHUNK_CHARS,)).fetchall()
    
    # Grouper par source
    sources: dict[str, list[dict]] = {}
    for rowid, content, source in rows:
        if len(content) > MAX_CHUNK_CHARS:
            content = content[:MAX_CHUNK_CHARS] + "\n[...]"
        sources.setdefault(source, []).append({
            "rowid": rowid, "content": content, "source": source
        })
    
    source_names = list(sources.keys())
    print(f"📚 {len(source_names)} sources, {sum(len(v) for v in sources.values())} chunks")
    
    # 2. Générer les exemples positifs
    examples = []
    for src_name in source_names:
        chunks = sources[src_name]
        for chunk in chunks[:5]:  # max 5 chunks par source
            ctype = classify_chunk(chunk["content"])
            sujets = expand_sujets(chunk["content"])
            if not sujets:
                continue
            sujet = random.choice(sujets)
            templates = QUESTION_TEMPLATES.get(ctype, QUESTION_TEMPLATES["general"])
            question = random.choice(templates).format(sujet=sujet)
            answer = generate_answer(chunk["content"], src_name)
            context = [(chunk["content"], src_name)]
            examples.append({
                "type": "positive",
                "context": context,
                "question": question,
                "answer": answer,
                "source": src_name,
            })
            if len(examples) >= TARGET_TRAIN + TARGET_VALID:
                break
        if len(examples) >= TARGET_TRAIN + TARGET_VALID:
            break
    
    print(f"✅ {len(examples)} exemples positifs générés")
    
    # 3. Générer les exemples piège (18%)
    n_piege = int((TARGET_TRAIN + TARGET_VALID) * PIEGE_RATIO)
    pieges = []
    all_flat = [c for clist in sources.values() for c in clist]
    
    for _ in range(n_piege * 3):  # *3 pour tenter plus de combinaisons
        if len(pieges) >= n_piege:
            break
        # Chunk A → contexte
        chunk_a = random.choice(all_flat)
        # Chunk B → sujet de la question (source différente)
        src_b = random.choice([s for s in source_names if s != chunk_a["source"]])
        if not src_b:
            continue
        chunk_b = random.choice(sources[src_b])
        sujets = expand_sujets(chunk_b["content"])
        if not sujets:
            continue
        sujet = random.choice(sujets)
        ctype = classify_chunk(chunk_b["content"])
        templates = QUESTION_TEMPLATES.get(ctype, QUESTION_TEMPLATES["general"])
        question = random.choice(templates).format(sujet=sujet)
        pieges.append({
            "type": "piege",
            "context": [(chunk_a["content"], chunk_a["source"])],
            "question": question,
            "answer": PIEGE_ANSWER,
            "source": f"{chunk_a['source']} / {chunk_b['source']}",
        })
    
    print(f"✅ {len(pieges)} exemples piège générés")
    
    # 4. Mélanger et séparer train/valid
    all_examples = examples + pieges
    random.shuffle(all_examples)
    
    valid_count = min(TARGET_VALID, len(all_examples) // 10)
    train_examples = all_examples[valid_count:]
    valid_examples = all_examples[:valid_count]
    
    # 5. Écrire les fichiers
    out_dir = Path(OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    for fname, exs in [("train.jsonl", train_examples), ("valid.jsonl", valid_examples)]:
        path = out_dir / fname
        with open(path, "w", encoding="utf-8") as f:
            for ex in exs:
                line = build_chatml(SYSTEM_PROMPT, ex["context"],
                                   ex["question"], ex["answer"])
                f.write(line + "\n")
        print(f"📝 {fname}: {len(exs)} exemples")
    
    # Stats
    train_piege = sum(1 for e in train_examples if e["type"] == "piege")
    valid_piege = sum(1 for e in valid_examples if e["type"] == "piege")
    print(f"\n📊 Stats: train={len(train_examples)} ({train_piege/len(train_examples)*100:.0f}% piège), "
          f"valid={len(valid_examples)} ({valid_piege/len(valid_examples)*100:.0f}% piège)")
    
    conn.close()


if __name__ == "__main__":
    main()
