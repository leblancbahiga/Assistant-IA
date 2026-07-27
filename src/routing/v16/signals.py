"""NURU Router V16 — Niveau 2 : Intent Scoring.

C'EST LE CŒUR DU CORRECTIF.

Bug racine identifié dans l'audit de router.py (V12) :
    la décision N2 est une chaîne de `if` en cascade :
        1. has_gk and not has_rag_kw  → GENERAL
        2. has_rag_kw or is_identity  → RAG          <-- teste AVANT le web !
        3. has_web                    → WEB
    Résultat : dès qu'un mot-clé RAG (ex. "fao") est présent, la requête
    part en RAG-DOCUMENT_KEYWORD avec confidence=0.9 FIXE, sans jamais
    regarder si un marqueur temporel WEB ("actuellement") est aussi présent.
    → "Que fait actuellement la FAO ?" est routée RAG. C'est le bug exact
    signalé par l'utilisateur.

Le correctif : on calcule un score simultané pour CHAQUE intention (jamais
de court-circuit avant le niveau 1/trivial), puis on ajoute des
modificateurs contextuels ciblés :
    - TEMPORAL_BOOST : un marqueur temporel fort (actuellement, aujourd'hui,
      cours du jour...) ajoute un gros bonus à WEB, indépendamment de la
      présence d'une entité RAG dans la même phrase.
    - POSSESSIVE_BOOST : "mon/ma/mes/notre" à proximité d'un mot générique
      (rapport, projet, photosynthèse...) bascule vers RAG — c'est ce qui
      distingue "explique la photosynthèse" (GENERAL) de "explique la
      photosynthèse dans MON rapport" (RAG).
    - La décision finale n'est prise qu'au niveau Fusion (fusion.py), pas ici.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

INTENTS = ["GENERAL", "RAG", "WEB", "ACTION", "MEMORY", "TOOL", "CODE", "VISION", "CHAT", "SYSTEM"]

# ── Mots-clés pondérés par intention (poids : 3 fort / 2 modéré / 1 faible) ──
INTENT_KEYWORDS: dict[str, dict[str, int]] = {
    "RAG": {
        "cv": 3, "curriculum": 3, "vitae": 3, "lettre": 3, "motivation": 3,
        "candidature": 3, "diplome": 3, "certificat": 3, "attestation": 3,
        "rapport": 2, "presentation": 2, "projet": 2, "fichier": 2, "document": 2,
        "yarid": 3, "iamgold": 3, "walikale": 3, "beaccom": 3, "rikolto": 3,
        "iita": 3, "fao": 3, "usaid": 3, "filiere": 2,
        "etude de base": 3, "enquete": 2, "sondage": 2,
        "compte rendu": 2, "proces verbal": 2, "pv": 1,
        "qui suis-je": 4, "qui suis je": 4, "parle-moi de moi": 4, "parle moi de moi": 4,
        "mon profil": 4, "ma bio": 4, "mes infos": 4,
    },
    "GENERAL": {
        "pourquoi": 2, "comment": 2, "explique": 2, "qu'est-ce": 2, "qu'est ce": 2,
        "fonctionne": 2, "definition": 2, "signifie": 2, "veut dire": 2,
        "photosynthese": 2, "evolution": 2, "relativite": 2, "gravite": 2,
        "atome": 2, "adn": 2, "big bang": 2,
        "qui etait": 2, "quand a eu lieu": 2, "histoire": 1,
        "combien": 2, "calcul": 2, "calcule": 2, "resultat": 1,
        "addition": 2, "soustraction": 2, "multiplication": 2, "division": 2,
        "morpion": 2, "echecs": 2, "dames": 1, "sudoku": 2, "puzzle": 2,
        "ou se trouve": 2, "capitale": 2, "difference entre": 2,
    },
    "WEB": {
        "actuel": 2, "actuelle": 2, "actuellement": 3, "aujourd'hui": 3, "aujourd hui": 3,
        "en ce moment": 3, "cette annee": 2, "de nos jours": 2, "recent": 2, "recente": 2,
        "dernier": 1, "derniere": 1, "nouveau": 1, "nouvelle": 1,
        "president": 2, "premier ministre": 2, "pdg": 2, "ceo": 2, "directeur": 1,
        "prix": 2, "cours": 2, "meteo": 3, "temperature": 2,
        "actualite": 3, "actualites": 3, "news": 2, "bourse": 2, "taux": 2, "inflation": 2,
    },
    "SIMPLE": {
        "bonjour": 1, "merci": 1, "oui": 1, "non": 1, "super": 1, "bien": 1,
    },
}

# Marqueurs temporels FORTS → override WEB indépendant de la présence d'une entité RAG.
STRONG_TEMPORAL_MARKERS = (
    "actuellement", "aujourd'hui", "aujourd hui", "en ce moment", "cette annee",
    "de nos jours", "en ce moment meme", "recemment",
)
TEMPORAL_BOOST_WEIGHT = 6.0

# Marqueurs possessifs → override RAG quand accolés à un terme générique.
POSSESSIVE_MARKERS = ("mon", "ma", "mes", "notre", "nos")
POSSESSIVE_BOOST_WEIGHT = 5.0
# Termes "génériques" qui, seuls, iraient en GENERAL mais qui, avec un
# possessif à proximité, indiquent un document personnel → RAG.
GENERIC_DOC_ANCHORS = ("rapport", "projet", "photosynthese", "presentation", "etude", "analyse", "document")

_RAG_PROPER_NAME_RE = re.compile(r"qui est\s+(\S+)")


@dataclass
class ScoreVector:
    scores: dict[str, float] = field(default_factory=dict)
    hits: dict[str, list[str]] = field(default_factory=dict)  # diagnostic : quels signaux ont contribué


def _keyword_score(tokens: list[str], folded_query: str, keywords: dict[str, int]) -> tuple[float, list[str]]:
    score = 0.0
    hits: list[str] = []
    token_set = set(tokens)
    for kw, weight in keywords.items():
        if " " in kw:
            if kw in folded_query:
                score += weight * 1.5
                hits.append(kw)
        else:
            if kw in token_set:
                score += weight
                hits.append(kw)
    if tokens:
        score = score / math.sqrt(len(tokens))
    return score, hits


def _has_possessive_near_anchor(tokens: list[str]) -> bool:
    """Détecte un possessif immédiatement suivi (fenêtre de 2 mots) d'une
    ancre documentaire générique. Résout l'ambiguïté GENERAL vs RAG pour
    des phrases comme "explique la photosynthèse dans mon rapport"."""
    for i, tok in enumerate(tokens):
        if tok in POSSESSIVE_MARKERS:
            window = tokens[i + 1:i + 3]
            if any(anchor in window for anchor in GENERIC_DOC_ANCHORS):
                return True
    return False


def _identity_query(raw_query: str, folded_query: str) -> bool:
    """"Qui est [Nom Propre] ?" — si le mot qui suit "qui est" est capitalisé
    dans la requête ORIGINALE, c'est probablement une question d'identité
    personnelle (Leblanc, un collègue...) plutôt que de la culture générale."""
    m = _RAG_PROPER_NAME_RE.search(folded_query)
    if not m:
        return False
    next_word = m.group(1).rstrip("?!.,;:")
    if not next_word:
        return False
    idx = raw_query.lower().find(next_word)
    if idx < 0:
        return False
    original = raw_query[idx: idx + len(next_word)]
    return bool(original) and original[0].isupper()


def score_intents(raw_query: str, tokens: list[str], folded_query: str) -> ScoreVector:
    vec = ScoreVector()
    for intent, kw_map in INTENT_KEYWORDS.items():
        score, hits = _keyword_score(tokens, folded_query, kw_map)
        vec.scores[intent] = score
        vec.hits[intent] = hits

    # Assure la présence de toutes les intentions même sans mots-clés dédiés
    for intent in INTENTS:
        vec.scores.setdefault(intent, 0.0)
        vec.hits.setdefault(intent, [])

    # ── Modificateur 1 : override temporel (corrige le bug FAO) ──
    if any(marker in folded_query for marker in STRONG_TEMPORAL_MARKERS):
        vec.scores["WEB"] += TEMPORAL_BOOST_WEIGHT
        vec.hits["WEB"].append("temporal_override")

    # ── Modificateur 2 : override possessif (photosynthèse vs mon rapport) ──
    if _has_possessive_near_anchor(tokens):
        vec.scores["RAG"] += POSSESSIVE_BOOST_WEIGHT
        vec.hits["RAG"].append("possessive_override")

    # ── Modificateur 3 : identité personnelle ("Qui est Leblanc ?") ──
    if _identity_query(raw_query, folded_query):
        vec.scores["RAG"] += 4.0
        vec.hits["RAG"].append("identity_override")

    return vec
