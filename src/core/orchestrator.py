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
from src.ai.verifier import EvidenceVerifier
from src.token_juice import TokenJuice
from src.learning.trace_collector import TraceCollector

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
        is_online = await self._check_connectivity()
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

        # ── 2. Routage avec PolicyEngine (NURU V5) ──
        route_result = await self.router.route_with_context(ctx)
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

        # ── 3. Cache sémantique ──
        if intent != "COMPLEX":
            cached, cached_diag = await self.memory_store.get_cache(query)
            if cached:
                await self.event_bus.emit("cache_hit", {"query": query})
                if use_tts and audio_engine:
                    asyncio.create_task(audio_engine.speak(cached))
                yield cached
                return

        # ── 4. Récupération contexte (avec décomposition si requête complexe) ──
        if intent in ("RAG", "COMPLEX"):
            # V8+ P10 : Décomposition des questions complexes en sous-requêtes
            from src.rag.decomposer import QueryDecomposer, should_decompose
            
            sub_queries = [query]
            if should_decompose(query):
                try:
                    decomposer = QueryDecomposer(cloud_llm=self.cloud_llm)
                    decomposed = await decomposer.decompose(query)
                    if len(decomposed) > 1:
                        sub_queries = decomposed
                        logger.info(
                            f"🔀 Décomposition: {query[:50]} → {len(sub_queries)} sous-requêtes"
                        )
                        await self.event_bus.emit("query.decomposed", {
                            "original": query,
                            "sub_queries": sub_queries,
                        })
                except Exception as e:
                    logger.debug(f"Décomposition non disponible: {e}")

            # Contextes fusionnés
            rag_contexts: list[str] = []
            merged_result = None
            web_contexts: list[str] = []

            for i, sq in enumerate(sub_queries):
                ctx, result, web = await self._retrieve_context(sq, intent)
                if ctx:
                    rag_contexts.append(ctx)
                if result and merged_result is None:
                    merged_result = result
                if web:
                    web_contexts.append(web)

            rag_context = "\n\n---\n\n".join(rag_contexts) if rag_contexts else ""
            web_context = "\n".join(web_contexts) if web_contexts else ""
            rag_result = merged_result
        else:
            rag_context, rag_result, web_context = await self._retrieve_context(query, intent)

        # NURU V6 : TokenJuice — compression du contexte RAG et web avant construction prompt
        if rag_context:
            rag_context = self.token_juice.compress(rag_context, stage="post")
        if web_context:
            web_context = self.token_juice.compress(web_context, stage="post")

        # ── 5. Fallback Web si RAG vide ──
        rag_context, intent = await self._maybe_web_fallback(
            query, intent, rag_context, rag_result, web_context
        )

        # ── 5.5 FallbackGuard V2 : bloquer cloud si mots-clés docs + contexte vide (NURU V5) ──
        if intent == "COMPLEX" and not rag_context and not web_context:
            query_lower = query.lower()
            from src.semantic_router import RAG_KEYWORDS
            has_rag_keyword = any(kw in query_lower for kw in RAG_KEYWORDS)
            if has_rag_keyword:
                logger.warning(
                    "🔒 FallbackGuard V2: requête documentaire sans contexte"
                    " → blocage cloud"
                )
                await self.event_bus.emit("query.strict_refused", {"query": query})
                yield "⚠️ Je n'ai pas trouvé cette information dans vos documents. "
                yield "Vérifiez que le fichier est indexé ou reformulez votre requête."
                return

        # ── 5.6 Mode Strict RAG (NURU V5) : refuser si aucun contexte documentaire ──
        if self.response_guard.is_strict and not rag_context.strip():
            logger.info("🔒 Strict RAG: refus — pas de contexte documentaire")
            event_data = {"query": query, "intent": intent}
            await self.event_bus.emit("query.strict_refused", event_data)
            yield self.response_guard.refuse_message(query)
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
            async for token in self._generate(system_prompt, full_prompt, query, intent, ctx, web_context=web_context, rag_context=rag_context):
                response_content += token
                yield token
        except Exception as e:
            logger.error(f"❌ Génération: {e}")
            yield f"\n[⚠️ Erreur: {e}]"
            return

        duration = time.time() - start_gen

        # ── 7.5 Vérification des citations post-génération (NURU V5) ──
        if intent == "RAG" and rag_context and response_content.strip():
            # Extraire les sources des chunks
            chunk_sources = []
            if rag_result and hasattr(rag_result, 'chunks_retrieved'):
                try:
                    # Récupérer les sources depuis le résultat RAG
                    if hasattr(rag_result, 'source_list'):
                        chunk_sources = rag_result.source_list
                except Exception:
                    pass
            if not chunk_sources and rag_context:
                # Fallback : extraire les [SOURCE N] du contexte
                chunk_sources = re.findall(r'\[SOURCE \d+\] ([^\n]+)', rag_context)

            vr = self.evidence_verifier.verify(
                response=response_content,
                chunk_sources=chunk_sources,
                rag_context=rag_context,
            )
            if not vr.valid and self.response_guard.is_strict:
                logger.warning(
                    f"🔒 Strict RAG: vérification échouée — {vr.reason}"
                )
                # En mode STRICT, remplacer la réponse par un refus
                response_content = self.response_guard.refuse_message(query)
                # On ne peut pas revenir en arrière sur les tokens déjà yield,
                # mais on note pour l'UI que la vérification a échoué
                await self.event_bus.emit("verification_failed", {
                    "query": query,
                    "reason": vr.reason,
                    "matched": vr.matched_citations,
                    "missing": vr.missing_citations,
                })

        # ── 7.6 V8+ Sprint 5 : Vérificateur de faits Cloud + retry ──
        if intent == "RAG" and response_content.strip() and ctx.is_online and not ctx.already_fact_checked:
            try:
                from src.rag.fact_checker import FactChecker
                checker = FactChecker(cloud_llm=self.cloud_llm)

                sources_text = []
                if rag_result and hasattr(rag_result, 'sources'):
                    sources_text = [s.get('preview', '') for s in rag_result.sources]
                if not sources_text and rag_context:
                    sources_text = [rag_context[:500]]

                if sources_text and len(response_content) > 50:
                    check = await checker.verify(response_content, sources_text)

                    if not check.verified and check.issues:
                        logger.info(f"🔍 V8+ FactChecker: {len(check.issues)} problème(s)")

                        if check.needs_regenerate and not ctx.already_retried:
                            ctx = ctx.with_retry().with_fact_checked()
                            logger.info("🔄 V8+ Retry: régénération avec instruction stricte")
                            yield "\n\n🔄 **Vérification : régénération en cours...**\n"

                            # Nouvelle génération avec instruction renforcée
                            strict_instruction = (
                                "\n\n## INSTRUCTION STRICTE\n"
                                "La réponse précédente contenait des affirmations non supportées par les sources.\n"
                                "Cette fois, réponds UNIQUEMENT avec les informations EXACTEMENT présentes dans le contexte ci-dessus.\n"
                                "Si une information n'est pas dans les sources, dis-le clairement. N'invente RIEN.\n"
                                "Cite chaque source utilisée.\n"
                            )
                            retry_prompt = full_prompt + strict_instruction
                            new_response = ""
                            async for token in self._generate(
                                system_prompt, retry_prompt, query, intent, ctx,
                                web_context=web_context, rag_context=rag_context
                            ):
                                new_response += token
                                yield token

                            if new_response:
                                response_content = new_response

                        # Même sans régénération, avertir l'utilisateur
                        else:
                            warning_msg = (
                                "⚠️ **Avertissement — Vérification des sources**\n\n"
                                "Certaines informations de cette réponse n'ont **pas pu être vérifiées** "
                                "contre les sources disponibles.\n\n"
                                "**Affirmations non vérifiées :**\n"
                            )
                            for issue in check.issues[:3]:
                                warning_msg += f"- {issue[:150]}\n"
                            warning_msg += (
                                "\n> *Vérifie ces points dans les documents originaux "
                                "avant de les utiliser.*\n"
                            )
                            yield "\n\n---\n" + warning_msg + "\n---\n"

                            # Émettre un événement pour le dashboard (Sprint 5.6)
                            self.event_bus.emit_sync("verification_warning", {
                                "message": warning_msg,
                                "issues": check.issues[:5],
                                "query": query,
                            })
            except Exception as e:
                logger.debug(f"V8+ FactChecker ignoré: {e}")

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
            await self.memory_store.set_cache(query, response_content)
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
        except Exception as e:
            logger.debug(f"🧠 LTM extrait post-réponse ignoré ({e})")

    # ─── Privées ───

    def _route_to_intent(self, decision: str) -> str:
        return {"LOCAL_RAG": "RAG", "CLOUD_GROQ": "COMPLEX", "WEB": "COMPLEX",
                "CLARIFICATION": "SIMPLE", "SIMPLE": "SIMPLE"}.get(decision, "SIMPLE")

    # NURU V5 : Vérification réseau réelle (remplace is_online toujours True)
    async def _check_connectivity(self) -> bool:
        """Vérifie la connectivité Internet avec timeout court (2s).
        Essais multiples : DNS Google, puis HTTP Google.
        """
        import socket
        methods = [
            ("dns", lambda: asyncio.open_connection("8.8.8.8", 53)),
            ("http", lambda: asyncio.open_connection("www.google.com", 80)),
        ]
        for name, coro_fn in methods:
            try:
                _, writer = await asyncio.wait_for(coro_fn(), timeout=1.5)
                writer.close()
                await writer.wait_closed()
                logger.debug(f"🌐 Connectivité vérifiée via {name}")
                return True
            except (OSError, asyncio.TimeoutError):
                continue
        logger.debug("🌐 Hors-ligne détecté (toutes les sondes ont échoué)")
        return False

    async def _retrieve_context(self, query: str, intent: str) -> tuple:
        rag_context, rag_result, web_context = "", None, ""
        tasks = []
        if intent in ("RAG", "COMPLEX"):
            tasks.append(self.rag_engine.retrieve(query))
        if intent == "COMPLEX" and self.web:
            tasks.append(self.web.search(query))
        if tasks:
            for c in await asyncio.gather(*tasks):
                if isinstance(c, tuple):
                    rag_context, rag_result = c
                elif isinstance(c, str):
                    web_context = c
        # Stocker pour observabilité UI
        self.last_rag_result = rag_result
        return rag_context, rag_result, web_context

    async def _maybe_web_fallback(self, query, intent, rag_context, rag_result, web_context):
        # NURU V5 : FallbackGuard — pas de cloud si RAG vide + mots-clés docs
        if intent == "RAG" and not rag_context and len(query.split()) > 3 and self.web:
            query_lower = query.lower()
            from src.semantic_router import RAG_KEYWORDS
            has_rag_keyword = any(kw in query_lower for kw in RAG_KEYWORDS)

            if has_rag_keyword and not rag_context:
                logger.warning(
                    "🔒 FallbackGuard: RAG vide + mots-clés documents"
                    " → refus cloud pour éviter hallucination"
                )
                rag_context = "AUCUNE SOURCE DOCUMENTAIRE PERTINENTE TROUVÉE"
                return rag_context, "RAG"  # Garde intent RAG → message d'absence

            logger.info("RAG vide → fallback Web")
            web_context = await self.web.search(query)
            if web_context:
                intent = "COMPLEX"
        return rag_context, intent

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

    async def _generate(self, system_prompt, full_prompt, query, intent, ctx, web_context="", rag_context=""):
        # NURU V5 : Fallback cloud renforcé — si RAM < 1 Go ET online,
        # on passe en cloud même pour RAG (évite les hallucinations du petit modèle qui swap)
        ram_too_low = ctx.ram_free_mb < 1000
        hybrid = getattr(ctx, 'hybrid_strategy', 'local_only')

        # NURU V6 : Stratégie Archon (RAG local + synthèse cloud)
        if hybrid == "rag" and intent == "RAG" and ctx.is_online and rag_context.strip():
            logger.info("☁️ Stratégie Archon: RAG local → synthèse cloud")
            # NURU V6 FIX : Prompt anti-hallucination renforcé pour Groq
            cloud_system = (
                f"Tu es NURU, assistant IA personnel. Tu dois répondre UNIQUEMENT à partir des documents ci-dessous.\n\n"
                f"## RÈGLES IMPÉRATIVES (sous peine d'être déconnecté) :\n"
                f"1. NE RIEN INVENTER — si le contexte ne contient pas l'information, dis exactement :\n"
                f"   \"Je ne trouve pas cette information dans les documents.\"\n"
                f"2. NE PAS DÉDUIRE — des projets agricoles dans un contexte ne signifie PAS que la personne est ingénieur agronome.\n"
                f"3. NE PAS GÉNÉRALISER — ne transforme pas un poste spécifique en \"expérience en gestion de projets\".\n"
                f"4. FORMAT OBLIGATOIRE — commence chaque fait par [Source: fichier] puis le fait exact trouvé.\n"
                f"5. Si tu ne peux pas citer un fait avec sa source précise, ne l'écris PAS.\n"
                f"6. Ne suggère JAMAIS de consulter d'autres documents — réponds avec ce que tu as.\n\n"
                f"=== DOCUMENTS ===\n"
                f"{rag_context}\n"
                f"=== FIN DES DOCUMENTS ===\n\n"
                f"Question : {query}\n\n"
                f"Réponse :"
            )
            async for token in self.cloud_llm.generate_stream(
                query, intent=intent, system_prompt=cloud_system
            ):
                yield token
            return

        # V8+ Sprint 5 : Cloud par défaut pour RAG/COMPLEX si online
        use_cloud_first = (intent in ("RAG", "COMPLEX") and ctx.is_online) or \
                          self.policy_engine.should_use_cloud(ctx)

        if use_cloud_first or hybrid == "verify":
            if not ctx.is_online:
                logger.warning("☁️ Cloud demandé mais hors-ligne → fallback local")
            else:
                logger.info(f"☁️ Cloud (intent={intent}, RAM: {ctx.ram_free_mb} MB, hybrid={hybrid})")
                # NURU V6 FIX : Instruction stricte pour le cloud aussi
                cloud_system = (
                    f"Tu es NURU, assistant personnel de Leblanc. Tu réponds en français.\n\n"
                )
                if rag_context.strip():
                    cloud_system += (
                        f"## CONTEXTE DE VOS DOCUMENTS (prioritaire)\n"
                        f"Les informations ci-dessous sont extraites de VOS documents personnels. "
                        f"Elles sont prioritaires sur toute autre source.\n"
                        f"- N'invente PAS d'information.\n"
                        f"- Cite tes sources avec [Source: fichier].\n"
                        f"{rag_context}\n\n"
                    )
                if web_context.strip():
                    cloud_system += (
                        f"## CONTEXTE DE RECHERCHE WEB\n{web_context}\n\n"
                    )
                async for token in self.cloud_llm.generate_stream(
                    query, intent=intent, system_prompt=cloud_system
                ):
                    yield token
                return

        # Fallback local
        logger.info(f"💻 Local (intent={intent}, hybrid={hybrid})")
        try:
            gen = self.local_llm.generate_stream(full_prompt, intent=intent)
            if self.runtime:
                async for token in self.runtime.schedule_generator("generation", gen):
                    yield token
            else:
                async for token in gen:
                    yield token
        except Exception as e:
            logger.error(f"Local fail: {e}. Fallback Cloud.")
            yield " [Bascule Cloud...] "
            # V6.2 : Inclure le contexte RAG dans le prompt cloud (pas seulement la query)
            cloud_prompt = query
            cloud_sys = system_prompt
            if rag_context and rag_context.strip() and "AUCUNE SOURCE" not in rag_context:
                cloud_sys = f"{system_prompt}\n\n## CONTEXTE DOCUMENTAIRE (SOURCES)\n{rag_context.strip()}\n\nInstructions : réponds UNIQUEMENT à partir du contexte ci-dessus. Si l'information n'y est pas, dis-le clairement."
                cloud_prompt = f"{query}\n\n[RAG context provided above]"
            async for token in self.cloud_llm.generate_stream(
                cloud_prompt, intent=intent, system_prompt=cloud_sys
            ):
                yield token

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
