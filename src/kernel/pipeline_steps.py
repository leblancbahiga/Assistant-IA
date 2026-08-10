"""
NURU Kernel — Pipeline Steps (Phase 3.9).

Steps composables qui encapsulent la logique du pipeline NURU.
Chaque step accède aux services via kernel.get() (pas d'import direct
de l'orchestrateur ou des singletons).

Flux complet :
    1. ReceiveQuestion  → normalise, session, TokenJuice
    2. Route            → router + V16, intent
    3. Retrieve         → RAG primary + multi + web fallback
    4. BuildContext     → prompt assembly, gardes, compression
    5. Generate         → ToT / CoT / Self-Consistency / stream
    6. Validate         → ArchonRefiner, StrictRAG, memory persist
    6b. Act             → (V18-09, V18.1 C4) exécution d'actions/tools, GATÉ
                         par `config.enable_act_step` (OFF par défaut). Lecture-seule
                         V18.1 : ne charge src.tools que si le flag est True.
    7. Respond          → yield final vers UI
"""

import asyncio
import logging
import re
import time
from typing import Any, Optional

from src.kernel.pipeline import PipelineContext, PipelineStep, StepResult
from src.core.ram_budget import get_budget

logger = logging.getLogger(__name__)

# V17 Option A — résolution d'anaphore : pronoms qui renvoient à une entité
# mentionnée précédemment ("son expérience" → "expérience de Leblanc Bahiga")
_ANAPHORIC_PRONOUNS = re.compile(
    r"\b(son|sa|ses|sa femme|il a|elle a|lui|cette personne|ce monsieur|"
    r"cette dame|cet homme|ce professionnel|ce projet|ce document)\b",
    re.IGNORECASE,
)
_ENTITY_RE = re.compile(r"\b[A-Z][a-zéèêëàâîïôûùç']{2,}(?:\s+[A-Z][a-zéèêëàâîïôûùç']{2,})+")


def _resolve_entity(query: str, session_store, session_id: str) -> Optional[str]:
    """Si la requête contient un pronom anaphorique, retourne l'entité
    (nom propre) mentionnée précédemment dans la session, sinon None."""
    if not _ANAPHORIC_PRONOUNS.search(query):
        return None
    try:
        session = session_store.get_or_create(session_id)
        history = list(session.messages)[-24:]
    except Exception:
        return None
    texts = []
    for msg in history:
        c = getattr(msg, "content", None) or getattr(msg, "text", None) or ""
        if isinstance(c, str):
            texts.append(c)
    # Chercher le dernier nom propre (séquence de mots capitalisés de 2+)
    joined = "\n".join(texts)
    entities = _ENTITY_RE.findall(joined)
    if entities and any(len(e.split()) >= 2 for e in entities):
        best = max(entities, key=len)
        return best.strip()
    return None


def _get_kernel():
    """Résout NuruKernel lazy (sans import au module level)."""
    from src.kernel import NuruKernel
    return NuruKernel()


def _get_service(name: str):
    """Raccourci pour récupérer un service du kernel."""
    return _get_kernel().get(name)


def _get_opt(name: str):
    """Raccourci pour récupérer un service optionnel (None si absent)."""
    try:
        return _get_kernel().get(name)
    except (KeyError, Exception):
        return None


def _config_minimal_pipeline() -> bool:
    """Lit config.minimal_pipeline (V18-15 — flag benchmark UNIQUEMENT).

    Import différé pour ne pas charger src.config au module import time
    (pipeline_steps est importé tôt). Retourne False par défaut : le mode
    Minimal Pipeline n'existe que pendant `run.py --benchmark --minimal`.
    """
    try:
        from src.config import config
        return bool(getattr(config, "minimal_pipeline", False))
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
# Step 1 — ReceiveQuestion
# ═══════════════════════════════════════════════════════════════

