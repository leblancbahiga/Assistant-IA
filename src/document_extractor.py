"""
NURU V6 — Extracteur universel de documents structurés (LLM).

Pour chaque document indexé (CV, rapport, lettre, article, note, etc.),
on extrait une fiche structurée : type, titre, résumé, sujets, entités.

Cela remplace le résumé extractif basique (premières lignes) par un
résumé LLM de qualité, stocké dans une table SQLite `doc_structured`
accessible par le RAG lors des requêtes pertinentes.

Usage:
    from src.document_extractor import extract_document, detect_doc_type
    meta = await extract_document(text, "rapport_riz_2024.pdf")
    print(meta.summary)
    print(meta.key_topics)
"""
import re
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Détection du type de document ──
# Patterns avec \b pour les mots isolés + détection naive pour underscores
DOC_TYPE_PATTERNS = {
    "CV": re.compile(
        r'(?:^|[\s_\-/])(cv|curriculum|vitae|resume|career)(?:$|[\s_\-\.\d])',
        re.IGNORECASE,
    ),
    "lettre_motivation": re.compile(
        r'(?:^|[\s_\-/])(motivation|candidature|cover)(?:$|[\s_\-\.\d])',
        re.IGNORECASE,
    ),
    "rapport": re.compile(
        r'(?:^|[\s_\-/])(rapport|report|analyse|étude|analysis|survey|baseline|assessment|'
        r'review)(?:$|[\s_\-\.\d])',
        re.IGNORECASE,
    ),
    "article": re.compile(
        r'(?:^|[\s_\-/])(article|publication|paper|journal|revue|newsletter)'
        r'(?:$|[\s_\-\.\d])',
        re.IGNORECASE,
    ),
    "note": re.compile(
        r'(?:^|[\s_\-/])(note|notes|memo|meeting|réunion|summary)'
        r'(?:$|[\s_\-\.\d])',
        re.IGNORECASE,
    ),
    "presentation": re.compile(
        r'(?:^|[\s_\-/])(presentation|slide|deck|ppt|powerpoint|présentation|'
        r'exposé)(?:$|[\s_\-\.\d])',
        re.IGNORECASE,
    ),
    "technique": re.compile(
        r'(?:^|[\s_\-/])(guide|tutorial|manuel|documentation|spec|spécification|'
        r'technical)(?:$|[\s_\-\.\d])',
        re.IGNORECASE,
    ),
    "formulaire": re.compile(
        r'(?:^|[\s_\-/])(formulaire|form|questionnaire|survey|application)'
        r'(?:$|[\s_\-\.\d])',
        re.IGNORECASE,
    ),
}

# Détection naive pour underscores (ex: mon_cv.pdf, cv_anglais.pdf)
DOC_TYPE_NAIVE = {
    "CV": re.compile(r'[_-]cv|cv[_-]|profil|lettre_motivation|cover_letter', re.IGNORECASE),
    "rapport": re.compile(r'rapport_|_rapport', re.IGNORECASE),
    "note": re.compile(r'note_|_note|compte_rendu|compte-rendu', re.IGNORECASE),
}


def detect_doc_type(filename: str, text: str = "") -> str:
    """Détecte le type de document par le nom de fichier puis le contenu."""
    combined = filename
    if text:
        combined += " " + text[:2000]

    for doc_type, pattern in DOC_TYPE_PATTERNS.items():
        if pattern.search(combined):
            return doc_type

    for doc_type, pattern in DOC_TYPE_NAIVE.items():
        if pattern.search(filename):
            return doc_type

    return "document"


# ── Modèle de métadonnées universel ──

