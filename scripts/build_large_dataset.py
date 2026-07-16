#!/usr/bin/env python3
"""Génère un dataset LoRA RAG de 400+ exemples depuis l'index nuru.db.

Stratégie :
1. Extrait tous les chunks de chunks_fts (contenu chunké propre)
2. Analyse chaque chunk pour identifier son type (définition, personne, 
   entreprise, procédure, chiffre, date, lieu, concept)
3. Génère une question naturelle et variée adaptée au type
4. Produit 80% positifs (contexte contient la réponse) + 20% pièges
5. Sauvegarde au format Phi-4 ChatML

Évite les artefacts PDF : filtre les lignes trop courtes, les fragments
de tableaux, les caractères Unicode exotiques.
"""
import json
import math
import os
import random
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

random.seed(42)

# ── Configuration ──
DB_PATH = "indexes/nuru.db"
OUTPUT_DIR = "data/adapters/rag"
TARGET_TRAIN = 384  # 400 - 16 validation
TARGET_VALID = 16
PIEGE_RATIO = 0.18  # 18% d'exemples piège
MIN_CHUNK_CHARS = 80
MAX_CHUNK_CHARS = 2000

# ── Templates de questions par type de contenu ──

QUESTION_TEMPLATES = {
    "definition": [
        "Qu'est-ce que {sujet} exactement ?",
        "Peux-tu expliquer ce qu'est {sujet} ?",
        "Comment définir {sujet} ?",
        "Que comprend le concept de {sujet} ?",
        "Quelle est la définition de {sujet} ?",
    ],
    "person": [
        "Qui est {sujet} ?",
        "Peux-tu présenter {sujet} ?",
        "Quel est le parcours de {sujet} ?",
        "Que fait {sujet} dans l'organisation ?",
        "Quelles sont les compétences de {sujet} ?",
    ],
    "organization": [
        "Qu'est-ce que {sujet} ?",
        "Peux-tu décrire {sujet} ?",
        "Quel est le rôle de {sujet} ?",
        "Comment fonctionne {sujet} ?",
        "Que fait {sujet} ?",
    ],
    "procedure": [
        "Comment {sujet} ?",
        "Quelle est la procédure pour {sujet} ?",
        "Peux-tu expliquer les étapes de {sujet} ?",
        "Comment mettre en œuvre {sujet} ?",
        "Quelles sont les bonnes pratiques pour {sujet} ?",
    ],
    "number": [
        "Quel est le {sujet} ?",
        "Combien de {sujet} ?",
        "Quelle quantité de {sujet} ?",
        "Quels sont les chiffres concernant {sujet} ?",
        "Peux-tu donner les statistiques de {sujet} ?",
    ],
    "date": [
        "Quand {sujet} ?",
        "À quelle date {sujet} ?",
        "Quel est le calendrier pour {sujet} ?",
        "Depuis quand {sujet} ?",
        "Quelle période couvre {sujet} ?",
    ],
    "location": [
        "Où {sujet} ?",
        "Dans quelle région {sujet} ?",
        "Quel est le lieu de {sujet} ?",
        "Où se déroule {sujet} ?",
        "Dans quel pays {sujet} ?",
    ],
    "general": [
        "Que nous apprend le document sur {sujet} ?",
        "Que contient le document concernant {sujet} ?",
        "Peux-tu résumer les informations sur {sujet} ?",
        "Quels sont les points clés à retenir sur {sujet} ?",
        "Que dit le rapport à propos de {sujet} ?",
    ],
}

# Expansions de sujets (pour varier les questions d'un même chunk)
def expand_sujets(chunk_text):
    """Extrait des sujets potentiels depuis le début du chunk."""
    sujets = []
    lines = chunk_text.strip().split('\n')
    for line in lines[:5]:
        line = line.strip()
        if not line:
            continue
        # Prendre les 3-6 premiers mots significatifs
        words = re.findall(r'\b[A-Z][a-zéèêëàâäùûüôöîïçÉÈÊËÀÂÄÙÛÜÔÖÎÏÇ]+(?:\s+[A-Z][a-zéèêëàâäùûüôöîïç]+)*\b', line)
        if words:
            s = ' '.join(words[:4])
            if len(s) > 15:
                sujets.append(s[:80])
        # Sinon, prendre les premiers mots tout court
        if not sujets:
            words = line.split()[:5]
            if words:
                s = ' '.join(words)
                if len(s) > 10:
                    sujets.append(s[:80])
    return sujets