class ReceiveQuestion(PipelineStep):
    """Normalise la requête, initialise la session, compresse via TokenJuice.

    Produit :
        - ctx.correlation_id
        - ctx.session prête (session_store)
        - ctx.query compressée
    """

    async def run(self, ctx: PipelineContext) -> tuple[PipelineContext, StepResult]:
        logger.info("📥 ReceiveQuestion: len=%d | session=%s", len(ctx.query), ctx.session_id)

        # 1. Correlation ID
        import uuid
        ctx.correlation_id = uuid.uuid4().hex[:8]
        logger.info("[%s] Pipeline start", ctx.correlation_id)

        # 2. Session store
        try:
            session_store = _get_service("session_store")
            session_store.create_session(ctx.session_id)
            session_store.add_message(
                ctx.session_id, "user", ctx.query,
                metadata={"mode": "pipeline"},
            )
            # Auto-titrage
            session = session_store.get_or_create(ctx.session_id)
            if not session.title:
                title = ctx.query[:60] + ("..." if len(ctx.query) > 60 else "")
                session_store.update_title(ctx.session_id, title)
        except Exception as e:
            logger.debug("⚠️ Session store: %s", e)

        # 3. TokenJuice compression
        try:
            token_juice = _get_service("token_juice")
            original = ctx.query
            compressed = token_juice.compress_query(ctx.query)
            if compressed != original and len(compressed) < len(original):
                ctx.query = compressed
                logger.debug("🧃 TokenJuice: %d→%d chars", len(original), len(compressed))
        except Exception as e:
            logger.debug("⚠️ TokenJuice: %s", e)

        # 4. V17 Option A — résolution d'anaphore : "son" → entité precedente
        #    ("Quelle est son expérience ?" après avoir parlé de Leblanc → "son"
        #    est résolu en "Leblanc Bahiga" pour la recherche RAG)
        try:
            session_store = _get_service("session_store")
            resolved = _resolve_entity(ctx.query, session_store, ctx.session_id)
            if resolved and resolved not in ctx.query:
                ctx.query = f"{ctx.query} ({resolved})"
                logger.info("🧭 Anaphore résolue: %s → '%s' ajoutée à la requête", resolved, ctx.query[:80])
        except Exception as e:
            logger.debug("⚠️ Résolution anaphore: %s", e)

        # 5. Émettre événement
        eb = _get_opt("event_bus")
        if eb: await eb.emit("query.received", {"query": ctx.query[:80], "correlation_id": ctx.correlation_id})

        return ctx, StepResult()


# ═══════════════════════════════════════════════════════════════
# Step 2 — Route
# ═══════════════════════════════════════════════════════════════

class Route(PipelineStep):
    """Route la requête via le router sémantique + V16.

    Produit :
        - ctx.intent (RAG | GENERAL | COMPLEX | SIMPLE | TOOL)
        - ctx.route_decision, route_confidence
        - ctx.v16_decision (optionnel)
    """

    def __init__(self, rag_required: bool = True):
        super().__init__()
        self.rag_required = rag_required

    async def run(self, ctx: PipelineContext) -> tuple[PipelineContext, StepResult]:
        logger.info("🧭 Route: %s...", ctx.query[:50])

        # 1. Vérification rapide : éviter retrieve_primary pour les salutations évidentes
        # (V17: ne pas lancer RAG avant de savoir ce qu'on route)
        _trivial_greeting = ctx.query.strip().lower() in (
            "bonjour", "salut", "hello", "cc", "coucou", "hey", "hi",
        )
        if not _trivial_greeting and self.rag_required:
            try:
                rag_pipeline = _get_service("rag_pipeline")
                rag_context, rag_result = await rag_pipeline.retrieve_primary(ctx.query, ctx)
            except Exception as e:
                logger.warning("⚠️ RAG primary: %s", e)
        else:
            rag_context = ""
            rag_result = None

        # 2. Routeur sémantique
        try:
            router = _get_service("router")
            route_result = await router.route_with_context(
                ctx, rag_context=rag_context, rag_result=rag_result,
            )
            ctx.route_decision = route_result.decision
            ctx.route_confidence = route_result.confidence
            ctx.spotlight_context = getattr(route_result, 'spotlight_context', '')

            hybrid = getattr(route_result, 'hybrid_strategy', 'local_only')
            ctx.hybrid_strategy = hybrid
            ctx.intent = ctx._route_to_intent(route_result.decision)

            logger.info("🧠 Route: %s (conf=%.2f)", ctx.route_decision, ctx.route_confidence)
        except Exception as e:
            logger.warning("⚠️ Routeur: %s — fallback GENERAL", e)
            ctx.route_decision = "GENERAL"
            ctx.route_confidence = 0.0
            ctx.intent = "GENERAL"

        # 3. V16 Production Router (shadow run → prend la main)
        try:
            v16_router = _get_service("v16_router")
            v16_decision = v16_router.route(ctx.query)
            ctx.v16_decision = v16_decision
            v16_to_intent = {
                "RAG": "RAG", "WEB": "COMPLEX", "GENERAL": "GENERAL",
                "ACTION": "COMPLEX", "MULTI_ROUTE": "COMPLEX",
                "SIMPLE": "SIMPLE",
            }
            ctx.intent = v16_to_intent.get(v16_decision.intent, "GENERAL")
            logger.info("🧠 V16: %s → intent=%s", v16_decision.intent, ctx.intent)

            # V17: Ne pas injecter de contexte RAG pour les salutations/conversation
            if ctx.intent in ("SIMPLE", "GENERAL"):
                ctx.rag_context = ""
                ctx.rag_result = None
                logger.debug("🧹 RAG context cleared for %s intent", ctx.intent)

            # Shadow comparison
            v12_intent = ctx._route_to_intent(route_result.decision) if route_result else "GENERAL"
            if v16_decision.intent != v12_intent:
                logger.debug("🔮 V16/V12 divergence: V16=%s V12=%s", v16_decision.intent, v12_intent)
        except Exception as e:
            logger.debug("⚠️ V16 router: %s", e)

        # 4. Événement route
        eb = _get_opt("event_bus")
        if eb: await eb.emit("route.decided", {
            "decision": ctx.route_decision,
            "confidence": ctx.route_confidence,
            "intent": ctx.intent,
        })
        if eb: await eb.emit("pipeline.step", {"step": "routing", "detail": ctx.intent})

        return ctx, StepResult()