@dataclass
class DocumentMetadata:
    """Métadonnées structurées pour n'importe quel document."""
    source_file: str = ""
    doc_type: str = "document"
    title: str = ""
    summary: str = ""
    key_topics: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)  # personnes, organisations
    dates_mentioned: list[str] = field(default_factory=list)
    language: str = ""
    word_count: int = 0
    structured_json: str = ""  # JSON complet pour stockage

    def to_dict(self) -> dict:
        return {
            "doc_type": self.doc_type,
            "title": self.title,
            "summary": self.summary,
            "key_topics": self.key_topics,
            "entities": self.entities,
            "dates_mentioned": self.dates_mentioned,
            "language": self.language,
            "word_count": self.word_count,
        }

    def model_dump_json(self, indent: int = 2) -> str:
        """Sérialisation pour stockage en DB."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def format_for_context(self) -> str:
        """Formate les métadonnées en texte lisible pour injection RAG."""
        lines = [f"=== FICHE : {self.title or self.source_file} ==="]
        lines.append(f"Type : {self.doc_type}")
        if self.summary:
            lines.append(f"Résumé : {self.summary}")
        if self.key_topics:
            lines.append(f"Sujets : {', '.join(self.key_topics)}")
        if self.entities:
            lines.append(f"Entités : {', '.join(self.entities)}")
        if self.dates_mentioned:
            lines.append(f"Dates : {', '.join(self.dates_mentioned)}")
        if self.language:
            lines.append(f"Langue : {self.language}")
        lines.append(f"Mots : {self.word_count}")
        return "\n".join(lines)


# ── Prompt d'extraction générique ──

GENERIC_EXTRACTION_PROMPT = """Tu es un extracteur de métadonnées de documents. Tu reçois le texte brut d'un document et tu dois en extraire les informations structurées au format JSON.

Règles strictes :
1. Extrais UNIQUEMENT les informations présentes dans le texte.
2. N'invente JAMAIS des informations absentes. Laisse les champs vides si incertain.
3. Sois concis : résumé en 2-3 phrases max, sujets en 3-5 mots-clés max.

Format JSON à produire STRICTEMENT :
{
    "title": "Titre du document (ou première phrase significative)",
    "summary": "Résumé du document en 2-3 phrases",
    "key_topics": ["Sujet 1", "Sujet 2", "Sujet 3"],
    "entities": ["Personne ou organisation mentionnée"],
    "dates_mentioned": ["Date ou période mentionnée"],
    "language": "Français|Anglais|... (langue principale du document)"
}

Produis UNIQUEMENT le JSON, sans commentaires."""


EXTRACTION_SYSTEM_PROMPT = """Tu es un assistant spécialisé dans l'extraction de métadonnées de documents.
Pour chaque document, tu dois identifier :
- Le TITRE : le titre exact ou déduit
- Le RÉSUMÉ : 2-3 phrases qui capturent l'essentiel
- Les SUJETS CLÉS : 3-5 mots-clés ou thèmes principaux
- Les ENTITÉS : personnes, organisations, lieux mentionnés
- Les DATES : dates ou périodes clés mentionnées
- La LANGUE : langue principale du document

Sois précis et concis. Ne fabrique jamais d'informations absentes."""


def _extract_json(text: str) -> Optional[dict]:
    """Extrait un bloc JSON de la réponse du LLM."""
    # Essayer bloc ```json ... ```
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Essayer { ... }
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