def classify_chunk(text):
    """Classifie le type de contenu d'un chunk."""
    text_lower = text.lower()
    
    # Mots-clés par type
    patterns = {
        "definition": r'\b(?:défini|concept|notion|terme|désigne|représente|constitue|s\'agit|est un|est une)\b',
        "person": r'\b(?:né[e]?\s+(?:en|à|le)|diplômé|expérience\s+professionnelle|compétences|CV|curriculum|poste|responsable|directeur|consultant|expert)\b',
        "organization": r'\b(?:organisation|entreprise|société|institution|ministère|association|bureau|agence|mission|programme|projet)\b',
        "procedure": r'\b(?:étape|procédure|processus|méthode|protocole|marche\s+à\s+suivre|instruction|guide|manuel|recommandation)\b',
        "number": r'\b(?:%|\d+[.,]\d+\s*(?:%|million|milliard|kg|tonne|ha|FCFA|EUR|\$))',
        "date": r'\b(?:20\d\d|janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre|période|calendrier)\b',
        "location": r'\b(?:région|département|ville|province|pays|localité|zone|territoire|situé|basé)\b',
    }
    
    # Score chaque type
    scores = {}
    for ctype, pat in patterns.items():
        matches = len(re.findall(pat, text_lower))
        if matches > 0:
            scores[ctype] = matches
    
    # Priorité : definition > person > organization > ...
    priority = ["definition", "person", "organization", "procedure", "number", "date", "location"]
    for p in priority:
        if p in scores:
            return p
    
    return "general"


def clean_chunk(text):
    """Nettoie un chunk des artefacts PDF/OCR."""
    # Supprimer les lignes vides multiples
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Supprimer les lignes trop courtes (artefacts)
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        line = line.strip()
        if len(line) < 3 and line and not line.isdigit():
            continue
        # Supprimer les séparateurs de tableaux
        if re.match(r'^[\s_\-|+]+$', line):
            continue
        # Supprimer les numéros de page isolés
        if re.match(r'^\d+\s*$', line):
            continue
        # Supprimer les artefacts unicode exotiques
        line = re.sub(r'[^\x20-\x7EÀ-ÿœŒæÆ\s]', '', line)
        cleaned.append(line)
    text = '\n'.join(cleaned)
    # Tronquer si trop long (garde 3 premières + 2 dernières phrases)
    if len(text) > MAX_CHUNK_CHARS:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if len(sentences) > 5:
            text = ' '.join(sentences[:3]) + ' [...] ' + ' '.join(sentences[-2:])
        else:
            text = text[:MAX_CHUNK_CHARS]
    return text.strip()


def generate_question(chunk_text, chunk_type, source_name, doc_index):
    """Génère une question naturelle à partir d'un chunk."""
    sujets = expand_sujets(chunk_text)
    
    if not sujets:
        # Fallback : question générique avec le nom du document
        sujet = source_name.replace('_', ' ').replace('-', ' ')[:60]
        templates = [
            f"Que contient le document sur {sujet} ?",
            f"Quelles informations trouve-t-on dans le document {sujet} ?",
            f"Peux-tu résumer le contenu du document {sujet} ?",
        ]
        return random.choice(templates)
    
    # Choisir un sujet aléatoire
    sujet = random.choice(sujets)
    
    # Prendre les templates du type, avec fallback general
    templates = QUESTION_TEMPLATES.get(chunk_type, QUESTION_TEMPLATES["general"])
    
    # Optionnellement, ajouter une référence au document source
    if random.random() < 0.3:
        ref = f"(d'après le document {source_name})"
        template = random.choice(templates)
        return f"{template} {ref}"
    
    return random.choice(templates).format(sujet=sujet)


