"""
NURU V6 — Extracteur CV → JSON structuré (Pydantic).

Pipeline d'extraction LLM qui transforme un CV textuel brut en JSON structuré
avant indexation. Solution au problème : un CV est une base de données
relationnelle (Candidat → Expériences → Rôles → Réalisations), pas du
texte plat approprié pour du chunking vectoriel.

Usage:
    from src.cv_extractor import extract_cv, is_cv
    cv = await extract_cv(text, filename="mon_cv.pdf")
    if cv:
        print(cv.model_dump_json(indent=2))
"""

import re
import json
import logging
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Détection de CV par nom de fichier ──
# Patterns séparés car \b (word boundary) ne fonctionne pas avec underscore
CV_WORD_PATTERNS = re.compile(
    r'(?:^|[\s_\-/])(cv|curriculum|vitae|resume|profil|motivation|'
    r'lettre|candidature|cover|biographie|biography|career)'
    r'(?:$|[\s_\-\.])',
    re.IGNORECASE,
)
# Détection renforcée : CV en début/présence dans le nom
CV_NAIVE_PATTERN = re.compile(r'[_-]cv|cv[_-]', re.IGNORECASE)

# Indices textuels qui signalent un CV dans le contenu
CV_CONTENT_SIGNALS = re.compile(
    r'(expérience professionnelle|professional experience|'
    r'formation|education|diplôme|degree|compétence|skill|'
    r'résumé professionnel|career summary|profil professionnel|'
    r'poste actuel|current position|employeur|employer|'
    r'références|references|langues|languages|'
    r'mission|réalisation|achievement|'
    r'curriculum vitae)',
    re.IGNORECASE,
)


def is_cv(fname: str) -> bool:
    """Détecte si un nom de fichier correspond à un CV/document de profil.

    Utilise les mêmes patterns que le HierarchicalChunkerV2 pour la cohérence.
    """
    return bool(CV_WORD_PATTERNS.search(fname)) or bool(CV_NAIVE_PATTERN.search(fname))


def is_cv_content(text: str) -> bool:
    """Détection renforcée : vérifie si le contenu ressemble à un CV.

    Utile quand le nom de fichier n'est pas évident.
    """
    # Un CV a généralement plusieurs sections clairement identifiables
    signals = CV_CONTENT_SIGNALS.findall(text[:5000])
    return len(signals) >= 3


# ── Pydantic-like models (dataclasses pour éviter dépendance pydantic) ──

@dataclass
class Experience:
    entreprise: str = ""
    poste: str = ""
    dates: str = ""
    realisations: list[str] = field(default_factory=list)
    lieu: str = ""

    def to_dict(self) -> dict:
        return {
            "entreprise": self.entreprise,
            "poste": self.poste,
            "dates": self.dates,
            "lieu": self.lieu,
            "realisations": self.realisations,
        }


@dataclass
class Formation:
    diplome: str = ""
    etablissement: str = ""
    dates: str = ""
    mention: str = ""

    def to_dict(self) -> dict:
        return {
            "diplome": self.diplome,
            "etablissement": self.etablissement,
            "dates": self.dates,
            "mention": self.mention,
        }


@dataclass
class Competence:
    domaine: str = ""
    items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "domaine": self.domaine,
            "items": self.items,
        }