async def extract_generic_cloud(text: str, filename: str = "") -> Optional[DocumentMetadata]:
    """Extraction générique via Groq — pour tout type de document."""
    try:
        import httpx
        import asyncio
        from src.config import config

        groq_key = config.groq_key
        if not groq_key:
            logger.warning("Clé Groq non disponible pour extraction générique")
            return None

        # Troncature pour la fenêtre cloud
        max_chars = 20000
        if len(text) > max_chars:
            text = text[:max_chars]

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {groq_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT
                 + "\n\nFormat JSON attendu : {\"title\": str, \"summary\": str, "
                 "\"key_topics\": [str], \"entities\": [str], "
                 "\"dates_mentioned\": [str], \"language\": str}"},
                {"role": "user", "content": f"Document : {filename}\n\n{text[:15000]}"},
            ],
            "temperature": 0.1,
            "max_tokens": 800,
            "response_format": {"type": "json_object"},
        }

        logger.info("Extraction générique via Groq (llama-3.1-8b-instant)...")
        async with httpx.AsyncClient(timeout=60.0) as client:
            for attempt in range(3):
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 429 and attempt < 2:
                    wait = 2 ** (attempt + 1)  # 2s, 4s
                    logger.warning(f"Rate limit Groq, attente {wait}s...")
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                result = resp.json()
                break

        content = result["choices"][0]["message"]["content"]

        # Essayer JSON direct, puis fallback regex
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            data = _extract_json(content)

        if not data:
            logger.warning(f"Impossible d'extraire le JSON de la réponse Groq pour {filename}")
            return None

        doc_type = detect_doc_type(filename, text)
        meta = DocumentMetadata(
            source_file=filename,
            doc_type=doc_type,
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            key_topics=data.get("key_topics", []),
            entities=data.get("entities", []),
            dates_mentioned=data.get("dates_mentioned", []),
            language=data.get("language", ""),
            word_count=len(text.split()),
        )
        meta.structured_json = meta.model_dump_json()
        logger.info(f"📄 {doc_type} extrait : {meta.title or filename}")
        return meta

    except Exception as e:
        logger.warning(f"⚠️ Extraction générique échouée pour {filename}: {e}")
        return None


async def extract_document(text: str, filename: str = "",
                           prefer_cloud: bool = True) -> Optional[DocumentMetadata]:
    """Point d'entrée principal : extraction universelle de document.

    Détecte automatiquement le type et adapte l'extraction.
    Pour les CV, utilise l'extraction CV spécialisée.
    Pour tous les autres documents, utilise l'extraction générique.
    """
    doc_type = detect_doc_type(filename, text)
    logger.info(f"📋 Extraction document : {filename} (type={doc_type})")

    # CV → extraction spécialisée avec CVStructure
    if doc_type == "CV":
        from src.cv_extractor import extract_cv, CVStructure, format_cv_for_context
        cv = await extract_cv(text, filename, prefer_cloud=prefer_cloud)
        if cv:
            meta = DocumentMetadata(
                source_file=filename,
                doc_type="CV",
                title=cv.nom or filename,
                summary=cv.resume_global or "",
                key_topics=[e.poste for e in cv.experiences[:3]] +
                           [c.domaine for c in cv.competences[:3]],
                entities=[e.entreprise for e in cv.experiences] +
                         [f.etablissement for f in cv.formations],
                dates_mentioned=[e.dates for e in cv.experiences if e.dates] +
                                [f.dates for f in cv.formations if f.dates],
                language="Français",
                word_count=len(text.split()),
            )
            # Stocker le CV complet dans structured_json pour usage avancé
            meta.structured_json = cv.model_dump_json()
            logger.info(f"✅ CV extrait : {cv.nom} "
                        f"({len(cv.experiences)} expériences)")
            return meta

    # Tous les autres documents → extraction générique
    if prefer_cloud:
        meta = await extract_generic_cloud(text, filename)
        if meta:
            return meta

    # Fallback extractif simple si LLM indisponible
    logger.info(f"Fallback extractif pour {filename}")
    lines = text.strip().split("\n")
    meaningful = [l.strip() for l in lines if len(l.strip()) > 30]
    summary = "\n".join(meaningful[:5]) if meaningful else text[:500]

    return DocumentMetadata(
        source_file=filename,
        doc_type=doc_type,
        title=filename,
        summary=summary[:1000],
        word_count=len(text.split()),
    )


def format_doc_for_context(meta: DocumentMetadata) -> str:
    """Formate les métadonnées structurées pour injection RAG."""
    if meta.doc_type == "CV" and meta.structured_json:
        # Pour les CV, essayer de charger le JSON complet pour un format riche
        try:
            from src.cv_extractor import CVStructure, format_cv_for_context
            cv = CVStructure.from_json(meta.structured_json, meta.source_file)
            if cv:
                return format_cv_for_context(cv)
        except Exception:
            pass
    return meta.format_for_context()