# ═══════════════════════════════════════════════════════════════
# Step 3 — Retrieve
# ═══════════════════════════════════════════════════════════════

class Retrieve(PipelineStep):
    """Récupération RAG multi-sources + Web fallback + gardes.

    Produit :
        - ctx.rag_context, web_context, rag_result
        - ctx.strict_refused si guard bloqué
    """

    async def run(self, ctx: PipelineContext) -> tuple[PipelineContext, StepResult]:
        logger.info("🔍 Retrieve: intent=%s", ctx.intent)

        rag_pipeline = _get_service("rag_pipeline")

        # 1. Mode FREE → pas de RAG
        response_guard = _get_service("response_guard")
        if response_guard.is_free:
            ctx.rag_context = ""
            ctx.intent = "SIMPLE"
            logger.info("🔓 Mode FREE: RAG contourné")
            return ctx, StepResult()

        # V17: Salutations/conversation → pas de RAG
        if ctx.intent in ("SIMPLE", "GENERAL"):
            ctx.rag_context = ""
            ctx.rag_result = None
            logger.debug("🧹 RAG skipped pour %s intent", ctx.intent)
            return ctx, StepResult()

        # 2. Multi-retrieval
        try:
            rag_context, web_context, merged_result = await rag_pipeline.retrieve_multi(
                ctx.query, ctx.intent, ctx.rag_context, ctx.rag_result,
            )
            ctx.rag_context = rag_context
            ctx.web_context = web_context
            ctx.rag_result = merged_result or ctx.rag_result
        except Exception as e:
            logger.warning("⚠️ Multi-retrieval: %s", e)

        # 3. TokenJuice compression post-RAG
        try:
            token_juice = _get_service("token_juice")
            if ctx.rag_context:
                ctx.rag_context = token_juice.compress(ctx.rag_context, stage="post")
            if ctx.web_context:
                ctx.web_context = token_juice.compress(ctx.web_context, stage="post")
        except Exception:
            pass

        # 4. Spotlight integration
        # V18-15 : en Mode Minimal Pipeline, l'intégration Spotlight est
        # court-circuitée (flag benchmark UNIQUEMENT — jamais le mode normal).
        _minimal = _config_minimal_pipeline()
        if ctx.spotlight_context and not _minimal:
            ctx.rag_context = rag_pipeline.integrate_spotlight(
                ctx.rag_context, ctx.rag_result, ctx.spotlight_context,
            )
        elif ctx.spotlight_context and _minimal:
            logger.info("🧪 [minimal] Intégration Spotlight désactivée (V18-15)")

        # 5. Low confidence cleanup
        has_spotlight = bool(ctx.spotlight_context)
        ctx.rag_context = rag_pipeline.clear_low_confidence_context(
            ctx.query, ctx.rag_context, ctx.rag_result, has_spotlight,
        )

        # 6. Web fallback
        ctx.rag_context, ctx.intent = await rag_pipeline.maybe_web_fallback(
            ctx.query, ctx.intent, ctx.rag_context,
        )

        # 7. Strict RAG guard
        strict_msg = await rag_pipeline.check_strict_blocks(
            ctx.query, ctx.intent, ctx.rag_context, ctx.web_context,
        )
        if strict_msg:
            ctx.strict_refused = True
            eb = _get_opt("event_bus")
            if eb: await eb.emit("query.strict_refused", {"query": ctx.query})
            return ctx, StepResult(skip_pipeline=True, response_ready=strict_msg)

        # 8. Émettre étape
        eb = _get_opt("event_bus")
        if eb: await eb.emit("pipeline.step", {"step": "rag", "detail": ctx.intent})

        return ctx, StepResult()


