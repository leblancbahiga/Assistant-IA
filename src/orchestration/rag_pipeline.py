"""
RAG Pipeline — Orchestrateur dédié au pipeline documentaire V10.2.

Extrait de NuruOrchestrator pour découpler :
  - RAG retrieval + décomposition
  - Web fallback + Spotlight
  - FallbackGuard + Strict RAG
  - Vérification citations + FactChecker avec retry

Utilisation :
  rag = RAGOrchestrator(rag_engine, cloud_llm, web, event_bus, response_guard, evidence_verifier)
  await rag.retrieve_multi(query, intent)  → (rag_context, rag_result, web_context)
  await rag.verify_citations(...)
  await rag.fact_check(...)
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import AsyncGenerator, Optional

from src.config import config
from src.core.exceptions import RAGError, LLMError, ConfigError
from src.routing.router import RAG_KEYWORDS
from src.rag.speculative import SpeculativeRAG

logger = logging.getLogger(__name__)

MAX_SPOTLIGHT_CHARS = 3000


class RAGOrchestrator:
    """Sous-orchestrateur RAG : retrieve, décomposition, fallback, vérification."""

    def __init__(
        self,
        rag_engine,
        cloud_llm,
        web_search,
        event_bus,
        response_guard,
        evidence_verifier,
    ):
        self.rag_engine = rag_engine
        self.cloud_llm = cloud_llm
        self.web = web_search
        self.event_bus = event_bus
        self.response_guard = response_guard
        self.evidence_verifier = evidence_verifier
        # V15 Phase 5 (Item 39) : Speculative RAG — génération rapide parallèle
        self.speculative = SpeculativeRAG(
            rag_engine=rag_engine,
            cloud_llm=cloud_llm,
            confidence_threshold=0.7,
        )

    # ══════════════════════════════════════════
    # 1. Retrieval principal
    # ══════════════════════════════════════════

    async def retrieve_primary(self, query: str, ctx) -> tuple:
        """Section 2 : RAG retrieval unique (avant routage)."""
        rag_context, rag_result = "", None
        rag_context, rag_result = await self.rag_engine.retrieve(query)
        return rag_context, rag_result

    # ══════════════════════════════════════════
    # 2. Retrieval multi-sous-requêtes + web
    # ══════════════════════════════════════════

    async def retrieve_multi(
        self, query: str, intent: str, primary_rag_context: str, primary_rag_result
    ) -> tuple:
        """Section 4 : récupération contexte avec décomposition."""
        if intent not in ("RAG", "COMPLEX"):
            return "", "", None

        sub_queries = [query]
        if intent == "COMPLEX":
            sub_queries = await self._try_decompose(query)

        rag_contexts: list[str] = []
        merged_result = None
        web_contexts: list[str] = []

        for i, sq in enumerate(sub_queries):
            if i == 0 and primary_rag_context:
                # V10.3k — AUDIT BUG-FIX : retrieve_primary retourne (context_str, result)
                # AVANT : unpacking `rag_ctx, result = primary_rag_context` qui récursait
                # sur la string du context et tronquait silencieusement à 2 chars.
                # Conséquence : RAG complètement invisible pour le LLM downstream.
                rag_ctx = primary_rag_context
                result = primary_rag_result
                web = ""
                if intent == "COMPLEX" and self.web:
                    web = await self.web.search(sq)
            else:
                rag_ctx, result, web = await self._retrieve_one(sq, intent)
            if rag_ctx:
                rag_contexts.append(rag_ctx)
            if result and merged_result is None:
                merged_result = result
            if web:
                web_contexts.append(web)

        rag_context = "\n\n---\n\n".join(rag_contexts) if rag_contexts else ""
        web_context = "\n".join(web_contexts) if web_contexts else ""
        return rag_context, web_context, merged_result

    async def _try_decompose(self, query: str) -> list[str]:
        """Décomposition optionnelle pour requêtes complexes."""
        from src.rag.decomposer import QueryDecomposer, should_decompose

        if not should_decompose(query):
            return [query]
        try:
            decomposer = QueryDecomposer(cloud_llm=self.cloud_llm)
            decomposed = await decomposer.decompose(query)
            if len(decomposed) > 1:
                logger.info(
                    f"🔀 Décomposition: {query[:50]} → {len(decomposed)} sous-requêtes"
                )
                await self.event_bus.emit("query.decomposed", {
                    "original": query,
                    "sub_queries": decomposed,
                })
                return decomposed
        except (RAGError, ConfigError) as e:
            logger.debug(f"Décomposition non disponible: {e}")
        return [query]

    async def _retrieve_one(self, query: str, intent: str) -> tuple:
        """RAG + web parallèles pour une sous-requête."""
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
        return rag_context, rag_result, web_context

    # ══════════════════════════════════════════
    # 3. Spotlight integration
    # ══════════════════════════════════════════

    def integrate_spotlight(
        self, rag_context: str, rag_result, spotlight_ctx: str
    ) -> str:
        """Section 4.5 : Fusion Spotlight + RAG."""
        if not spotlight_ctx:
            return rag_context

        if len(spotlight_ctx) > MAX_SPOTLIGHT_CHARS:
            spotlight_ctx = spotlight_ctx[:MAX_SPOTLIGHT_CHARS] + "\n[...tronqué...]"

        if not rag_context:
            logger.info(f"🔍 Spotlight seul: {len(spotlight_ctx)} chars (RAG vide)")
            return spotlight_ctx

        rag_top_score = getattr(rag_result, 'top_score', 0.0) if rag_result else 0.0
        if rag_top_score < 0.35:
            return (
                f"[CONTENU SPOTLIGHT — Documents trouvés sur le système]\n"
                f"{spotlight_ctx}\n\n"
                f"[CONTENU INDEX RAG (score={rag_top_score:.2f})]\n"
                f"{rag_context}"
            )
        return (
            f"{rag_context}\n\n"
            f"[CONTENU SPOTLIGHT — Documents supplémentaires trouvés]\n"
            f"{spotlight_ctx}"
        )

    # ══════════════════════════════════════════
    # 4. Nettoyage contexte FAIBLE confiance
    # ══════════════════════════════════════════

    def clear_low_confidence_context(
        self, query: str, rag_context: str, rag_result, has_spotlight: bool
    ) -> str:
        """Section 4.6 : Vider le contexte si FAIBLE et aucun mot-clé trouvé."""
        if (
            rag_result
            and getattr(rag_result, 'confidence_label', 'HAUTE') == 'FAIBLE'
            and not has_spotlight
            and rag_context
            and len(rag_context) < 3000
        ):
            query_words = set(
                w.lower() for w in re.findall(r'\w+', query)
                if len(w) > 2 and w.lower() not in {
                    'de', 'la', 'le', 'les', 'du', 'des', 'un', 'une', 'et', 'ou',
                    'est', 'sont', 'dans', 'sur', 'par', 'pour', 'avec', 'que', 'qui',
                    'parle', 'moi', 'peux', 'tu', 'je', 'ne', 'pas', 'the', 'a', 'an',
                }
            )
            if query_words and not any(kw in rag_context.lower() for kw in query_words):
                logger.warning(
                    f"🔇 Contexte RAG vidé: aucun mot-clé trouvé dans {len(rag_context)} chars "
                    f"(mots-clés: {query_words})"
                )
                return ""
        return rag_context

    # ══════════════════════════════════════════
    # 5. Fallback Web
    # ══════════════════════════════════════════

    async def maybe_web_fallback(
        self, query: str, intent: str, rag_context: str
    ) -> tuple:
        """Section 5 : RAG vide → fallback Web."""
        if intent == "RAG" and not rag_context and len(query.split()) > 3 and self.web:
            query_lower = query.lower()
            has_rag_keyword = any(kw in query_lower for kw in RAG_KEYWORDS)
            if has_rag_keyword:
                logger.warning(
                    "🔒 FallbackGuard: RAG vide + mots-clés documents"
                    " → refus cloud pour éviter hallucination"
                )
                return "AUCUNE SOURCE DOCUMENTAIRE PERTINENTE TROUVÉE", "RAG"

            logger.info("RAG vide → fallback Web")
            web_context = await self.web.search(query)
            if web_context:
                return web_context, "COMPLEX"
        return rag_context, intent

    # ══════════════════════════════════════════
    # 6. FallbackGuard V2 + Strict RAG
    # ══════════════════════════════════════════

    async def check_strict_blocks(
        self, query: str, intent: str, rag_context: str, web_context: str
    ) -> Optional[str]:
        """Sections 5.5-5.6 : Retourne un message de blocage ou None."""
        # FallbackGuard V2
        if intent == "COMPLEX" and not rag_context and not web_context:
            query_lower = query.lower()
            has_rag_keyword = any(kw in query_lower for kw in RAG_KEYWORDS)
            if has_rag_keyword:
                logger.warning(
                    "🔒 FallbackGuard V2: requête documentaire sans contexte"
                    " → blocage cloud"
                )
                await self.event_bus.emit("query.strict_refused", {"query": query})
                return "⚠️ Je n'ai pas trouvé cette information dans vos documents. Vérifiez que le fichier est indexé ou reformulez votre requête."

        # Strict RAG mode
        if intent == "RAG" and self.response_guard.is_strict and not rag_context.strip():
            logger.info("🔒 Strict RAG: refus — pas de contexte documentaire")
            await self.event_bus.emit("query.strict_refused", {"query": query, "intent": intent})
            return self.response_guard.refuse_message(query)

        return None

    # ══════════════════════════════════════════
    # 7. Vérification citations post-génération
    # ══════════════════════════════════════════

    async def verify_citations(
        self, intent: str, rag_context: str, response_content: str, rag_result, query: str
    ) -> Optional[str]:
        """Section 7.5 : Vérifie les citations. Retourne message de refus ou None."""
        if not (intent == "RAG" and rag_context and response_content.strip()
                and "AUCUNE SOURCE" not in rag_context):
            return None

        chunk_sources = []
        if rag_result and hasattr(rag_result, 'chunks_retrieved'):
            try:
                if hasattr(rag_result, 'source_list'):
                    chunk_sources = rag_result.source_list
            except (AttributeError, RAGError):
                pass
        if not chunk_sources and rag_context:
            chunk_sources = re.findall(r'\[SOURCE \d+\] ([^\n]+)', rag_context)

        vr = self.evidence_verifier.verify(
            response=response_content,
            chunk_sources=chunk_sources,
            rag_context=rag_context,
        )
        if not vr.valid and self.response_guard.is_strict:
            logger.warning(f"🔒 Strict RAG: vérification échouée — {vr.reason}")
            await self.event_bus.emit("verification_failed", {
                "query": query,
                "reason": vr.reason,
                "matched": vr.matched_citations,
                "missing": vr.missing_citations,
            })
            return self.response_guard.refuse_message(query)
        return None

    # ══════════════════════════════════════════
    # 8. FactChecker + retry
    # ══════════════════════════════════════════

    async def fact_check_and_retry(
        self,
        intent: str,
        response_content: str,
        rag_context: str,
        ctx,
        query: str,
        cloud_llm,
        rag_result,
    ) -> tuple:
        """Section 7.6 : Vérification Cloud + décision régénération.

        Retourne (should_regenerate: bool, warning_msg: str|None).

        L'appelant (process_query) gère le streaming de la régénération
        via LLMGenerator.generate().
        """
        if not (intent == "RAG" and response_content.strip() and ctx.is_online
                and not ctx.already_fact_checked
                and "AUCUNE SOURCE" not in rag_context):
            return False, None

        try:
            from src.rag.fact_checker import FactChecker
            checker = FactChecker(cloud_llm=cloud_llm)

            sources_text = []
            # On utilise le rag_result passé en paramètre
            if rag_result:
                sources_text = [s.get('preview', '') for s in getattr(rag_result, 'sources', [])]
            if not sources_text and rag_context:
                sources_text = [rag_context[:500]]

            if sources_text and len(response_content) > 50:
                check = await checker.verify(response_content, sources_text)
                if not check.verified and check.issues:
                    logger.info(f"🔍 V8+ FactChecker: {len(check.issues)} problème(s)")

                    if check.needs_regenerate and not ctx.already_retried:
                        logger.info("🔄 V8+ Retry: régénération instruction stricte")
                        return True, None

                    # Avertissement sans régénération
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
                    self.event_bus.emit_sync("verification_warning", {
                        "message": warning_msg,
                        "issues": check.issues[:5],
                        "query": query,
                    })
                    return False, warning_msg

        except (RAGError, LLMError) as e:
            logger.debug(f"V8+ FactChecker ignoré: {e}")

        return False, None

    # ══════════════════════════════════════════
    # 6. Speculative RAG
    # ══════════════════════════════════════════

    async def answer_speculative(self, query: str) -> tuple:
        """Réponse spéculative : génération rapide + RAG parallèle."""
        response, is_spec = await self.speculative.answer(query)
        return response, is_spec, self.speculative.get_stats()