"""
LLM Generator — Orchestrateur dédié à la génération LLM V10.2.

Extrait de NuruOrchestrator pour découpler :
  - Génération cloud/local avec streaming
  - Stratégie Archon (RAG local + synthèse cloud)
  - Cloud-first fallback
  - Connectivity checking
  - Temperature management

Utilisation :
  gen = LLMGenerator(local_llm, cloud_llm, policy_engine, runtime, event_bus)
  async for token in gen.generate(system_prompt, full_prompt, query, intent, ctx, ...):
      ...
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

from src.core.exceptions import LLMError, RAGError

logger = logging.getLogger(__name__)


def _extract_user_facts(system_prompt: str) -> str:
    """Extrait la section 'Ce que tu sais sur [Utilisateur]' du system_prompt.

    Retourne une chaîne vide si la section est absente.
    """
    from src.identity_manager import IdentityManager
    identity = IdentityManager.load()
    marker = f"## Ce que tu sais sur {identity['user_name']}"
    start = system_prompt.find(marker)
    if start == -1:
        return ""
    # Lire jusqu'au prochain '##' ou fin de chaîne
    after = start + len(marker)
    end = system_prompt.find("\n## ", after)
    if end == -1:
        section = system_prompt[start:]
    else:
        section = system_prompt[start:end]
    return section.strip()


class LLMGenerator:
    """Sous-orchestrateur de génération LLM : cloud/local streaming + fallback."""

    def __init__(self, local_llm, cloud_llm, policy_engine, runtime, event_bus, session_store=None):
        self.local_llm = local_llm
        self.cloud_llm = cloud_llm
        self.policy_engine = policy_engine
        self.runtime = runtime
        self.event_bus = event_bus
        self.session_store = session_store
        self.last_tokens = 0  # V17: compteur de tokens pour metriques dashboard

    # ══════════════════════════════════════════
    # 1. Connectivité
    # ══════════════════════════════════════════

    async def check_connectivity(self) -> bool:
        """Vérifie la connectivité Internet avec timeout court (2s)."""
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

    # ══════════════════════════════════════════
    # 2. Génération principale
    # ══════════════════════════════════════════

    async def generate(
        self,
        system_prompt: str,
        full_prompt: str,
        query: str,
        intent: str,
        ctx,
        web_context: str = "",
        rag_context: str = "",
        original_query: str = "",
        stream_session=None,  # V15 P2 #26 : StreamSession optionnel
        session_id: str = "", # V16.1 : injection historique conversation cloud
    ) -> AsyncGenerator[str, None]:
        """Section 7 : Génération avec fallback cloud/local.

        Yields les tokens de réponse.
        Optionnel : stream_session pour callbacks + abort.
        """
        ram_too_low = ctx.ram_free_mb < 1000
        hybrid = getattr(ctx, 'hybrid_strategy', 'local_only')
        cloud_temp = 0.1 if rag_context.strip() else 0.7
        user_message = original_query or query

        # ── Intent-based cloud routing (no RAM/swap decisions) ──
        # Cloud UNIQUEMENT pour COMPLEX (raisonnement) + WEB (recherche)
        # Local pour tout le reste (GENERAL, RAG, SIMPLE, etc.)
        use_cloud_first = (
            (intent in ("COMPLEX", "WEB"))
            and ctx.is_online
        )

        # "verify" hybrid strategy needs cloud (confidence verification)
        if hybrid == "verify" and ctx.is_online:
            use_cloud_first = True

        if use_cloud_first:
            if not ctx.is_online:
                logger.warning("☁️ Cloud demandé mais hors-ligne → fallback local")
            else:
                logger.info(f"☁️ Cloud (intent={intent}, hybrid={hybrid}, temp={cloud_temp})")
                # V17: utiliser le system_prompt du pipeline (conserve les instructions
                # de mode RAG, format de citation, etc.) au lieu de le reconstruire
                cloud_system = system_prompt
                if rag_context.strip():
                    cloud_system += (
                        f"\n\n## CONTEXTE DE VOS DOCUMENTS\n"
                        f"{rag_context}\n"
                    )
                if web_context.strip():
                    cloud_system += f"\n\n## CONTEXTE DE RECHERCHE WEB\n{web_context}\n"
                if session_id and self.session_store:
                    session_ctx = self.session_store.build_context(session_id, max_messages=8)
                    if session_ctx:
                        cloud_system += "\\n" + session_ctx + "\\n"
                anchored_prompt = (
                    f"En te basant sur le contexte ci-dessus, "
                    f"réponds à la question suivante : {user_message}"
                )
                logger.info(f"☁️ Cloud call — user='{user_message[:60]}' | temp={cloud_temp} | rag={len(rag_context)} chars")
                n_tok = 0
                async for token in self.cloud_llm.generate_stream(
                    anchored_prompt, intent=intent, system_prompt=cloud_system, temperature=cloud_temp
                ):
                    n_tok += 1
                    yield token
                self.last_tokens = n_tok
                return

        # ── Local LLM (tout le reste) ──
        logger.info(f"💻 Local (intent={intent}, hybrid={hybrid})")
        try:
            gen = self.local_llm.generate_stream(full_prompt, intent=intent)
        except Exception as e:
            logger.error(f"💻 Local init error: {e}")
            yield f"💻 Erreur locale: {e}"
            return
        if self.runtime:
            n_tok = 0
            async for token in self.runtime.schedule_generator("generation", gen):
                if stream_session and stream_session.is_cancelled:
                    break
                n_tok += 1
                yield token
                if stream_session:
                    stream_session.emit(token)
            self.last_tokens = n_tok
        else:
            n_tok = 0
            async for token in gen:
                if stream_session and stream_session.is_cancelled:
                    break
                n_tok += 1
                yield token
                if stream_session:
                    stream_session.emit(token)
            self.last_tokens = n_tok
