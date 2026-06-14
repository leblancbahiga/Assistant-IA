"""NURU V4.5 — Orchestrateur asynchrone principal.

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
from src.core.exceptions import (
    OrchestratorError, RAGError, LLMError, MemoryError,
    RouterError, ConfigError, GuardError,
)
from src.ai.verifier import EvidenceVerifier
from src.token_juice import TokenJuice
from src.learning.trace_collector import TraceCollector
from src.cache.llm_cache import LLMCache
from src.orchestration import RAGOrchestrator, LLMGenerator

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
    """Orchestrateur asynchrone du pipeline NURU V4.5.

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
        reflection_engine=None,
        system_prompt_builder=None,  # V4.5 : callback pour construire le prompt système
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
        self.reflection = reflection_engine
        self._system_prompt_builder = system_prompt_builder
        # NURU V5 : Mode Strict RAG depuis config
        self.response_guard = StrictRAGGuard(config.response_mode)
        # NURU V5 : Vérificateur de citations
        self.evidence_verifier = EvidenceVerifier()
        # NURU V6 : Middleware de compression de contexte (TokenJuice)
        tj_enabled = getattr(config, 'token_juice_enabled', True)
        self.token_juice = TokenJuice(
            enabled=tj_enabled,
            max_chunk_chars=getattr(config, 'token_juice_max_chunk_chars', 2000),
        )
        # NURU V6 : Learning Loop — collecteur de traces
        self.trace_collector = TraceCollector()
        # NURU V4.5 : Long-Term Memory — faits utilisateur structurés
        self.long_term_memory = None  # Initialisé via set_long_term_memory()
        # Suivi du dernier résultat RAG pour l'observabilité UI
        self.last_rag_result = None

        # V10.2 : Cache LLM multi-niveau (L1 RAM + L2 SQLite)
        self.llm_cache = LLMCache(self.memory_store)

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
    ) -> AsyncGenerator[str, None]:
        """Pipeline complet : route → RAG → génère → stream.

        Yields les tokens de réponse.
        """
        # ── 1. Contexte avec état réseau réel (NURU V5) ──
        is_online = await self.llm_gen.check_connectivity()
        ctx = QueryContext.from_runtime(
            query, session_id,
            is_online=is_online,
        )
        # NURU V6 : TokenJuice — compression de la requête avant routage
        original_query = query
        query = self.token_juice.compress_query(query)
        if query != original_query and len(query) < len(original_query):
            logger.debug(
                f"🧃 TokenJuice: requête compressée "
                f"{len(original_query)}→{len(query)} chars"
            )
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
                    asyncio.create_task(audio_engine.speak(cached))
                yield cached
                return

        # ── 4. Récupération contexte (RAGOrchestrator multi-sous-requêtes) ──
        rag_context, web_context, merged_result = await self.rag_pipeline.retrieve_multi(
            query, intent, rag_context, rag_result,
        )
        rag_result = merged_result or rag_result

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
        # NURU V4.5 : injection des faits utilisateur Long-Term Memory
        user_facts_str = ""
        if self.long_term_memory:
            relevant_facts = await self.long_term_memory.get_relevant_facts(query, limit=10)
            if relevant_facts:
                user_facts_str = self.long_term_memory.format_facts_for_prompt(relevant_facts)
        system_prompt, full_prompt = self._build_prompt(intent, query, rag_context, web_context, user_facts_str=user_facts_str)

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

        # ── 7. Génération (streaming) ──
        response_content = ""
        start_gen = time.time()

        try:
            async for token in self.llm_gen.generate(
                system_prompt, full_prompt, query, intent, ctx,
                web_context=web_context, rag_context=rag_context,
                original_query=original_query,
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

        # ── 9. Réflexion ──
        if self.reflection:
            analysis = await self.reflection.analyze(
                query=query, response=response_content,
                metadata={"intent": intent, "latency_ms": int(duration * 1000)},
            )
            analysis_dict = analysis if isinstance(analysis, dict) else {}
            self.memory_store.add_reflection(
                query=query, feedback=str(analysis),
                score=1.0 - analysis_dict.get("hallucination_risk", 0),
            )

        # ── 10. Mémoire ──
        if intent != "COMPLEX":
            await self.llm_cache.set(query, response_content)
        self.memory_store.add_message("user", query)
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
        ))

        # ── 11. Long-Term Memory : extraction post-réponse ──
        asyncio.create_task(self._ltm_extract_post_response(
            query=original_query,
            response=response_content,
            intent=intent,
        ))

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

    def _build_prompt(self, intent, query, rag_context, web_context, user_facts_str=""):
        full_rag = ""
        if intent == "COMPLEX":
            full_rag = web_context + ("\n\n" + rag_context if rag_context else "")
        else:
            full_rag = rag_context

        # Construire le prompt système via le callback NuruCore
        if self._system_prompt_builder:
            system_prompt = self._system_prompt_builder(
                intent=intent,
                facts=self.memory_store.get_recent_facts(limit=20),
                procedures=self.memory_store.get_procedures(),
            )
        else:
            system_prompt = f"Tu es NURU, assistant personnel de Leblanc."

        # NURU V4.5 : Injection des faits utilisateur long terme dans le système
        if user_facts_str:
            system_prompt += f"\n\n## INFORMATIONS SUR L'UTILISATEUR\n{user_facts_str}"

        if self.context_budget:
            # Formater user_facts en liste pour le budget
            user_facts_lines = user_facts_str.split("\n") if user_facts_str else []
            full_prompt = self.context_budget.allocate(
                system=system_prompt,
                rag=full_rag,
                facts=self.memory_store.get_recent_facts(limit=20),
                history=self.memory_store.get_recent_history(limit=8),
                user_facts=user_facts_lines,
                include_system=(intent != "COMPLEX"),
            )
        else:
            full_prompt = f"{system_prompt}\n\n{full_rag}"

        if intent == "COMPLEX":
            full_prompt += f"\n## QUESTION À TRAITER :\n{query}"
            if full_rag.strip() and "AUCUNE SOURCE" not in full_rag:
                full_prompt += (
                    f"\n\n## INSTRUCTION — CONTEXTE DISPONIBLE\n"
                    f"Le CONTEXTE ci-dessus contient des documents de l'utilisateur. "
                    f"Utilise- les en PRIORITÉ pour répondre.\n"
                    f"- Consulte d'abord le contexte dans ta réponse.\n"
                    f"- Complète avec tes connaissances si nécessaire.\n"
                    f"- Cite les sources quand tu utilises le contexte.\n"
                )
        elif intent == "GENERAL":
            # V10.1 : Connaissances générales — aucune instruction RAG stricte
            full_prompt += (
                f"\n\n## QUESTION (connaissances générales)\n"
                f"Réponds avec tes connaissances. Si tu n'es pas certain, dis-le.\n\n"
                f"{query}<|end|>\n<|assistant|>\n"
            )
        elif intent == "RAG" and full_rag.strip() and "AUCUNE SOURCE" not in full_rag:
            full_prompt += (
                f"\n\n## INSTRUCTION STRICTE — RAG UNIQUEMENT\n"
                f"Tu dois répondre UNIQUEMENT à partir du CONTEXTE ci-dessus "
                f"(entre === DÉBUT DU CONTEXTE === et === FIN DU CONTEXTE ===).\n"
                f"- N'utilise PAS tes connaissances internes.\n"
                f"- Si l'information n'est pas dans le contexte, dis "
                f"\"Je ne trouve pas cette information dans les documents.\"\n"
                f"- N'invente RIEN. Ne complète PAS.\n"
                f"- Cite la source avec [Source: nom_du_fichier].\n\n"
                f"{query}<|end|>\n<|assistant|>\n"
            )
        else:
            full_prompt += f"{query}<|end|>\n<|assistant|>\n"
        return system_prompt, full_prompt

    def _finalize(self, response, duration, intent, rag_result):
        tokens = len(response) // 4
        tps = tokens / duration if duration > 0 else 0
        model = "local" if intent != "COMPLEX" else "cloud"
        route = "LOCAL" if intent != "COMPLEX" else "CLOUD"
        rag_score = (rag_result.top_score if rag_result else 0) or getattr(self.rag_engine, "last_top_score", 0)

        if self.runtime:
            self.runtime.update_generation_stats(
                tokens=tokens, seconds=duration, model=model,
                route=route, rag_score=rag_score,
            )
        return OrchestratorResult(
            response=response, route=route, confidence=rag_score,
            duration_s=duration, tokens_generated=tokens,
            tokens_per_sec=tps, model=model,
        )