# ═══════════════════════════════════════════════════════════════
# Step 4 — BuildContext
# ═══════════════════════════════════════════════════════════════

class BuildContext(PipelineStep):
    """Assemble le prompt : mémoire, faits, RAG, web, budget token.

    Produit :
        - ctx.system_prompt, full_prompt
        - ctx.user_facts_str
        - ctx.use_tot, use_cot (décisions de mode)
    """

    async def run(self, ctx: PipelineContext) -> tuple[PipelineContext, StepResult]:
        logger.info("📝 BuildContext: intent=%s", ctx.intent)

        # 1. Faits utilisateur Long-Term Memory
        try:
            ltm = _get_service("long_term_memory")
            if ltm:
                facts = await ltm.get_relevant_facts(ctx.query, limit=10)
                if facts:
                    ctx.user_facts_str = ltm.format_facts_for_prompt(facts)
        except Exception as e:
            logger.debug("⚠️ LTM facts: %s", e)

        # 2. Construction du prompt
        try:
            prompt_builder = _get_service("prompt_builder")
            memory_store = _get_service("memory")
            session_store = _get_service("session_store")
            context_budget = _get_service("context_budget")

            # V17: SIMPLE → prompt minimal, sans contexte doc ni historique session
            if ctx.intent == "SIMPLE":
                system_prompt = "Tu es NURU, un assistant personnel amical et naturel."
                full_prompt = f"{system_prompt}\n\n{ctx.query}"
                ctx.system_prompt = system_prompt
                ctx.full_prompt = full_prompt
                logger.debug("💬 SIMPLE: prompt minimal (pas de RAG/session)")
            else:
                # V18-24 : rebrancher le prompt système via NuruCore.build_system_prompt
                # (snippet round 4 Q1 ✅ VALIDÉ) — au lieu de None (BUG V17)
                nuru_core = _get_service("nuru_core")
                if nuru_core and hasattr(nuru_core, "build_system_prompt"):
                    system_prompt_builder = nuru_core.build_system_prompt
                else:
                    system_prompt_builder = None

                system_prompt, full_prompt = prompt_builder.build_prompt(
                    ctx.intent, ctx.query, ctx.rag_context, ctx.web_context,
                    user_facts_str=ctx.user_facts_str,
                    session_id=ctx.session_id if ctx.intent != "SIMPLE" else None,
                    system_prompt_builder=system_prompt_builder,
                    memory_store=memory_store,
                    session_store=session_store,
                    context_budget=context_budget,
                    model_family=ctx._model_for_intent(ctx.intent),
                    session_max_context=10,
                    confidence_label=getattr(ctx.rag_result, 'confidence_label', None) if ctx.rag_result else None,
                )
                ctx.system_prompt = system_prompt
                ctx.full_prompt = full_prompt

            # V17 P12: trace prompt final (DEBUG)
            logger.debug(
                "📝 BuildContext trace [%s] intent=%s system=%d chars full=%d chars rag=%d chars web=%d",
                ctx.correlation_id[:12], ctx.intent,
                len(ctx.system_prompt or ""), len(ctx.full_prompt or ""),
                len(ctx.rag_context or ""), len(ctx.web_context or ""),
            )

        except Exception as e:
            logger.warning("⚠️ Prompt builder: %s", e)
            return ctx, StepResult(error=f"Prompt construction: {e}")

        # 3. Budget token — écrêtage final
        try:
            config = _get_service("config")
            max_safe_chars = config.rag_max_context_tokens * 4
            if len(ctx.full_prompt) > max_safe_chars:
                excess = len(ctx.full_prompt) - max_safe_chars
                logger.debug("🧃 Écrêtage post-template: %d chars", excess)
                if ctx.rag_context and ctx.rag_context in ctx.full_prompt:
                    trimmed = ctx.rag_context[:len(ctx.rag_context) - excess - 100]
                    trimmed += "\n[... tronqué ...]"
                    ctx.full_prompt = ctx.full_prompt.replace(ctx.rag_context, trimmed, 1)
                if len(ctx.full_prompt) > max_safe_chars:
                    keep = max_safe_chars - 200
                    half = keep // 2
                    ctx.full_prompt = ctx.full_prompt[:half] + "\n[... tronqué ...]\n" + ctx.full_prompt[-half:]
        except Exception:
            pass

        # 4. Mode ToT (Tree of Thoughts)
        tot_keywords = [
            "arbre de decision", "explore toutes les possibilites",
            "analyse en profondeur", "raisonnement approfondi",
            "toi activer", "tot:",
        ]
        if re.search("|".join(tot_keywords), ctx.query.lower()) or \
           (ctx.intent == "COMPLEX" and len(ctx.query.split()) >= 15):
            ctx.use_tot = True
            logger.info("🌳 ToT activée")

        # 5. Mode CoT (Chain of Thought) — V17.2 : réservé à COMPLEX
        # (le CoT sur RAG factuel double les tokens et rallonge inutilement
        # la réponse — audits _3/_4/_5 recommandent de désactiver les modes
        # lourds par défaut sur M1 8Go)
        if not ctx.use_tot and ctx.intent == "COMPLEX":
            try:
                from src.learning.chain_of_thought import should_use_cot, format_cot_prompt
                if should_use_cot(ctx.query, ctx.intent):
                    ctx.use_cot = True
                    ctx.full_prompt = format_cot_prompt(ctx.system_prompt, ctx.query, ctx.rag_context)
                    logger.info("💭 CoT activée")
            except Exception:
                pass

        eb = _get_opt("event_bus")
        if eb: await eb.emit("pipeline.step", {"step": "context", "prompt_len": len(ctx.full_prompt)})

        return ctx, StepResult()