def generate_answer(chunk_text, source_name):
    """Génère une réponse sourcée à partir du chunk."""
    # Nettoyer et résumer si nécessaire
    text = chunk_text.strip()
    if len(text) > 800:
        # Garder les 2-3 premières phrases
        sentences = re.split(r'(?<=[.!?])\s+', text)
        answer = ' '.join(sentences[:3])
        if len(sentences) > 3:
            answer += ' [...]'
    else:
        answer = text
    
    # Ajouter la source
    source_clean = source_name.replace('_', ' ').replace('-', ' ')
    return f"[Source: {source_clean}] {answer}"


def build_example(chunk_text, source_name, chunk_type, is_piege=False, wrong_source=""):
    """Construit un exemple complet au format Phi-4 ChatML."""
    clean = clean_chunk(chunk_text)
    
    if is_piege:
        # Piège : contexte d'un document, question d'un autre
        question = generate_question(clean, chunk_type, source_name, 0)
        # On garde le contexte mais la réponse dit "pas trouvé"
        answer = "Je ne trouve pas la réponse à cette question dans le contexte documentaire fourni."
        context_source = wrong_source
    else:
        question = generate_question(clean, chunk_type, source_name, 0)
        answer = generate_answer(clean, source_name)
        context_source = source_name
    
    # Contexte documentaire
    context = (
        f"CONTEXTE DOCUMENTAIRE LOCAL TROUVÉ :\n"
        f"[{context_source}]\n{clean}\n\n"
        f"INSTRUCTION : Réponds UNIQUEMENT à partir du contexte ci-dessus."
    )
    
    system_prompt = (
        "Tu es NURU, assistant cognitif local. Tu réponds UNIQUEMENT à partir des documents "
        "fournis dans le contexte. Cite tes sources avec [Source: nom]. "
        "Si la réponse ne se trouve pas dans le contexte, dis-le clairement."
    )
    
    text = (
        f"<|im_start|>system\n{system_prompt}\n\n{context}\n<|im_end|>\n"
        f"<|im_start|>user\n{question}\n<|im_end|>\n"
        f"<|im_start|>assistant\n{answer}\n<|im_end|>"
    )
    
    return text


