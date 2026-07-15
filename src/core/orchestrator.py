"""
NURU V8+ — Orchestrateur asynchrone principal.

Point d'entrée du pipeline : reçoit une requête utilisateur,
orchestre routage → RAG → génération → mémoire, et retourne
un résultat structuré.
"""
import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional

from src.config import config

from src.core.query_context import QueryContext, EvidencePack
from src.core.events import EventBus
from src.core.policies import PolicyEngine
from src.core.response_guard import StrictRAGGuard
from src.core.prompt_guard import (
    sanitize_for_prompt_injection,
    sanitize_document_content,
    build_safe_user_facts_block,
)
from src.core.exceptions import (
    OrchestratorError, RAGError, LLMError, MemoryError,
    RouterError, ConfigError, GuardError,
)
from src.ai.verifier import EvidenceVerifier
from src.token_juice import TokenJuice
from src.learning.trace_collector import TraceCollector
from src.cache.llm_cache import LLMCache
from src.orchestration import RAGOrchestrator, LLMGenerator
from src.routing.prompt_builder import DynamicPromptBuilder
# V16 FIX: SessionMemory unifié (remplace MemoryStore fragmenté)
from src.core.session_memory import SessionMemory, get_session_memory
# V16: Self-Consistency Engine
from src.learning.self_consistency import SelfConsistencyEngine

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorResult:
    """Résultat structuré d'une requête traitée par l'orchestrateur."""
    response: str = ""
    route: str = "unknown"
    confidence: float = 0.0
    evidence: Optional[EvidencePack] = None
    tokens_generated: int = 0
    tokens_prompt: int = 0
    duration_s: float = 0.0
    tokens_per_sec: float = 0.0
    model: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "route": self.route,
            "confidence": round(self.confidence, 3),
            "tokens": self.tokens_generated,
            "duration_s": round(self.duration_s, 2),
            "tps": round(self.tokens_per_sec, 2),
            "model": self.model,
        }


