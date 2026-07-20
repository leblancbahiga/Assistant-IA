"""NURU Router V16 — Niveau 1 : Fast Rules (<0.05 ms).

Fusion des TRIVIAL_PATTERNS de router.py et semantic_router.py (ils étaient
dupliqués et avaient légèrement divergé — c'est corrigé ici : une seule
source de vérité).

Ce niveau ne doit JAMAIS faire de scoring : c'est un aiguillage direct
pour les cas où l'ambiguïté est nulle (salutations, oui/non, identité du
bot). Tout le reste passe au niveau 2.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

TRIVIAL_PATTERNS: dict[str, str] = {
    r"^(bonjour|salut|hello|hi|coucou|hey|yo)\b": "SIMPLE",
    r"^(merci|thanks|merci beaucoup|merci bien)\b": "SIMPLE",
    r"^(bonsoir|bonne nuit|bonne journee|bonne soiree|bonne fin de semaine|a demain|bye|aurevoir|au revoir|ciao)\b": "SIMPLE",
    r"^(oui|non|ok|d'accord|daccord|super|parfait|cool|genial|nickel|top)\b": "SIMPLE",
    r"^(c'?(est|etait) (bien|super|genial|nul|pas mal|sympa|interessant))\b": "SIMPLE",
    r"^(je (suis|va|vais) (bien|content|heureux|fatigue|occupe))\b": "SIMPLE",
    r"^(qui (es-?tu|etes-?vous|est-tu|est ce))\b": "SIMPLE",
    r"^(tu es|vous etes) qui\b": "SIMPLE",
    r"^(quelle est (ton|ta) (nom|identite|but|mission|role|fonction|objectif|createur|auteur))\b": "SIMPLE",
    r"^(tu peux )?(repeter|repete|expliquer|clarifier|resumer|reformuler)\b": "SIMPLE",
}

# NOTE: "qui suis-je" est délibérément EXCLU d'ici : c'est une question
# d'identité PERSONNELLE (l'utilisateur), pas une question sur le bot.
# Elle doit continuer au niveau 2 pour être scorée RAG. C'était une source
# de confusion dans le code V12 (commentaire "NOTA" à ce sujet) — ici la
# distinction est explicite et testée (voir tests/test_router_v16.py).

_COMPILED: list[tuple[re.Pattern, str]] = [(re.compile(p), i) for p, i in TRIVIAL_PATTERNS.items()]


@dataclass
class FastRuleHit:
    intent: str
    confidence: float = 0.99
    reasoning: str = "fast_rule"


def match_fast_rule(folded_query: str) -> Optional[FastRuleHit]:
    for pattern, intent in _COMPILED:
        if pattern.match(folded_query):
            return FastRuleHit(intent=intent, reasoning=f"fast_rule:{pattern.pattern}")
    return None