@dataclass
class CVStructure:
    nom: str = ""
    titre_poste: str = ""
    resume_global: str = ""
    experiences: list[Experience] = field(default_factory=list)
    formations: list[Formation] = field(default_factory=list)
    competences: list[Competence] = field(default_factory=list)
    langues: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    coordonnees: dict = field(default_factory=dict)
    source_file: str = ""

    def to_dict(self) -> dict:
        return {
            "nom": self.nom,
            "titre_poste": self.titre_poste,
            "resume_global": self.resume_global,
            "experiences": [e.to_dict() for e in self.experiences],
            "formations": [f.to_dict() for f in self.formations],
            "competences": [c.to_dict() for c in self.competences],
            "langues": self.langues,
            "certifications": self.certifications,
            "coordonnees": self.coordonnees,
            "source_file": self.source_file,
        }

    def model_dump_json(self, indent: int = 2) -> str:
        """Sérialisation JSON pour le stockage en DB."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str, source_file: str = "") -> Optional["CVStructure"]:
        """Reconstruit un CVStructure depuis son JSON stocké."""
        try:
            data = json.loads(json_str)
            data["source_file"] = source_file

            experiences = [
                Experience(**e) for e in data.get("experiences", [])
            ]
            formations = [
                Formation(**f) for f in data.get("formations", [])
            ]
            competences = [
                Competence(**c) for c in data.get("competences", [])
            ]

            return cls(
                nom=data.get("nom", ""),
                titre_poste=data.get("titre_poste", ""),
                resume_global=data.get("resume_global", ""),
                experiences=experiences,
                formations=formations,
                competences=competences,
                langues=data.get("langues", []),
                certifications=data.get("certifications", []),
                coordonnees=data.get("coordonnees", {}),
                source_file=source_file,
            )
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.error(f"Erreur parsing JSON CV: {e}")
            return None


# ── Prompt d'extraction structurée ──

EXTRACTION_SYSTEM_PROMPT = """Tu es un extracteur de CV spécialisé. Tu reçois le texte brut d'un CV et tu dois en extraire les informations structurées au format JSON.

Règles strictes :
1. Extrais UNIQUEMENT les informations présentes dans le texte fourni.
2. N'invente JAMAIS des informations absentes.
3. Si une information est incertaine, laisse le champ vide ("" ou []).
4. Sois exhaustif : extrais TOUTES les expériences, formations, compétences.
5. Pour les dates, conserve le format original (ex: "2018-2021", "Mars 2019").
6. Chaque réalisation doit être une phrase complète extraite textuellement.

Format de sortie JSON (à produire STRICTEMENT) :
{
    "nom": "Nom complet",
    "titre_poste": "Titre du poste actuel ou recherché",
    "resume_global": "Résumé du profil en 1-2 phrases",
    "experiences": [
        {
            "entreprise": "Nom de l'entreprise",
            "poste": "Titre du poste",
            "dates": "Période",
            "lieu": "Ville, Pays",
            "realisations": ["Réalisation 1", "Réalisation 2"]
        }
    ],
    "formations": [
        {
            "diplome": "Intitulé du diplôme",
            "etablissement": "Nom de l'établissement",
            "dates": "Année d'obtention",
            "mention": "Mention (ou vide)"
        }
    ],
    "competences": [
        {
            "domaine": "Domaine (Informatique, Management, etc.)",
            "items": ["Compétence 1", "Compétence 2"]
        }
    ],
    "langues": ["Langue 1 (Niveau)", "Langue 2 (Niveau)"],
    "certifications": ["Certification 1", "Certification 2"],
    "coordonnees": {
        "email": "",
        "telephone": "",
        "ville": "",
        "linkedin": ""
    }
}