# ═══════════════════════════════════════════════════════════════
# Step 5 — Generate
# ═══════════════════════════════════════════════════════════════

class Generate(PipelineStep):
    """Génère la réponse : streaming LLM (local ou cloud).

    Supporte ToT, CoT, Self-Consistency selon les flags positionnés
    par BuildContext.

    Produit :
        - ctx.response (texte complet)
        - ctx.model_used, tokens_generated, tokens_prompt
    """

    async def run(self, ctx: PipelineContext) -> tuple[PipelineContext, StepResult]:
        logger.info("⚡ Generate: intent=%s | tot=%s | cot=%s",
                     ctx.intent, ctx.use_tot, ctx.use_cot)

        llm_gen = _get_service("llm_generator")
        eb = _get_opt("event_bus")
        if eb: await eb.emit("pipeline.step", {"step": "generation"})

        # 1. Check connectivité (online/offline)
        ctx.is_online = await llm_gen.check_connectivity()

        # 2. Cache sémantique (sauf COMPLEX)
        if ctx.intent != "COMPLEX":
            try:
                llm_cache = _get_service("llm_cache")
                cached, diag = await llm_cache.get(ctx.query)
                if cached:
                    ctx.cache_hit = True
                    ctx.cached_response = cached
                    ctx.response = cached
                    logger.info("💾 Cache hit: %d chars", len(cached))
                    if eb: await eb.emit("cache_hit", {"query": ctx.query[:40]})
                    return ctx, StepResult(skip_pipeline=True, response_ready=cached)
            except Exception as e:
                logger.debug("⚠️ Cache: %s", e)

        # 3. Self-Consistency (RAG haute confiance uniquement)
        use_sc = (
            not ctx.use_tot
            and ctx.intent == "RAG"
            and bool(ctx.rag_context)
            and ctx.rag_result is not None
            and getattr(ctx.rag_result, 'confidence_label', 'FAIBLE') in ("HAUTE", "MOYENNE")
        )

        start_gen = time.time()
        # V17: signaler au DocWatcher que la generation est en cours (evite concurrency RAM)
        get_budget().set_generating(True)

        try:
            if ctx.use_tot:
                # ToT — Tree of Thoughts
                response = await self._generate_tot(ctx, llm_gen)
            elif use_sc:
                # Self-Consistency
                response = await self._generate_sc(ctx, llm_gen)
            else:
                # Streaming normal (accumulé + temps réel)
                gen_kwargs = {
                    "stream_session": ctx.stream_session,
                    "web_context": ctx.web_context,
                    "rag_context": ctx.rag_context,
                    "original_query": ctx.query,
                    "session_id": ctx.session_id,
                }
                response = ""
                async for token in llm_gen.generate(
                    ctx.system_prompt, ctx.full_prompt, ctx.query, ctx.intent, ctx,
                    **gen_kwargs
                ):
                    response += token
                    # V17 FIX : forwarder les tokens en temps réel vers run_stream()
                    if ctx.stream_queue is not None:
                        await ctx.stream_queue.put(token)

            ctx.response = response
            ctx.model_used = getattr(llm_gen, 'last_model', '') or ''
            ctx.tokens_generated = getattr(llm_gen, 'last_tokens', 0) or 0
            ctx.tokens_prompt = getattr(llm_gen, 'last_prompt_tokens', 0) or 0

        except Exception as e:
            logger.exception("❌ Generation error: %s", e)
            get_budget().set_generating(False)
            return ctx, StepResult(error=f"Generation: {e}")

        get_budget().set_generating(False)

        gen_time = time.time() - start_gen
        logger.info(
            "✅ Généré: %d tokens en %.1fs (%.0f tok/s) | model=%s",
            ctx.tokens_generated, gen_time,
            ctx.tokens_generated / gen_time if gen_time > 0 else 0,
            ctx.model_used,
        )

        return ctx, StepResult()

    async def _generate_tot(self, ctx: PipelineContext, llm_gen: Any) -> str:
        """Génération Tree of Thoughts avec exploration arborescente."""
        from src.learning.tot_engine import TreeOfThoughts
        tot = TreeOfThoughts(
            generate_fn=llm_gen.generate_sync,
            validate_fn=self._validate_tot_candidate,
        )
        result = await tot.explore(
            query=ctx.query,
            context=ctx.rag_context,
            max_branches=3,
            max_depth=2,
        )
        return result.get("best", "")

    async def _validate_tot_candidate(self, candidate: str, query: str, context: str) -> tuple[float, str]:
        """Valide un candidat ToT (pertinence, cohérence)."""
        try:
            from src.ai.verifier import EvidenceVerifier
            verifier = EvidenceVerifier()
            result = verifier.verify(candidate, query, context)
            return result.confidence, result.reason
        except Exception:
            return 0.5, ""

    async def _generate_sc(self, ctx: PipelineContext, llm_gen: Any) -> str:
        """Génération Self-Consistency (N échantillons → vote majoritaire)."""
        try:
            sc_engine = _get_service("self_consistency_engine")
            result = await sc_engine.generate(
                prompt=ctx.full_prompt,
                n_samples=3,
                temperature=0.7,
                intent=ctx.intent,
            )
            return result.get("response", result.get("consensus", ""))
        except Exception as e:
            logger.warning("⚠️ Self-Consistency: %s → fallback stream", e)
            # Fallback: stream simple
            response = ""
            async for token in llm_gen.generate(
                ctx.system_prompt, ctx.full_prompt, ctx.query, ctx.intent, ctx,
                web_context=ctx.web_context,
                rag_context=ctx.rag_context,
                original_query=ctx.query,
                session_id=ctx.session_id,
            ):
                response += token
            return response