def main():
    print("🔍 Extraction des chunks depuis l'index RAG...")
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Récupérer les documents disponibles
    cur.execute("SELECT DISTINCT source FROM chunk_hierarchy WHERE source IS NOT NULL")
    docs = [row[0] for row in cur.fetchall()]
    print(f"📚 {len(docs)} documents sources trouvés")
    
    # Récupérer les chunks groupés par document
    doc_chunks = defaultdict(list)
    cur.execute("""
        SELECT cfts.rowid, cfts.content, ch.source
        FROM chunks_fts cfts
        JOIN chunk_hierarchy ch ON cfts.rowid = ch.chunk_id
        WHERE ch.source IS NOT NULL
        ORDER BY ch.source, cfts.rowid
    """)
    
    total = 0
    for rowid, content, source in cur.fetchall():
        if content and len(content.strip()) >= MIN_CHUNK_CHARS:
            doc_chunks[source].append(content)
            total += 1
    
    print(f"📄 {total} chunks extraits, répartis sur {len(doc_chunks)} documents")
    
    # Statistiques par document
    for doc, chunks in sorted(doc_chunks.items(), key=lambda x: -len(x[1])):
        print(f"   {doc}: {len(chunks)} chunks")
    
    conn.close()
    
    if total < TARGET_TRAIN + TARGET_VALID:
        print(f"⚠️ Pas assez de chunks ({total}) pour générer {TARGET_TRAIN + TARGET_VALID} exemples")
        # Ajuster les cibles
        ratio = TARGET_TRAIN / (TARGET_TRAIN + TARGET_VALID)
        TARGET_TRAIN_ACTUAL = int(total * ratio)
        TARGET_VALID_ACTUAL = total - TARGET_TRAIN_ACTUAL
        print(f"   Cibles ajustées : {TARGET_TRAIN_ACTUAL} train, {TARGET_VALID_ACTUAL} valid")
    else:
        TARGET_TRAIN_ACTUAL = TARGET_TRAIN
        TARGET_VALID_ACTUAL = TARGET_VALID
    
    # Préparer les chunks pour la génération
    # Mélanger les chunks mais garder la trace du document
    all_chunks = []
    for doc, chunks in doc_chunks.items():
        for chunk in chunks:
            all_chunks.append((chunk, doc))
    
    random.shuffle(all_chunks)
    
    # Calculer les besoins
    n_total = TARGET_TRAIN_ACTUAL + TARGET_VALID_ACTUAL
    n_piege = int(n_total * PIEGE_RATIO)
    n_positive = n_total - n_piege
    
    print(f"\n🎯 Cibles : {n_positive} positifs + {n_piege} pièges = {n_total} total")
    
    # Génération des exemples
    examples = []
    chunk_idx = 0
    
    # Exemples positifs
    success_pos = 0
    for _ in range(n_positive):
        if chunk_idx >= len(all_chunks):
            break
        chunk_text, doc_name = all_chunks[chunk_idx]
        chunk_idx += 1
        
        chunk_type = classify_chunk(chunk_text)
        example = build_example(chunk_text, doc_name, chunk_type, is_piege=False)
        
        # Vérifier que la question n'est pas exactement identique à la précédente
        if examples and example == examples[-1]:
            continue
        
        examples.append(example)
        success_pos += 1
        
        if success_pos % 50 == 0:
            print(f"   Générés {success_pos} exemples positifs...")
    
    print(f"✅ {success_pos} exemples positifs générés")
    
    # Exemples piège
    success_piege = 0
    for _ in range(n_piege):
        if chunk_idx >= len(all_chunks):
            break
        
        # Chunk pour le contexte
        chunk_text, doc_name = all_chunks[chunk_idx]
        chunk_idx += 1
        
        # Choisir un document différent pour la question
        other_docs = [d for d in docs if d != doc_name]
        if not other_docs:
            continue
        
        wrong_doc = random.choice(other_docs)
        chunk_type = classify_chunk(chunk_text)
        example = build_example(chunk_text, doc_name, chunk_type, is_piege=True, wrong_source=wrong_doc)
        
        # Éviter les doublons
        if examples and example == examples[-1]:
            continue
        
        examples.append(example)
        success_piege += 1
    
    print(f"✅ {success_piege} exemples piège générés")
    print(f"📊 Total : {len(examples)} exemples ({success_piege/len(examples)*100:.0f}% piège)")
    
    # Division train/valid
    random.shuffle(examples)
    valid_count = min(TARGET_VALID_ACTUAL, len(examples) // 10)
    valid_examples = examples[:valid_count]
    train_examples = examples[valid_count:]
    
    print(f"\n💾 Sauvegarde...")
    
    # Écrire train.jsonl
    train_path = os.path.join(OUTPUT_DIR, "train.jsonl")
    with open(train_path, 'w', encoding='utf-8') as f:
        for ex in train_examples:
            f.write(json.dumps({"text": ex}, ensure_ascii=False) + '\n')
    print(f"   train.jsonl : {len(train_examples)} exemples")
    
    # Écrire valid.jsonl
    valid_path = os.path.join(OUTPUT_DIR, "valid.jsonl")
    with open(valid_path, 'w', encoding='utf-8') as f:
        for ex in valid_examples:
            f.write(json.dumps({"text": ex}, ensure_ascii=False) + '\n')
    print(f"   valid.jsonl : {len(valid_examples)} exemples")
    
    # Stats
    train_words = [len(ex.split()) for ex in train_examples]
    valid_words = [len(ex.split()) for ex in valid_examples]
    
    piege_train = sum(1 for ex in train_examples if "Je ne trouve pas" in ex)
    piege_valid = sum(1 for ex in valid_examples if "Je ne trouve pas" in ex)
    
    print(f"\n📊 Statistiques finales :")
    print(f"   Train : {len(train_examples)} ex ({piege_train} pièges, {piege_train/len(train_examples)*100:.0f}%)")
    print(f"   Valid : {len(valid_examples)} ex ({piege_valid} pièges, {piege_valid/len(valid_examples)*100:.0f}%)")
    print(f"   Mots/ex train : moyen={sum(train_words)/len(train_words):.0f} "
          f"min={min(train_words)} max={max(train_words)}")
    print(f"   Mots/ex valid : moyen={sum(valid_words)/len(valid_words):.0f} "
          f"min={min(valid_words)} max={max(valid_words)}")
    print(f"\n✅ Dataset prêt dans {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
