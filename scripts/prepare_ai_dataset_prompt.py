#!/usr/bin/env python3
"""Génère un fichier d'instructions PRÊT à donner à une IA externe (Claude, ChatGPT,
DeepSeek…) pour qu'elle produise un dataset LoRA de QUALITÉ pour NURU.

Usage:
    python scripts/prepare_ai_dataset_prompt.py [--max_chunks 60]

Sortie:
    data/ai_dataset_task.txt   ← le fichier à copier/coller dans une autre IA
"""

import json, os, sys, sqlite3
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

INDEX_DB = "indexes/nuru.db"
OUT_FILE = Path("data/ai_dataset_task.txt")

SYSTEM_PROMPT = (
    "Tu es NURU, assistant IA expert en agronomie et chaînes de valeur agricoles.\n"
    "Tu réponds UNIQUEMENT à partir des documents fournis ci-dessous.\n"
    "Tu cites tes sources avec [Source: nom_fichier].\n"
    "Si l'information n'est pas dans les documents, tu dis que tu ne trouves pas.\n"
    "Tu fournis des réponses COMPLÈTES, STRUCTURÉES et DÉTAILLÉES : "
    "développe chaque point, utilise des listes et des titres quand c'est pertinent."
)

HEADER = """\
# TÂCHE : Générer un dataset d'entraînement LoRA de QUALITÉ pour NURU

Tu es un expert en création de datasets pour le fine-tuning d'un assistant IA
agricole local (NURU, modèle Phi-4-mini). Tu produis des paires question/réponse
à partir des documents ci-dessous.

## Contexte
NURU est un assistant RAG qui répond UNIQUEMENT à partir des documents personnels
de l'utilisateur (rapports FAO, études BEACCOM, CV, propositions de projets
agricoles en RDC). Le dataset sert à entraîner un adaptateur LoRA apprendre :
citer les sources, refuser hors-contexte, produire des réponses RICHES et STRUCTURÉES.

## RÈGLES DE QUALITÉ (critiques)
1. RÉPONSES LONGUES et STRUCTURÉES (300 à 800 mots) :
   - Introduction (1-2 phrases)
   - 2 à 4 SECTIONS avec titres en gras (##)
   - LISTES À PUCES, tableaux ou paragraphes pour détailler
   - EXEMPLES concrets issus du contexte
   - Conclusion (1-2 phrases)
   Jamais une réponse d'une seule phrase ou d'un paragraphe court.

2. CITATIONS : après chaque information factuelle importante, cite :
   [Source: nom_du_fichier]
   Exemple : "Le projet PASA-NK vise la sécurité alimentaire [Source: rapport.pdf]."
   N'invente JAMAIS une information hors contexte.

3. FIDÉLITÉ : réponds UNIQUEMENT avec ce qui est dans les documents fournis.

4. QUESTIONS PIÈGES (15 à 18% du total) :
   - Le contexte est celui d'un document A (ex: rapport sur le riz).
   - La question porte sur un sujet B ABSENT de ce contexte.
   - Réponse = refus clair :
     "Je ne trouve pas l'information demandée dans les documents fournis."

## FORM DE SORTIE EXACT (JSON Lines, un objet par ligne, clé "messages")
Chaque ligne est un objet JSON :
{"messages": [
  {"role": "system", "content": "<SYSTEM_PROMPT ci-dessus>"},
  {"role": "user", "content": "[Document N] (Source: fichier)\n<chunk>\n\nQuestion : <question>"},
  {"role": "assistant", "content": "<réponse longue structurée avec [Source: ...]>"}
]}
Écris UNIQUEMENT des lignes JSON valides, sans texte autour, sans ```json.
"""

