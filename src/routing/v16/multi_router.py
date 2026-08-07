"""NURU Router V16 — Niveau 6 : Multi-routing.

Répond à l'exemple "Compare mon CV avec cette offre d'emploi." qui doit
produire un plan à plusieurs étapes (RAG → WEB → LLM) plutôt qu'une seule
destination.

Deux déclencheurs indépendants (l'un suffit) :
    1. Connecteurs explicites de comparaison/combinaison dans la requête
       ("compare X avec Y", "et aussi", "puis", "ainsi que").
    2. Deux intentions dont les scores fusionnés sont tous deux au-dessus
       de MIN_ROUTE_THRESHOLD et suffisamment proches (pas de gagnant net).

Seules certaines paires sont "compatibles" en pratique (RAG+WEB,
RAG+ACTION) — le reste (ex: SIMPLE+WEB) est trop rare/risqué pour justifier
un plan à deux étapes et retombe sur la meilleure intention seule.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .fusion import FusedResult

MIN_ROUTE_THRESHOLD = 0.20
CLOSE_ENOUGH_RATIO = 0.65  # second_score / best_score

COMPATIBLE_PAIRS = {
    frozenset({"RAG", "WEB"}),
    frozenset({"RAG", "ACTION"}),
    frozenset({"WEB", "ACTION"}),
}

COMBINATOR_PATTERNS = [
    re.compile(r"\bcompare\b.+\bavec\b"),
    re.compile(r"\bet aussi\b"),
    re.compile(r"\bainsi que\b"),
    re.compile(r"\bpuis\b"),
]


@dataclass
class RoutePlan:
    steps: list[str]
    reasoning: str = ""


def maybe_build_plan(folded_query: str, fused: FusedResult, keyword_scores: dict) -> RoutePlan | None:
    pair = frozenset({fused.best_intent, fused.second_intent})
    if pair not in COMPATIBLE_PAIRS:
        return None

    explicit_combinator = any(p.search(folded_query) for p in COMBINATOR_PATTERNS)

    # Garde-fou : sans connecteur explicite, exiger que les DEUX intentions
    # aient une vraie preuve par mots-clés (niveau 2), pas seulement un bruit
    # de similarité sémantique sur une requête courte à faible signal.
    # Sans ce garde-fou, "Quelles sont les nouvelles du jour ?" (WEB pur)
    # déclenchait à tort un plan WEB+RAG à cause d'un score sémantique RAG
    # résiduel — corrigé et couvert par un test de non-régression.
    both_have_keyword_evidence = (
        keyword_scores.get(fused.best_intent, 0.0) >= 1.0
        and keyword_scores.get(fused.second_intent, 0.0) >= 1.0
    )
    score_based = (
        both_have_keyword_evidence
        and fused.second_score >= MIN_ROUTE_THRESHOLD
        and fused.best_score > 0
        and (fused.second_score / fused.best_score) >= CLOSE_ENOUGH_RATIO
    )

    if not (explicit_combinator or score_based):
        return None

    # Ordre de résolution fixe et documenté : documents locaux d'abord
    # (rapide, pas de réseau), puis web (latence réseau), puis synthèse LLM.
    order = {"RAG": 0, "WEB": 1, "ACTION": 2}
    steps = sorted([fused.best_intent, fused.second_intent], key=lambda x: order.get(x, 9))
    steps.append("LLM_SYNTHESIS")

    reason = "connecteur explicite" if explicit_combinator else "scores proches et compatibles"
    return RoutePlan(steps=steps, reasoning=reason)