# ═══════════════════════════════════════════════════════════════
# Step 6 — Validate
# ═══════════════════════════════════════════════════════════════

class Validate(PipelineStep):
    """Valide et affine la réponse générée.

    - ArchonRefiner : auto-correction post-génération
    - StrictRAGGuard : vérification de conformité RAG
    - Persistance mémoire : LTM, session, faits
    """

    # V18.1 C1 — throttle des WARNING de désactivation des services fantômes.
    _archon_refiner_warned = False
    _trace_collector_warned = False

    async def run(self, ctx: PipelineContext) -> tuple[PipelineContext, StepResult]:
        logger.info("✅ Validate: response_len=%d", len(ctx.response))

        if not ctx.response or ctx.cache_hit:
            return ctx, StepResult()

        eb = _get_opt("event_bus")

        # 1. ArchonRefiner — désactivé (V18.1)
        # Service fantôme : jamais enregistré au kernel (nuru_core.py:224-227)
        # et API incompatible (pipeline_steps.py:632-635 appelait
        # refine(query, response, rag_context, intent=...) mais la signature est
        # refine(response, rag_context, rag_score, intent) — archon_refiner.py:68-74
        # → même enregistré, TypeError. Réactivation = chantier séparé.
        if not type(self)._archon_refiner_warned:
            type(self)._archon_refiner_warned = True
            logger.warning(
                "ArchonRefiner désactivé (service non enregistré, API incompatible) — V18.1"
            )

        # 2. Evidence verification (si RAG)
        if ctx.rag_result and ctx.rag_context:
            try:
                verifier = _get_service("evidence_verifier")
                result = verifier.verify(
                    ctx.response, ctx.query, ctx.rag_context,
                )
                if not result.valid and result.confidence < 0.3:
                    logger.warning("⚠️ Score évidence faible: %.2f — %s", result.confidence, result.reason)
                    # V17.4 FIX : l'hallucination détectée doit être neutralisée,
                    # pas seulement loggée. On régénère une fois avec un prompt
                    # strict (citation obligatoire), sinon on renvoie un refus honnête.
                    try:
                        llm_gen = _get_service("llm_generator")
                        has_real_context = bool(
                            ctx.rag_context
                            and "AUCUNE SOURCE" not in ctx.rag_context
                        )
                        if llm_gen is not None and has_real_context:
                            strict_prompt = (
                                "Réponds UNIQUEMENT à partir du contexte ci-dessous, "
                                "en citant [Source: nom] après chaque fait. "
                                "Si l'information n'y est pas, dis en une phrase que tu "
                                "ne la trouves pas dans les documents — n'invente rien.\n\n"
                                f"CONTEXTE:\n{ctx.rag_context[:3000]}\n\n"
                                f"QUESTION: {ctx.query}"
                            )
                            retry_text = ""
                            async for token in llm_gen.generate(
                                strict_prompt, strict_prompt, ctx.query, "RAG", ctx,
                                session_id=ctx.session_id,
                            ):
                                retry_text += token if isinstance(token, str) else ""
                                # Streamer la correction vers l'UI en temps réel
                                if ctx.stream_queue is not None and isinstance(token, str):
                                    await ctx.stream_queue.put(token)
                            if retry_text and len(retry_text) > 20:
                                retry_result = verifier.verify(
                                    retry_text, ctx.query, ctx.rag_context,
                                )
                                if retry_result.valid or retry_result.confidence >= 0.3:
                                    ctx.response = retry_text
                                    logger.info("🔁 Régénération stricte: évidence %.2f OK",
                                                retry_result.confidence)
                                else:
                                    ctx.response = (
                                        "Je ne trouve pas cette information dans les "
                                        "documents fournis. [Source: AUCUNE SOURCE]"
                                    )
                            else:
                                ctx.response = (
                                    "Je ne trouve pas cette information dans les "
                                    "documents fournis. [Source: AUCUNE SOURCE]"
                                )
                    except Exception as e:
                        logger.debug("⚠️ Régénération stricte: %s", e)
                        ctx.response = (
                            "Je ne trouve pas cette information dans les "
                            "documents fournis. [Source: AUCUNE SOURCE]"
                        )
            except Exception as e:
                logger.debug("⚠️ Evidence verifier: %s", e)

        # 3. Persistance en mémoire courte
        try:
            session_store = _get_service("session_store")
            session_store.add_message(ctx.session_id, "assistant", ctx.response)
        except Exception:
            pass

        # 4. Long-Term Memory extraction (faits utilisateur)
        try:
            ltm = _get_service("long_term_memory")
            if ltm:
                await ltm.extract_post_response(ctx.query, ctx.response, ctx.intent)
        except Exception as e:
            logger.debug("⚠️ LTM extract: %s", e)

        # 5. Trace collector — désactivé (V18.1)
        # Service fantôme : jamais enregistré au kernel (nuru_core.py:224-227)
        # et appel async sans await (pipeline_steps.py:724 appelait
        # trace.record(...) sans await → coroutine jetée, zéro trace même
        # enregistré ; args positionnels décalés intent→mode, model_used→confidence).
        if not type(self)._trace_collector_warned:
            type(self)._trace_collector_warned = True
            logger.warning(
                "TraceCollector désactivé (service non enregistré, appel async sans await) — V18.1"
            )

        if eb: await eb.emit("pipeline.step", {"step": "validation"})
        return ctx, StepResult()


