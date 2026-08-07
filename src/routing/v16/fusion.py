"""NURU Router V16 — Niveau 5 : Fusion des scores.

Combine (regex/mots-clés, sémantique légère, contexte) en un seul vecteur
de scores comparables, puis normalise en pseudo-probabilités pour que le
logging et les seuils de multi-routing (niveau 6) soient interprétables.

Poids par défaut — ajustables sans redéploiement (config.py) :
    W_KEYWORD  = 1.0   (niveau 2, toujours disponible, quasi gratuit)
    W_SEMANTIC = 0.6   (niveau 3, seulement si ambigu — voir should_run_semantic)
    W_CONTEXT  = 1.2   (niveau 4 — le contexte doit pouvoir renverser une
                        décision keyword faible, mais pas une décision très
                        confiante)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .context_engine import ContextBoost
from .semantic_similarity import SemanticScore
from .signals import INTENTS, ScoreVector

W_KEYWORD = 1.0
W_SEMANTIC = 0.6
W_CONTEXT = 1.2

# Si l'écart entre les deux meilleurs scores (niveau 2 seul) est inférieur
# à cette marge, la requête est jugée "ambiguë" → on invoque le niveau 3
# (sémantique). Ça garde le niveau 3 hors du chemin chaud pour la grande
# majorité des requêtes (cf. benchmark).
AMBIGUITY_MARGIN = 2.0


@dataclass
class FusedResult:
    scores: dict[str, float]
    probs: dict[str, float]
    best_intent: str
    best_score: float
    second_intent: str
    second_score: float
    used_semantic: bool
    reasoning: list[str] = field(default_factory=list)


def is_ambiguous(vec: ScoreVector) -> bool:
    ordered = sorted(vec.scores.values(), reverse=True)
    if len(ordered) < 2:
        return False
    return (ordered[0] - ordered[1]) < AMBIGUITY_MARGIN


def fuse(
    vec: ScoreVector,
    semantic: SemanticScore | None,
    context: ContextBoost,
) -> FusedResult:
    reasoning: list[str] = []
    fused: dict[str, float] = {}
    for intent in INTENTS:
        score = W_KEYWORD * vec.scores.get(intent, 0.0)
        if semantic is not None:
            score += W_SEMANTIC * semantic.scores.get(intent, 0.0)
        if context.intent == intent:
            score += W_CONTEXT * context.weight
            reasoning.append(context.reasoning)
        fused[intent] = score

    total = sum(max(s, 0.0) for s in fused.values()) or 1.0
    probs = {k: max(v, 0.0) / total for k, v in fused.items()}

    ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    best_intent, best_score = ordered[0]
    second_intent, second_score = ordered[1] if len(ordered) > 1 else ("GENERAL", 0.0)

    if vec.hits.get(best_intent):
        reasoning.append(f"{best_intent} hits: {', '.join(vec.hits[best_intent])}")

    return FusedResult(
        scores=fused,
        probs=probs,
        best_intent=best_intent,
        best_score=best_score,
        second_intent=second_intent,
        second_score=second_score,
        used_semantic=semantic is not None,
        reasoning=reasoning,
    )
