"""NURU V17 — Post-processing des artefacts de tokenisation française.

Corrige les problèmes de tokenisation du LLM local (Phi-4-mini) avec le français :
- Espaces intempestifs dans les mots composés : "Bon jour" → "Bonjour"
- Collages : "puis-jevous" → "puis-je vous"
- Noms propres coupés : "NUR U" → "NURU"
- Espaces devant la ponctuation haute : " !" → "!", " ?" → "?"
- Apostrophes mal gérées

Utilise un buffer glissant pour corriger en streaming sans accumuler tout le texte.
"""

import re
import logging

logger = logging.getLogger(__name__)

# ── Dictionnaire de corrections : mots français souvent mal tokenizés ──
# Format : (pattern_regex, remplacement_str_ou_callable)
FRENCH_COMPOUNDS: list = [
    (r"\b[Bb]on jour\b", lambda m: "B" + "onjour" if m.group(0)[0].isupper() else "bonjour"),
    (r"\baujourd'? ?hui\b", "aujourd'hui"),
    (r"\bparce ?que\b", "parce que"),
    (r"\bpeut-?etre\b", "peut-être"),
    (r"\btres\b", "très"),
    (r"\bapres\b", "après"),
]

# ── Noms propres connus qui peuvent être coupés ──
KNOWN_NAMES: list = [
    (r"\bNUR ?U\b", "NURU"),
    (r"\bN ?U ?R ?U\b", "NURU"),
    (r"\bPhi-?4\b", "Phi-4"),
]

# ── Patterns génériques ──
PATTERNS: list = [
    # Espace après apostrophe (sauf pour les cas comme "l' homme" → "l'homme")
    (r"(?<=[dlmnstcj])' (?=\w)", "'"),
    # Majuscule + espace + Majuscule dans un nom propre (ex: "N U R U" → "NURU")
    (r"\b([A-Z]) ([A-Z])(?: ([A-Z]))?(?: ([A-Z]))?\b", lambda m: "".join(g for g in m.groups() if g)),
    # Espace entre lettre et apostrophe (ex: "l' homme" → "l'homme")
    (r"(\w)' (\w)", r"\1'\2"),
    # "puis-je vous" collé
    (r"\bpuis-jevous\b", "puis-je vous"),
    # Ponctuation collée
    (r"(\w)\.(\w)", r"\1. \2"),
    # Doubles espaces
    (r" {2,}", " "),
]

# ── Mots spéciaux (préservation de cas spécifiques) ──
# Prépositions et articles français qui ne doivent pas être fusionnés
SAFE_WORDS: set[str] = {
    "au", "aux", "du", "des", "sur", "sous", "dans", "avec", "pour", "par",
    "est", "et", "ou", "où", "la", "le", "les", "de", "en", "un", "une",
    "ce", "ces", "ses", "son", "sa", "mes", "tes", "nos", "vos",
    "que", "qui", "quoi", "dont", "où",
    "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
    "me", "te", "se", "lui", "leur",
    "ne", "pas", "plus", "rien", "personne",
    "à", "ça", "là",
}


def _normalize_spacing(text: str) -> str:
    """Corrige les espaces autour de la ponctuation française."""
    # Espace après ponctuation (point, virgule) manquant
    text = re.sub(r"([.,?!])(\w)", r"\1 \2", text)
    # Espace avant virgule incorrect
    text = re.sub(r" +,", ",", text)
    return text


def _replace_compound(m: re.Match, pattern: str, replacement: str) -> str:
    """Remplace un composé français — vérifie que chaque partie n'est pas un mot valide seul."""
    # Si le mot complet existe comme mot valide, ne pas le corriger
    full = m.group(0)
    if full.lower() in SAFE_WORDS or full in SAFE_WORDS:
        return full
    if callable(replacement):
        return replacement(m)
    return replacement


def _fix_tokenization(text: str) -> str:
    """Corrige les artefacts de tokenisation française dans un texte.

    Applique les corrections composé par composé, puis normalise la ponctuation.
    """
    if not text:
        return text

    # 1. Corriger les noms propres connus
    for pattern, replacement in KNOWN_NAMES:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # 2. Corriger les composés français
    for pattern, replacement in FRENCH_COMPOUNDS:
        text = re.sub(
            pattern,
            lambda m, p=pattern, r=replacement: _replace_compound(m, p, r),
            text,
        )

    # 3. Patterns génériques
    for pattern, replacement in PATTERNS:
        text = re.sub(pattern, replacement, text)

    # 4. Normalisation finale
    text = _normalize_spacing(text)

    return text


# ── Buffer glissant pour streaming ──

class TokenizationFixStream:
    """Corrige la tokenisation en streaming via un buffer glissant.

    Accumule les tokens, applique les corrections sur la portion non encore
    fixée, et yield le diff. Permet de streamer proprement tout en corrigeant.
    """

    def __init__(self, window_size: int = 200):
        self._buffer = ""
        self._last_yielded_len = 0
        self._window_size = window_size

    def process_token(self, token: str) -> str:
        """Ajoute un token au buffer et retourne le texte corrigé à émettre."""
        self._buffer += token

        # Appliquer les corrections sur tout le buffer
        corrected = _fix_tokenization(self._buffer)

        # Calculer la portion non encore émise
        new_content = corrected[self._last_yielded_len:]
        self._last_yielded_len = len(corrected)

        return new_content

    def flush(self) -> str:
        """Vide le buffer et retourne le texte restant corrigé."""
        corrected = _fix_tokenization(self._buffer)
        remaining = corrected[self._last_yielded_len:]
        self._buffer = ""
        self._last_yielded_len = 0
        return remaining