# ═══════════════════════════════════════════════════════════════
# Step 6b — Act (V18-09, V18.1 C4)
# ═══════════════════════════════════════════════════════════════

class Act(PipelineStep):
    """Step Act — exécution d'actions/tools (V18-09), GATÉ.

    Lecture-seule V18.1 (C4) : on implémente la STRUCTURE (gate, lazy imports,
    accès permissions/agent_limits) mais PAS l'exécution réelle des tools —
    elle sera unifiée en C5 (MCP).

    Comportement :
        - `config.enable_act_step == False` (défaut) → no-op strict :
            zéro import de `src.tools`, le pipeline continue inchangé.
        - `config.enable_act_step == True` → lazy import différé de `src.tools`
            (19+ modules, ~19,3 MiB) effectué DANS `run()`, jamais au boot.
            L'exécution effective reste à C5 ; ici on ne fait que valider que
            le module est chargable et on lit les permissions/agent_limits.
    """

    async def run(self, ctx: PipelineContext) -> tuple[PipelineContext, StepResult]:
        # Accès au singleton config — import léger (src.config ≠ src.tools),
        # effectué ici pour rester cohérent avec le lazy pattern des étapes.
        from src.config import config

        # ── GATE — désactivé par défaut ──
        if not config.enable_act_step:
            logger.info("⏸️ Act gâté (enable_act_step=False) — no-op")
            return ctx, StepResult()

        # ── Actif : lazy import DIFFÉRÉ de src.tools (~19,3 MiB) ──
        # L'import n'a lieu qu'ici, jamais au boot. Lecture-seule V18.1 :
        # on lit le REGISTRE UNIFIÉ (ToolOrchestrator — la même source de
        # vérité que le serveur MCP, chantier C5 / V18-10). Aucune exécution.
        try:
            from src.tools.orchestrator import ToolOrchestrator
            orch = ToolOrchestrator.get_instance()
            orch.setup()  # peupler le registre unique (idempotent)
            registry = orch.get_registry()
            tool_names = [t.name for t in registry.list_tools()]
            logger.info(
                "⚙️ Act actif (enable_act_step=True) — registre unifié lu: "
                "%d outils (%s). Exécution runtime = chantier C5 (MCP).",
                len(tool_names), ", ".join(tool_names[:5]) + ("…" if len(tool_names) > 5 else ""),
            )
        except Exception as e:  # src.tools import impossible → step dégradé
            logger.warning("⚠️ Act: import src.tools échoué: %s", e)
            return ctx, StepResult(error=f"Act: import src.tools: {e}")

        # Permissions + limites injectées via le contexte (lecture seule).
        limits = getattr(ctx, "agent_limits", None) or config.agent_limits
        perms = getattr(ctx, "permissions", None)
        if limits is not None:
            logger.info(
                "🔐 Act: allowed_tools=%s max_steps=%s max_concurrent=%s perms=%s",
                getattr(limits, "allowed_tools", []),
                getattr(limits, "max_steps", None),
                getattr(limits, "max_concurrent", None),
                bool(perms),
            )

        # NOTE C4/lecture-seule : aucune exécution de tool ici (C5).
        return ctx, StepResult()


# ═══════════════════════════════════════════════════════════════
# Step 7 — Respond
# ═══════════════════════════════════════════════════════════════

class Respond(PipelineStep):
    """Finalise la réponse et émet les événements UI.

    Produit :
        - ctx inchangé (la réponse est déjà accumulée)
        - Émet des événements pour l'UI (stream finish)
    """

    async def run(self, ctx: PipelineContext) -> tuple[PipelineContext, StepResult]:
        logger.info("📤 Respond: response_len=%d", len(ctx.response))

        eb = _get_opt("event_bus")

        # 1. TTS si demandé
        if ctx.use_tts and ctx.audio_engine and ctx.response:
            try:
                asyncio.ensure_future(ctx.audio_engine.speak(ctx.response))
            except Exception as e:
                logger.debug("⚠️ TTS: %s", e)

        # 2. Événements de fin
        if eb: await eb.emit("pipeline.step", {"step": "complete", "len": len(ctx.response)})
        if eb: await eb.emit("response.ready", {
            "response": ctx.response[:200],
            "model": ctx.model_used,
            "tokens": ctx.tokens_generated,
        })

        return ctx, StepResult()