class NuruOrchestrator:
    """Orchestrateur asynchrone du pipeline NURU V8+.

    1. Reçoit une requête utilisateur
    2. Construit un QueryContext
    3. Route via SemanticRouter (avec cache TTL)
    4. Assemble les preuves via RAG Engine
    5. Génère la réponse (local ou cloud selon policies)
    6. Persiste en mémoire
    7. Émet des événements pour l'UI

    Injection de dépendances : tous les composants passés au constructeur.
    Migration incrémentale : utilisable en parallèle de NuruCore.
    """

    def __init__(
        self,
        router,
        rag_engine,
        local_llm,
        cloud_llm,
        memory_store,
        policy_engine: Optional[PolicyEngine] = None,
        event_bus: Optional[EventBus] = None,
        runtime_manager=None,
        web_search=None,
        context_budget=None,
        system_prompt_builder=None,  # Callback pour construire le prompt système
    ):
        self.router = router
        self.rag_engine = rag_engine
        self.local_llm = local_llm
        self.cloud_llm = cloud_llm
        self.memory_store = memory_store
        self.policy_engine = policy_engine or PolicyEngine()
        self.event_bus = event_bus or EventBus()
        self.runtime = runtime_manager
        self.web = web_search
        self.context_budget = context_budget
        self._system_prompt_builder = system_prompt_builder
        self.prompt_builder = DynamicPromptBuilder()
        # NURU : Mode Strict RAG depuis config
        self.response_guard = StrictRAGGuard(config.response_mode)
        # NURU : Vérificateur de citations
        self.evidence_verifier = EvidenceVerifier()
        # NURU : Middleware de compression de contexte (TokenJuice)
        tj_enabled = getattr(config, 'token_juice_enabled', True)
        self.token_juice = TokenJuice(
            enabled=tj_enabled,
            max_chunk_chars=getattr(config, 'token_juice_max_chunk_chars', 2000),
        )
        # NURU : Learning Loop — collecteur de traces
        self.trace_collector = TraceCollector()
        # NURU : Long-Term Memory — faits utilisateur structurés
        self.long_term_memory = None  # Initialisé via set_long_term_memory()
        # Suivi du dernier résultat RAG pour l'observabilité UI
        self.last_rag_result = None

        # V10.2 : Cache LLM multi-niveau (L1 RAM + L2 SQLite)
        self.llm_cache = LLMCache(self.memory_store)

        # V10.3j — AUDIT BUG-FIX : `rag_pipeline` est référencé par ResearchArchon.
        # Avant ce fix, `self.rag_pipeline` n'était défini nulle part → crash au démarrage.
        # Sémantique : rag_pipeline = point d'entrée du pipeline RAG (retrieve + chunks).
        # On l'aliase sur rag_engine car ce dernier est déjà DI-é depuis NuruCore.
        self.rag_pipeline = rag_engine

        # V16 FIX: SessionMemory unifié (remplace MemoryStore + SessionStore fragmentés)
        from src.core.session_memory import get_session_memory
        self.session_memory = get_session_memory(max_messages=6)
        self._session_max_context = getattr(config, 'session_max_messages', 10)
        
        # V10.3f : Sessions conversationnelles persistantes (gardé pour compat)
        from src.session.store import SessionStore
        self.session_store = SessionStore()

        # V10.3h : ArchonRefiner — auto‑correction post‑génération
        from src.ai.archon_refiner import ArchonRefiner
        self.archon_refiner = ArchonRefiner(
            cloud_llm=self.cloud_llm,
            enabled=getattr(config, 'archon_enabled', True),
        )

        # V10.3j : ResearchArchon — recherche multi‑agent pour COMPLEX
        from src.ai.archon_research import ResearchArchon
        self.research_archon = ResearchArchon(
            cloud_llm=self.cloud_llm,
            rag_pipeline=self.rag_pipeline,
            enabled=getattr(config, 'research_archon_enabled', True),
        )

        # V10.2 : Sous-orchestrateurs
        self.rag_pipeline = RAGOrchestrator(
            rag_engine=self.rag_engine,
            cloud_llm=self.cloud_llm,
            web_search=self.web,
            event_bus=self.event_bus,
            response_guard=self.response_guard,
            evidence_verifier=self.evidence_verifier,
        )
        self.llm_gen = LLMGenerator(
            local_llm=self.local_llm,
            cloud_llm=self.cloud_llm,
            policy_engine=self.policy_engine,
            runtime=self.runtime,
            event_bus=self.event_bus,
        )

    async def process_query(
        self,
        query: str,
        session_id: str = "default",
        use_tts: bool = False,
        audio_engine=None,
        stream_session=None,  # V15 P2 #26 : StreamSession optionnel
    ) -> AsyncGenerator[str, None]:
        """Pipeline complet : route → RAG → génère → stream.

        Yields les tokens de réponse.
        Optionnel : stream_session pour callbacks + abort.
        """
        # ── 1. Contexte avec état réseau réel (NURU V5) ──
        is_online = await self.llm_gen.check_connectivity()
        ctx = QueryContext.from_runtime(
            query, session_id,
            is_online=is_online,
        )
        # V10.3f : Enregistrer la question dans l'historique session
        original_query = query
        query = self.token_juice.compress_query(query)
        if query != original_query and len(query) < len(original_query):
            logger.debug(
                f"🧃 TokenJuice: requête compressée "
                f"{len(original_query)}→{len(query)} chars"
            )
        # V10.3f : Enregistrer la question utilisateur dans la session
        self.session_store.create_session(session_id)
        self.session_store.add_message(session_id, "user", original_query, metadata={"mode": ctx.mode})
        # Auto-titrage : premier message → titre de session
        if not self.session_store.get_or_create(session_id).title:
            title = original_query[:60] + ("..." if len(original_query) > 60 else "")
            self.session_store.update_title(session_id, title)
        await self.event_bus.emit("query.received", {"query": query})

        # ── 2. RAG retrieval (UNE SEULE FOIS — partagé entre routeur et contexte) ──
        rag_context, rag_result = await self.rag_pipeline.retrieve_primary(query, ctx)
        self.last_rag_result = rag_result

        route_result = await self.router.route_with_context(ctx, rag_context=rag_context, rag_result=rag_result)
        hybrid_strategy = getattr(route_result, 'hybrid_strategy', 'local_only')
        ctx = ctx.with_route(route_result.decision, hybrid_strategy=hybrid_strategy)
        intent = self._route_to_intent(route_result.decision)
        await self.event_bus.emit("route.decided", {
            "decision": route_result.decision,
            "confidence": route_result.confidence,
            "rag_score": route_result.rag_top_score,
        })
        await self.event_bus.emit("pipeline.step", {"step": "routing", "detail": route_result.decision})
        logger.info(
            f"🧠 Route: {query[:40]}... → {route_result.decision} "
            f"(conf: {route_result.confidence:.2f})"
        )

        # ── 3. Cache sémantique (L1 RAM → L2 SQLite) ──
        if intent != "COMPLEX":
            cached, cached_diag = await self.llm_cache.get(query)
            if cached:
                await self.event_bus.emit("cache_hit", {"query": query})
                if use_tts and audio_engine:
                    asyncio.create_task(audio_engine.speak(cached)).add_done_callback(
                        lambda t: t.exception() if not t.cancelled() else None
                    )
                yield cached

        # ── 4. Récupération contexte (RAGOrchestrator multi-sous-requêtes) ──
        if self.response_guard.is_free:
            # Mode FREE : pas de RAG, pas de web search, conversation libre
            rag_context = ""
            web_context = ""
            merged_result = rag_result  # pylint: disable=possibly-used-before-assignment
            intent = "SIMPLE"
            logger.info("🔓 Mode FREE: RAG + web contournés")
        else:
            rag_context, web_context, merged_result = await self.rag_pipeline.retrieve_multi(
                query, intent, rag_context, rag_result,
            )
        rag_result = merged_result or rag_result
        # Émettre l'étape RAG (après multi-retrieval)
        await self.event_bus.emit("pipeline.step", {"step": "rag", "detail": intent})

        # NURU V6 : TokenJuice — compression du contexte RAG et web
        if rag_context:
            rag_context = self.token_juice.compress(rag_context, stage="post")
        if web_context:
            web_context = self.token_juice.compress(web_context, stage="post")

        # V10 : Ajouter le contexte Spotlight lu si disponible
        spotlight_ctx = getattr(route_result, 'spotlight_context', '')
        if spotlight_ctx:
            rag_context = self.rag_pipeline.integrate_spotlight(
                rag_context, rag_result, spotlight_ctx,
            )

        # V10: Vider le contexte RAG si résultats FAIBLE confiance
        has_spotlight = bool(spotlight_ctx)
        rag_context = self.rag_pipeline.clear_low_confidence_context(
            query, rag_context, rag_result, has_spotlight,
        )

        # ── 5. Fallback Web si RAG vide ──
        rag_context, intent = await self.rag_pipeline.maybe_web_fallback(
            query, intent, rag_context,
        )

        # ── 5.5-5.6 FallbackGuard + Strict RAG ──
        strict_msg = await self.rag_pipeline.check_strict_blocks(
            query, intent, rag_context, web_context if 'web_context' in dir() else "",
        )
        if strict_msg:
            await self.event_bus.emit("query.strict_refused", {"query": query})
            yield strict_msg
            return

        # ── 6. Construction prompt ──
        # NURU : injection des faits utilisateur Long-Term Memory
        user_facts_str = ""
        if self.long_term_memory:
            relevant_facts = await self.long_term_memory.get_relevant_facts(query, limit=10)
            if relevant_facts:
                user_facts_str = self.long_term_memory.format_facts_for_prompt(relevant_facts)
        system_prompt, full_prompt = self.prompt_builder.build_prompt(
            intent, query, rag_context, web_context,
            user_facts_str=user_facts_str, session_id=session_id,
            system_prompt_builder=self._system_prompt_builder,
            memory_store=self.memory_store,
            session_store=self.session_store,
            context_budget=self.context_budget,
            model_family=self._model_for_intent(intent),
            session_max_context=self._session_max_context,
        )

        # Action E : Budget token post-template — écrêtage final du prompt complet
        max_safe_chars = config.rag_max_context_tokens * 4  # ~4 chars/token
        if len(full_prompt) > max_safe_chars:
            excess = len(full_prompt) - max_safe_chars
            logger.debug(f"🧃 TokenJuice: écrêtage post-template de {excess} chars")
            # On tronque le contexte RAG (la partie la plus longue) d'abord
            if rag_context and rag_context in full_prompt:
                # Réduire le contexte RAG de l'excédent
                trimmed_rag = rag_context[:len(rag_context) - excess - 100] + "\n[... tronqué pour budget token ...]"
                full_prompt = full_prompt.replace(rag_context, trimmed_rag, 1)
            # Si toujours trop long, tronquer la fin du prompt
            if len(full_prompt) > max_safe_chars:
                full_prompt = full_prompt[:max_safe_chars - 100] + "\n[... tronqué ...]"

        # ── 6.5 Activation CoT (Chain of Thought) ──
        # V16: Injecte instruction de raisonnement etape par etape
        # pour les requetes complexes (COMPLEX ou RAG multi-saut)
        use_cot = False
        if intent in ("COMPLEX", "RAG", "GENERAL"):
            from src.learning.chain_of_thought import should_use_cot, format_cot_prompt, extract_reasoning_and_answer
            use_cot = should_use_cot(query, intent)
            if use_cot:
                logger.info(f"💭 CoT activee pour: {query[:50]}...")
                full_prompt = format_cot_prompt(system_prompt, query, rag_context)

        # ── 7. Génération (streaming) ──
        await self.event_bus.emit("pipeline.step", {"step": "generation"})
        response_content = ""
        start_gen = time.time()

        try:
            # V16: Self-Consistency pour requêtes RAG avec confiance suffisante
            # Génère 3 réponses et vote par similarité (réduit hallucinations ~40%)
            use_self_consistency = (
                intent == "RAG"
                and rag_context
                and rag_result
                and getattr(rag_result, 'confidence_label', 'FAIBLE') in ("HAUTE", "MOYENNE")
                and len(rag_context) > 100
            )
            
            if use_self_consistency:
                # Initialiser SelfConsistencyEngine si pas déjà fait
                if not hasattr(self, '_self_consistency'):
                    from src.learning.self_consistency import SelfConsistencyEngine
                    self._self_consistency = SelfConsistencyEngine(n_samples=3, temperature=0.7)
                
                # Construire le prompt de base pour Self-Consistency
                sc_prompt = self._build_self_consistency_prompt(
                    system_prompt, full_prompt, query, rag_context, intent
                )
                
                async def sc_generate_fn(prompt: str, temp: float) -> str:
                    """Wrapper pour génération Self-Consistency (non-streaming)."""
                    return await self._generate_sc_response(prompt, intent, temp)
                
                logger.info(f"🗳️ Self-Consistency activée pour: {query[:50]}...")
                sc_result = await self._self_consistency.generate_consistent(
                    query=query,
                    context=rag_context,
                    generate_fn=sc_generate_fn,
                    system_prompt=system_prompt,
                )
                
                # Stream la réponse consensuelle
                response_content = sc_result.final_response
                logger.info(f"✅ Self-Consistency: consensus {sc_result.consensus_score:.0%}")
                
                # Yield par chunks pour compatibilité UI streaming
                chunk_size = 50
                for i in range(0, len(response_content), chunk_size):
                    yield response_content[i:i+chunk_size]
                    await asyncio.sleep(0.01)
            else:
                # Génération normale (streaming)
                async for token in self.llm_gen.generate(
                    system_prompt, full_prompt, query, intent, ctx,
                    web_context=web_context, rag_context=rag_context,
                    original_query=original_query,
                    stream_session=stream_session,  # V15 P2 #26
                ):
                    response_content += token
                    yield token

        except (LLMError, GuardError, RAGError) as e:
            logger.error(f"❌ Génération: {e}")
            yield f"\n[⚠️ Erreur: {e}]"
            return

        duration = time.time() - start_gen

        # ── 7.5 Vérification des citations post-génération ──
        refusal = await self.rag_pipeline.verify_citations(
            intent, rag_context, response_content, rag_result, query,
        )
        if refusal:
            response_content = refusal
            await self.event_bus.emit("verification_failed", {
                "query": query,
                "reason": "Strict RAG: vérification échouée",
            })

        # ── 7.6 Vérificateur de faits Cloud + retry ──
        should_regenerate, warning_msg = await self.rag_pipeline.fact_check_and_retry(
            intent, response_content, rag_context, ctx, query,
            self.cloud_llm, rag_result,
        )
        if should_regenerate:
            ctx = ctx.with_retry().with_fact_checked()
            yield "\n\n🔄 **Vérification : régénération en cours...**\n"
            strict_instr = (
                "\n\n## INSTRUCTION STRICTE\n"
                "La réponse précédente contenait des affirmations non supportées par les sources.\n"
                "Cette fois, réponds UNIQUEMENT avec les informations EXACTEMENT présentes "
                "dans le contexte ci-dessus.\n"
                "Si une information n'est pas dans les sources, dis-le clairement. N'invente RIEN.\n"
                "Cite chaque source utilisée.\n"
            )
            new_response = ""
            async for token in self.llm_gen.generate(
                system_prompt, full_prompt + strict_instr, query, intent, ctx,
                web_context=web_context, rag_context=rag_context,
                original_query=original_query,
            ):
                new_response += token
                yield token
            if new_response:
                response_content = new_response
        elif warning_msg:
            yield "\n\n---\n" + warning_msg + "\n---\n"

        # V16: Post-traitement CoT — extraire uniquement la reponse finale
        if use_cot and response_content:
            from src.learning.chain_of_thought import extract_reasoning_and_answer, strip_reasoning_if_needed
            reasoning, answer = extract_reasoning_and_answer(response_content)
            if answer:
                # Remplacer le yield de la reponse brute si on avait deja yield
                logger.info(f"💭 CoT: raisonnement extrait ({len(reasoning)} chars), reponse {len(answer)} chars")
                response_content = answer
            else:
                # Fallback: si le parsing echoue, utiliser la reponse brute
                logger.debug("💭 CoT: parsing non structure, utilisation reponse brute")
                response_content = strip_reasoning_if_needed(response_content)

        # V10.3h : ArchonRefiner — auto‑correction post‑génération
        refined = await self.archon_refiner.refine(
            response_content,
            rag_context=rag_context,
            rag_score=rag_result.top_score if rag_result else 0.0,
            intent=intent,
        )
        if refined != response_content:
            response_content = refined
            yield "\n\n🔮 **Vérification Archon : réponse raffinée**\n"

        # V10.3f : Enregistrer la réponse dans l'historique session
        self.session_store.add_message(
            session_id, "assistant", response_content,
            metadata={"intent": intent, "duration_ms": int(duration * 1000)},
        )

        # ── 8. Finalisation ──
        result = self._finalize(response_content, duration, intent, rag_result)
        event_data = result.to_dict()
        # Enrichir avec les données RAG pour le dashboard d'observabilité
        if rag_result:
            event_data["rag_result"] = {
                "documents_found": getattr(rag_result, "documents_found", 0),
                "chunks_retrieved": getattr(rag_result, "chunks_retrieved", 0),
                "chunks_injected": getattr(rag_result, "chunks_injected", 0),
                "top_score": getattr(rag_result, "top_score", 0.0),
                "retrieval_time_ms": getattr(rag_result, "retrieval_time_ms", 0.0),
                "rejected_chunks": getattr(rag_result, "rejected_chunks", 0),
                "rejection_reason": getattr(rag_result, "rejection_reason", ""),
                "sources": getattr(rag_result, "sources", []),
                "query_rewritten": getattr(rag_result, "query_rewritten", ""),
                "tokens_injected": getattr(rag_result, "tokens_injected", 0),
                "diagnostic": getattr(rag_result, "diagnostic", None),
            }
            event_data["rag_score"] = round(getattr(rag_result, "top_score", 0.0), 2)
        await self.event_bus.emit("generation_complete", event_data)

        # Émission séparée rag_score pour le dashboard
        rag_score_val = event_data.get("rag_score", 0.0)
        sources_list = []
        if rag_result and hasattr(rag_result, "sources"):
            sources_list = list(rag_result.sources)
        self.event_bus.emit_sync("rag_score", {
            "score": rag_score_val,
            "sources": sources_list,
        })

        # ── 10. Mémoire ──
        if intent != "COMPLEX":
            await self.llm_cache.set(query, response_content)
        # V16 FIX: SessionMemory unifié (FIFO 6 messages) — remplace MemoryStore fragmenté
        self.session_memory.add_interaction(original_query, response_content)
        # Aussi sauvegarder dans MemoryStore pour compatibilité dashboard/observabilité
        self.memory_store.add_message("user", original_query)
        self.memory_store.add_message("assistant", response_content)

        # NURU V6 : Learning Loop — enregistrement de la trace
        asyncio.create_task(self.trace_collector.record(
            query=original_query,
            response=response_content[:500],
            mode="CLOUD" if intent == "COMPLEX" else "LOCAL",
            confidence=result.confidence,
            tokens_prompt=result.tokens_prompt or len(full_prompt) // 4,
            tokens_generated=result.tokens_generated,
            latency_ms=int(duration * 1000) if 'duration' in dir() else 0,
            model=result.model,
        )).add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

        # ── 11. Long-Term Memory : extraction post-réponse ──
        asyncio.create_task(self._ltm_extract_post_response(
            query=original_query,
            response=response_content,
            intent=intent,
        )).add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    def set_long_term_memory(self, ltm):
        """Injecte le module Long-Term Memory (injection de dépendance)."""
        self.long_term_memory = ltm
        logger.info("🧠 Long-Term Memory activée")

    async def _ltm_extract_post_response(self, query: str, response: str, intent: str):
        """Extraction asynchrone des faits après chaque réponse (fire-and-forget)."""
        if not self.long_term_memory:
            return
        try:
            history = [
                {"role": "user", "content": query},
                {"role": "assistant", "content": response},
            ]
            facts = await self.long_term_memory.extract_facts(history)
            for fact in facts:
                self.long_term_memory.store_fact(
                    fact_type=fact.get("fact_type", "other"),
                    content=fact.get("content", ""),
                    source="conversation",
                    confidence=fact.get("confidence", 0.8),
                )
        except (MemoryError, RAGError) as e:
            logger.debug(f"🧠 LTM extrait post-réponse ignoré ({e})")

    # ─── Privées (conservées) ───

    def _route_to_intent(self, decision: str) -> str:
        return {
            "LOCAL_RAG": "RAG",
            "DOCUMENT_KEYWORD": "RAG",
            "GENERAL_KNOWLEDGE": "GENERAL",
            "CLOUD_GROQ": "COMPLEX",
            "WEB": "COMPLEX",
            "CLARIFICATION": "SIMPLE",
            "SIMPLE": "SIMPLE",
        }.get(decision, "GENERAL")

    def _model_for_intent(self, intent: str) -> str:
        """Mappe un intent au nom de famille de modèle."""
        return {
            "COMPLEX": "llama",
            "RAG": "phi",
            "GENERAL": "phi",
            "SIMPLE": "phi",
        }.get(intent, "phi")

    # ── Helpers Self-Consistency ─────────────────────────────────────

    def _build_self_consistency_prompt(
        self,
        system_prompt: str,
        full_prompt: str,
        query: str,
        rag_context: str,
        intent: str,
    ) -> str:
        """Construit le prompt de base pour Self-Consistency (sans duplication)."""
        # Le full_prompt contient déjà system_prompt + rag_context + instructions
        # On retourne juste la partie à compléter
        return full_prompt

    async def _generate_sc_response(
        self,
        prompt: str,
        intent: str,
        temperature: float,
    ) -> str:
        """Génère une réponse complète (non-streaming) pour Self-Consistency.
        
        Utilise le LocalLLM directement avec temperature variable.
        """
        # Utiliser la méthode generate (non-streaming) du LocalLLM
        return await self.local_llm.generate(
            prompt=prompt,
            intent=intent,
            temperature=temperature,
        )