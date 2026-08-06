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
    "Tu réponds en te basant en PRIORITÉ sur les documents fournis ci-dessous.\n"
    "Tu cites tes sources avec [Source: nom_fichier] quand tu utilises le document.\n"
    "Si l'information n'est pas dans les documents, réponds honnêtement avec tes "
    "connaissances ou dis-le clairement.\n"
    "Tu fournis des réponses COMPLÈTES, STRUCTURÉES et DÉTAILLÉES : "
    "développe chaque point, utilise des listes et des titres quand c'est pertinent."
)

HEADER = """\
# TÂCHE : Générer un dataset d'entraînement LoRA de QUALITÉ pour NURU

Tu es un expert en création de datasets pour le fine-tuning d'un assistant IA
agricole local (NURU, modèle Phi-4-mini). Tu produis des paires question/réponse
à partir des documents ci-dessous.

## Contexte
NURU est un assistant RAG qui répond à partir des documents personnels
de l'utilisateur (rapports FAO, études BEACCOM, CV, propositions de projets
agricoles en RDC). Le dataset sert à entraîner un adaptateur LoRA à :
citer les sources, répondre avec précision à partir des documents, produire
des réponses RICHES et STRUCTURÉES. Les réponses répondent TOUJOURS
directement à la question — jamais de commentaire sur le contexte ou la réponse.

## RÈGLES DE QUALITÉ (critiques)
0. INTERDICTION ABSOLUE DE META-DISCOURS : la réponse assistant répond DIRECTEMENT
   à la question. JAMAIS de phrases qui parlent de la réponse, du contexte ou du
   processus au lieu de répondre. Interdit, entre autres :
   - « L'extrait fournit des éléments précis pour répondre à la question, mais… »
   - « La réponse doit rester limitée au contenu fourni… »
   - « J'ai limité la recherche au contenu de l'extrait… »
   - « Il ne serait donc pas fiable d'utiliser des connaissances générales… »
   - « Le contexte fournit également des éléments précis… »
   Chaque réponse commence DIRECTEMENT par l'information demandée
   (ex: « Le projet BEACCOM vise… », « L'expérience de Leblanc comprend… »).
   Une réponse piège se limite à : « Je ne trouve pas cette information dans
   les documents fournis. » — sans justification ni développement.

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

3. FIDÉLITÉ : base-toi sur les documents fournis en priorité. Si l'information
   n'y est pas, réponds honnêtement avec tes connaissances ou indique-le —
   sans commentaire meta-discursif sur le processus de réponse.

4. QUESTIONS PIÈGES (15 à 18% du total) :
   - Le contexte est celui d'un document A (ex: rapport sur le riz).
   - La question porte sur un sujet B ABSENT de ce contexte.
   - Réponse = refus bref ET direct :
     « Je ne trouve pas cette information dans les documents fournis. »
     — une seule phrase, SANS justification, SANS développement.

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
    """Extrait des DOCUMENTS SUBSTANTIELS en regroupant les chunks par source.

    Le problème : les chunks FTS font ~120 mots en médiane — trop courts pour
    générer une réponse de 300-800 mots. On regroupe donc les chunks d'une même
    source pour reconstituer un document de 1500-3000+ caractères, et on filtre
    le bruit (fichiers de debug, code, audit markdown, etc.).
    """
    # Extensions de documents réels (PDF/DOCX/XLSX) — exclut code/markdown debug
    DOC_EXTS = (".pdf", ".docx", ".doc", ".xlsx", ".csv", ".txt")
    NOISE_KEYWORDS = (
        "audit_kernel", "deps_debug", "reindex_checkpoint", "workspace.xml",
        ".venv/", "node_modules", "package.json", "requirements.txt",
        "test_", ".pyc", "backup_", "NURU-V5", "nuru_brain",
    )

    conn = sqlite3.connect(INDEX_DB)
    rows = conn.execute(
        "SELECT cfts.content, ch.source, ch.section_title "
        "FROM chunks_fts cfts "
        "JOIN chunk_hierarchy ch ON cfts.rowid = ch.chunk_id "
        "WHERE ch.source IS NOT NULL AND length(cfts.content) > 50 "
        "ORDER BY ch.source, cfts.rowid",
    ).fetchall()
    conn.close()

    # Grouper par source
    grouped: dict[str, list[str]] = {}
    sections: dict[str, str] = {}
    for content, source, section in rows:
        sl = source.lower()
        # Filtrer le bruit
        if any(n in sl for n in NOISE_KEYWORDS):
            continue
        if not source.lower().endswith(DOC_EXTS) and "." not in source:
            continue
        grouped.setdefault(source, []).append(content.strip())
        if section and source not in sections:
            sections[source] = section

    # Construire les "documents" : concaténer les chunks d'une même source
    docs = []
    for source, chunks in grouped.items():
        if len(chunks) < 2:
            continue  # trop peu de matière
        full = "\n\n".join(chunks)
        if len(full) < 800:
            continue  # document trop court
        # Limiter à 3000 chars par document (garde la taille raisonnable)
        if len(full) > 3000:
            full = full[:3000] + "\n[… fin du document tronquée …]"
        docs.append({
            "content": full,
            "source": source,
            "section": sections.get(source, ""),
        })
        if len(docs) >= max_chunks:
            break

    return docs


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
        "- Génère 15 à 18% de questions PIÈGES (contexte A + question B absente → refus bref).\n"
        "- Varie les questions : objectifs, défis, résultats, acteurs, processus, chiffres, localisation.\n"
        "- INTERDIT : tout meta-discours (commenter le contexte, la réponse ou le "
        "processus). Chaque réponse commence par l'information demandée.\n"
        f"- Utilise ce SYSTEM_PROMPT en tête de CHAQUE exemple :\n{SYSTEM_PROMPT}\n"
        "- Respecte STRICTEMENT le format JSON Lines {\"messages\": [...]}.\n"
        "- Écris UNIQUEMENT les lignes JSON valides, sans texte autour ni ```json.\n"
    )

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text("\n".join(parts), encoding="utf-8")
    print(f"✅ {len(chunks)} documents substantiels extraits (chunks groupés par source)")
    print(f"📄 Fichier prêt : {OUT_FILE}")
    print("   → Copie son contenu dans une IA (Claude/ChatGPT/DeepSeek).")
    print("   → Place les lignes JSON générées dans data/adapters/rag/train.jsonl (+ valid.jsonl).")


if __name__ == "__main__":
    main()