EXAMPLE = {
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "[Document 1] (Source: rapport_beaccom.pdf)\nLe projet BEACCOM vise l'analyse de la vulnérabilité climatique au Nord-Kivu et propose des stratégies d'adaptation pour les communautés agricoles.\n\nQuestion : Quels sont les objectifs du projet BEACCOM ?"},
        {"role": "assistant", "content": "[Source: rapport_beaccom.pdf]\nLe projet BEACCOM vise plusieurs objectifs stratégiques pour améliorer la résilience des communautés agricoles au Nord-Kivu, en RDC.\n\n## 1. Analyse de la vulnérabilité climatique\nLe projet évalue l'impact des changements climatiques sur les moyens d'existence locaux, notamment les effets des sécheresses et inondations sur les récoltes.\n\n## 2. Stratégies d'adaptation\nLe projet introduit des variétés résistantes et la diversification des cultures pour réduire la dépendance à une seule culture.\n\n## 3. Renforcement des capacités\nLes communautés locales sont formées aux techniques agricoles durables.\n\nEn conclusion, le projet adopte une approche holistique pour sécuriser les moyens d'existence face au climat changeant."},
    ]
}


def load_chunks(max_chunks: int = 60) -> list[dict]:
    conn = sqlite3.connect(INDEX_DB)
    rows = conn.execute(
        "SELECT cfts.content, ch.source, ch.section_title "
        "FROM chunks_fts cfts "
        "JOIN chunk_hierarchy ch ON cfts.rowid = ch.chunk_id "
        "WHERE ch.source IS NOT NULL AND length(cfts.content) > 80 "
        "ORDER BY RANDOM() LIMIT ?",
        (max_chunks,),
    ).fetchall()
    conn.close()
    return [
        {"content": c.strip(), "source": s, "section": t or ""}
        for c, s, t in rows
        if c and c.strip()
    ]


def main():
    max_chunks = 60
    if "--max_chunks" in sys.argv:
        max_chunks = int(sys.argv[sys.argv.index("--max_chunks") + 1])

    chunks = load_chunks(max_chunks)
    if not chunks:
        print(f"❌ Aucun chunk trouvé dans {INDEX_DB}")
        print("   L'index existe-t-il ? Lance d'abord scripts/reindex_all.py.")
        return

    parts = []
    parts.append(HEADER)
    parts.append("")

    # Documents sources
    parts.append("=" * 60)
    parts.append(f"# {len(chunks)} DOCUMENTS SOURCES (pour générer les paires)")
    parts.append("=" * 60)
    for i, ch in enumerate(chunks, 1):
        parts.append("")
        parts.append(f"## [Document {i}] — Source: {ch['source']}")
        if ch["section"]:
            parts.append(f"Section: {ch['section']}")
        content = ch["content"]
        if len(content) > 1200:
            content = content[:1200] + "\n[… fin du chunk tronquée …]"
        parts.append(content)
        parts.append("-" * 60)

    # Exemple de format
    parts.append("")
    parts.append("=" * 60)
    parts.append("# EXEMPLE DE FORMAT ATTENDU")
    parts.append("=" * 60)
    parts.append(json.dumps(EXAMPLE, ensure_ascii=False, indent=2))

    # Consigne finale
    parts.append("")
    parts.append("=" * 60)
    parts.append("# CONSIGNE FINALE")
    parts.append("=" * 60)
    parts.append(
        f"\nProduis un dataset de qualité à partir des {len(chunks)} documents ci-dessus :\n"
        "- Génère 100 à 300 paires POSITIVES (question + réponse longue sourcée de 300-800 mots).\n"
        "- Génère 15 à 18% de questions PIÈGES (contexte A + question B absente → refus).\n"
        "- Varie les questions : objectifs, défis, résultats, acteurs, processus, chiffres, localisation.\n"
        f"- Utilise ce SYSTEM_PROMPT en tête de CHAQUE exemple :\n{SYSTEM_PROMPT}\n"
        "- Respecte STRICTEMENT le format JSON Lines {\"messages\": [...]}.\n"
        "- Écris UNIQUEMENT les lignes JSON valides, sans texte autour ni ```json.\n"
    )

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text("\n".join(parts), encoding="utf-8")
    print(f"✅ {len(chunks)} chunks extraits")
    print(f"📄 Fichier prêt : {OUT_FILE}")
    print("   → Copie son contenu dans une IA (Claude/ChatGPT/DeepSeek).")
    print("   → Place les lignes JSON générées dans data/adapters/rag/train.jsonl (+ valid.jsonl).")


if __name__ == "__main__":
    main()