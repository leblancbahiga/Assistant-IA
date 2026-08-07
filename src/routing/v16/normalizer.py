"""NURU Router V16 — Normalisation (Niveau 0).

Étape unique et bon marché exécutée avant tout le reste du pipeline.
Objectif : que les niveaux suivants n'aient jamais à gérer la casse,
les accents incohérents ("etudie" vs "étudie") ou les espaces multiples.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

_WS_RE = re.compile(r"\s+")


def fold_accents(text: str) -> str:
    """Retire les diacritiques (é→e, ô→o...) pour un matching robuste."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


@dataclass
class NormalizedQuery:
    raw: str
    lower: str          # lower + espaces nettoyés, ACCENTS CONSERVÉS (pour la casse des noms propres ailleurs)
    folded: str          # lower + accents retirés (pour les patterns/mots-clés)
    tokens: list = field(default_factory=list)
    word_count: int = 0


def normalize(query: str) -> NormalizedQuery:
    raw = query
    lower = _WS_RE.sub(" ", query.strip().lower())
    folded = fold_accents(lower)
    tokens = folded.split()
    return NormalizedQuery(raw=raw, lower=lower, folded=folded, tokens=tokens, word_count=len(tokens))