Produis UNIQUEMENT le JSON, sans commentaires ni texte autour."""


def _extract_json_from_response(text: str) -> Optional[dict]:
    """Extrait un bloc JSON valide depuis la réponse du LLM.

    Gère les cas où le LLM ajoute du texte autour du JSON.
    """
    # Essayer de trouver un bloc ```json ... ```
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Essayer de trouver { ... } directement
    brace_match = re.search(r'\{.*\}', text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


async def extract_cv_local(text: str, filename: str = "") -> Optional[CVStructure]:
    """Extraction via LLM local (Phi-4-mini / Qwen 1.5B).

    Utilise mlx_lm.generate pour une extraction non-streaming.
    """
    try:
        import mlx.core as mx
        from mlx_lm import load, generate

        from src.config import config

        # Token tronqué si trop long pour le modèle local (1.5B/4B)
        max_chars = 12000  # ~3000 tokens pour le contexte local
        if len(text) > max_chars:
            logger.info(f"CV tronqué de {len(text)} → {max_chars} caractères pour extraction locale")
            text = text[:max_chars]

        prompt = f"[INST] {EXTRACTION_SYSTEM_PROMPT}\n\nTexte du CV :\n{text}\n\n[/INST]"

        model_id = config.local_model
        resolved_path = config.get_model_path(model_id)

        logger.info(f"Extraction CV locale avec {model_id}...")
        model, tokenizer = load(resolved_path)

        response = generate(
            model, tokenizer,
            prompt=prompt,
            max_tokens=1500,
        )

        data = _extract_json_from_response(response)
        if data:
            cv = _build_cv_structure(data, filename)
            logger.info(f"✅ CV extrait localement : {cv.nom or 'inconnu'} "
                        f"({len(cv.experiences)} expériences)")
            return cv

        logger.warning("Échec extraction JSON depuis réponse locale")
        return None

    except ImportError as e:
        logger.error(f"mlx_lm non disponible : {e}")
        return None
    except Exception as e:
        logger.error(f"Erreur extraction CV locale : {e}")
        return None


async def extract_cv_cloud(text: str, filename: str = "") -> Optional[CVStructure]:
    """Extraction via LLM cloud (Groq/OpenRouter).

    Plus fiable que le local pour l'extraction structurée.
    """
    try:
        import httpx

        from src.config import config

        groq_key = config.groq_key
        if not groq_key:
            logger.error("Clé Groq non disponible pour extraction CV cloud")
            return None

        # Troncature pour respecter la fenêtre de contexte cloud
        max_chars = 24000  # ~6000 tokens
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
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": f"Texte du CV :\n{text}"},
            ],
            "temperature": 0.1,
            "max_tokens": 2000,
            "response_format": {"type": "json_object"},
        }

        logger.info("Extraction CV via Groq (llama-3.1-8b-instant)...")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()

        content = result["choices"][0]["message"]["content"]

        # Essayer JSON direct, puis fallback regex
        data = None
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            data = _extract_json_from_response(content)

        if not data:
            logger.warning("Impossible d'extraire le JSON de la réponse Groq")
            return None

        cv = _build_cv_structure(data, filename)
        logger.info(f"✅ CV extrait cloud : {cv.nom or 'inconnu'} "
                    f"({len(cv.experiences)} expériences, {len(cv.competences)} domaines)")
        return cv

    except ImportError as e:
        logger.error(f"httpx non disponible : {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON invalide depuis Groq (fallback échoué) : {e}")
        return None
    except Exception as e:
        logger.error(f"Erreur extraction CV cloud : {e}")
        return None


def _build_cv_structure(data: dict, filename: str = "") -> CVStructure:
    """Construit un CVStructure à partir d'un dict JSON.

    Gère les imprécisions du LLM (noms de champs variés).
    """
    # Mapping des noms de champs possibles (le LLM peut varier)
    nom = (data.get("nom") or data.get("name") or data.get("full_name")
           or data.get("candidat") or data.get("candidate") or "")
    titre = (data.get("titre_poste") or data.get("poste_actuel")
             or data.get("current_position") or data.get("title") or "")
    resume = (data.get("resume_global") or data.get("profil")
              or data.get("summary") or data.get("profile") or "")

    experiences_raw = (data.get("experiences") or data.get("experience")
                       or data.get("experiences_professionnelles")
                       or data.get("work_experience") or [])

    formations_raw = (data.get("formations") or data.get("formation")
                      or data.get("education") or [])

    competences_raw = (data.get("competences") or data.get("competences_cles")
                       or data.get("skills") or data.get("competences_techniques")
                       or [])

    langues = (data.get("langues") or data.get("languages") or [])
    certifications = (data.get("certifications") or data.get("certification") or [])
    coordonnees = (data.get("coordonnees") or data.get("coordonnées")
                   or data.get("contact") or {})

    # Construire les objets typés
    experiences = []
    for e in experiences_raw:
        if isinstance(e, dict):
            experiences.append(Experience(
                entreprise=e.get("entreprise") or e.get("company") or e.get("employeur") or "",
                poste=e.get("poste") or e.get("title") or e.get("role") or "",
                dates=e.get("dates") or e.get("periode") or e.get("date") or "",
                lieu=e.get("lieu") or e.get("location") or "",
                realisations=e.get("realisations") or e.get("achievements")
                         or e.get("responsibilities") or [],
            ))

    formations = []
    for f in formations_raw:
        if isinstance(f, dict):
            formations.append(Formation(
                diplome=f.get("diplome") or f.get("degree") or f.get("diploma") or "",
                etablissement=f.get("etablissement") or f.get("school")
                             or f.get("institution") or f.get("university") or "",
                dates=f.get("dates") or f.get("year") or f.get("annee") or "",
                mention=f.get("mention") or f.get("grade") or "",
            ))

    competences = []
    for c in competences_raw:
        if isinstance(c, dict):
            competences.append(Competence(
                domaine=c.get("domaine") or c.get("category") or c.get("area") or "",
                items=c.get("items") or c.get("competences") or c.get("skills") or [],
            ))
        elif isinstance(c, str):
            # Cas simple : juste une liste de compétences sans catégorie
            competences.append(Competence(domaine="Général", items=[c]))

    return CVStructure(
        nom=nom,
        titre_poste=titre,
        resume_global=resume,
        experiences=experiences,
        formations=formations,
        competences=competences,
        langues=langues if isinstance(langues, list) else [],
        certifications=certifications if isinstance(certifications, list) else [],
        coordonnees=coordonnees if isinstance(coordonnees, dict) else {},
        source_file=filename,
    )


async def extract_cv(text: str, filename: str = "", prefer_cloud: bool = True) -> Optional[CVStructure]:
    """Point d'entrée principal : extraction CV avec fallback.

    Stratégie :
    1. Cloud (Groq) — plus fiable, JSON structuré garanti
    2. Local (Phi-4-mini/Qwen) — fallback si pas de cloud
    """
    if prefer_cloud:
        cv = await extract_cv_cloud(text, filename)
        if cv:
            return cv
        logger.info("Cloud indisponible, tentative locale...")

    cv = await extract_cv_local(text, filename)
    return cv


def format_cv_for_context(cv: CVStructure) -> str:
    """Formate un CV structuré en texte lisible pour injection dans le contexte RAG.

    Produit un format clair et complet que le LLM peut exploiter facilement.
    """
    parts = []
    parts.append(f"=== CV : {cv.nom} ===")
    if cv.titre_poste:
        parts.append(f"Poste : {cv.titre_poste}")
    if cv.resume_global:
        parts.append(f"Résumé : {cv.resume_global}")

    if cv.experiences:
        parts.append("\nExpériences professionnelles :")
        for exp in cv.experiences:
            parts.append(f"• {exp.poste} @ {exp.entreprise} ({exp.dates})")
            if exp.lieu:
                parts.append(f"  Lieu : {exp.lieu}")
            for r in exp.realisations:
                parts.append(f"  - {r}")

    if cv.formations:
        parts.append("\nFormation :")
        for f in cv.formations:
            line = f"• {f.diplome} - {f.etablissement} ({f.dates})"
            if f.mention:
                line += f" — {f.mention}"
            parts.append(line)

    if cv.competences:
        parts.append("\nCompétences :")
        for comp in cv.competences:
            items = ", ".join(comp.items)
            parts.append(f"• {comp.domaine} : {items}")

    if cv.langues:
        parts.append(f"\nLangues : {', '.join(cv.langues)}")

    if cv.certifications:
        parts.append(f"\nCertifications : {', '.join(cv.certifications)}")

    if cv.coordonnees:
        coords = []
        for k, v in cv.coordonnees.items():
            if v:
                coords.append(f"{k}: {v}")
        if coords:
            parts.append(f"\nContact : {' | '.join(coords)}")

    return "\n".join(parts)
