"""NURU Router V16 — Orchestrateur.

Pipeline :
    Normalisation → Fast Rules → Intent Scoring → [Semantic si ambigu]
    → Context Engine → Fusion → Multi-routing → Résultat

Aucun appel LLM nulle part dans ce fichier. C'est une contrainte dure :
le classifieur LLM de router.py V12 (build_classify_prompt / _classify_with_llm)
est entièrement retiré du chemin de décision. Le LLM ne doit plus intervenir
qu'APRÈS le routage (génération de la réponse), jamais pour décider la route.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from .cache import TTLDecisionCache, make_key
from .context_engine import ConversationState, resolve_context
from .fast_rules import match_fast_rule
from .fusion import fuse, is_ambiguous
from .multi_router import RoutePlan, maybe_build_plan
from .normalizer import normalize
from .semantic_similarity import SemanticSimilarity
from .signals import score_intents

logger = logging.getLogger(__name__)


@dataclass
class RouteDecision:
    intent: str
    confidence: float
    reasoning: str
    processing_time_ms: float
    plan: Optional[RoutePlan] = None
    scores: dict = field(default_factory=dict)
    from_cache: bool = False


class RouterV16:
    def __init__(self, cache_size: int = 256, cache_ttl: float = 300.0,
                 embedding_backend=None):
        self._cache = TTLDecisionCache(maxsize=cache_size, ttl_seconds=cache_ttl)
        self._semantic = SemanticSimilarity(backend=embedding_backend)
        self._conversation = ConversationState()

    def route(self, query: str) -> RouteDecision:
        t0 = time.perf_counter()
        nq = normalize(query)

        ctx_fingerprint = f"doc={self._conversation.last_document_ref}"
        cache_key = make_key(nq.folded, ctx_fingerprint)
        cached = self._cache.get(cache_key)
        if cached is not None:
            cached.processing_time_ms = (time.perf_counter() - t0) * 1000
            cached.from_cache = True
            return cached

        # ── Niveau 1 : Fast Rules ──
        hit = match_fast_rule(nq.folded)
        if hit is not None:
            decision = RouteDecision(
                intent=hit.intent, confidence=hit.confidence,
                reasoning=hit.reasoning,
                processing_time_ms=(time.perf_counter() - t0) * 1000,
            )
            self._cache.set(cache_key, decision)
            self._conversation.update_after_route(hit.intent, nq.folded)
            return decision

        # ── Niveau 2 : Intent Scoring ──
        vec = score_intents(nq.raw, nq.tokens, nq.folded)

        # ── Niveau 3 : Semantic (seulement si ambigu) ──
        semantic = None
        if is_ambiguous(vec):
            semantic = self._semantic.score(nq.folded)

        # ── Niveau 4 : Context Engine ──
        context_boost = resolve_context(nq.folded, self._conversation)

        # ── Niveau 5 : Fusion ──
        fused = fuse(vec, semantic, context_boost)

        # ── Niveau 6 : Multi-routing ──
        plan = maybe_build_plan(nq.folded, fused, vec.scores)

        confidence = fused.probs[fused.best_intent]
        reasoning = "; ".join(fused.reasoning) if fused.reasoning else f"keyword scoring → {fused.best_intent}"
        if semantic is not None:
            reasoning += " | +semantic (ambigu)"

        decision = RouteDecision(
            intent=fused.best_intent if plan is None else "MULTI_ROUTE",
            confidence=confidence,
            reasoning=reasoning,
            processing_time_ms=(time.perf_counter() - t0) * 1000,
            plan=plan,
            scores=fused.scores,
        )
        self._cache.set(cache_key, decision)
        self._conversation.update_after_route(fused.best_intent, nq.folded)
        return decision
