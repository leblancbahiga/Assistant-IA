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

    def __init__(self, local_llm, cloud_llm, policy_engine, runtime, event_bus):
        self.local_llm = local_llm
        self.cloud_llm = cloud_llm
        self.policy_engine = policy_engine
        self.runtime = runtime
        self.event_bus = event_bus

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
    ) -> AsyncGenerator[str, None]:
        """Section 7 : Génération avec fallback cloud/local.

        Yields les tokens de réponse.
        """
        ram_too_low = ctx.ram_free_mb < 1000
        hybrid = getattr(ctx, 'hybrid_strategy', 'local_only')
        cloud_temp = 0.1 if rag_context.strip() else 0.7
        user_message = original_query or query

        # ── Stratégie Archon ──
        if hybrid == "rag" and intent == "RAG" and ctx.is_online and rag_context.strip():
            logger.info("☁️ Stratégie Archon: RAG local → synthèse cloud")
            user_facts_section = _extract_user_facts(system_prompt)
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
                f"En te basant EXCLUSIVEMENT sur les DOCUMENTS ci-dessus, "
                f"réponds à la question suivante : {user_message}\n\n"
                f"Réponse :"
            )
            if user_facts_section:
                cloud_system += f"\n\n{user_facts_section}"
            logger.info(f"☁️ Archon cloud call — user='{user_message[:60]}' | temp={cloud_temp} | rag={len(rag_context)} chars")
            async for token in self.cloud_llm.generate_stream(
                user_message, intent=intent, system_prompt=cloud_system, temperature=cloud_temp
            ):
                yield token
            return

        # ── Cloud-first ──
        use_cloud_first = ctx.is_online or self.policy_engine.should_use_cloud(ctx)

        if use_cloud_first or hybrid == "verify":
            if not ctx.is_online:
                logger.warning("☁️ Cloud demandé mais hors-ligne → fallback local")
            else:
                logger.info(f"☁️ Cloud (intent={intent}, RAM: {ctx.ram_free_mb} MB, hybrid={hybrid}, temp={cloud_temp})")
                from src.identity_manager import IdentityManager
                identity = IdentityManager.load()
                cloud_system = f"Tu es NURU, assistant personnel de {identity['user_name']}. Tu réponds en français.\n\n"
                user_facts_section = _extract_user_facts(system_prompt)
                if rag_context.strip():
                    cloud_system += (
                        f"## CONTEXTE DE VOS DOCUMENTS (prioritaire, utilise EXCLUSIVEMENT ces informations)\n"
                        f"Les informations ci-dessous sont extraites de VOS documents personnels. "
                        f"Elles sont prioritaires sur toute autre source.\n"
                        f"- N'invente PAS d'information. Utilise UNIQUEMENT ce contexte.\n"
                        f"- Si l'information n'est pas dans le contexte, dis "
                        f"\"Je ne trouve pas cette information dans vos documents.\"\n"
                        f"- Cite tes sources avec [Source: fichier].\n"
                        f"{rag_context}\n\n"
                    )
                if web_context.strip():
                    cloud_system += f"## CONTEXTE DE RECHERCHE WEB\n{web_context}\n\n"
                if user_facts_section:
                    cloud_system += f"\n{user_facts_section}\n"
                anchored_prompt = (
                    f"En te basant sur le contexte ci-dessus, "
                    f"réponds à la question suivante : {user_message}"
                )
                logger.info(f"☁️ Cloud call — user='{user_message[:60]}' | temp={cloud_temp} | rag={len(rag_context)} chars")
                async for token in self.cloud_llm.generate_stream(
                    anchored_prompt, intent=intent, system_prompt=cloud_system, temperature=cloud_temp
                ):
                    yield token
                return

        # ── Fallback local ──
        logger.info(f"💻 Local (intent={intent}, hybrid={hybrid})")
        try:
            gen = self.local_llm.generate_stream(full_prompt, intent=intent)
            if self.runtime:
                async for token in self.runtime.schedule_generator("generation", gen):
                    yield token
            else:
                async for token in gen:
                    yield token
        except (LLMError, RAGError) as e:
            logger.error(f"Local fail: {e}. Fallback Cloud.")
            yield " [Bascule Cloud...] "
            cloud_prompt = user_message
            cloud_sys = system_prompt
            if rag_context and rag_context.strip() and "AUCUNE SOURCE" not in rag_context:
                cloud_sys = (
                    f"{system_prompt}\n\n"
                    f"## CONTEXTE DOCUMENTAIRE (SOURCES)\n{rag_context.strip()}\n\n"
                    f"Instructions : utilise EXCLUSIVEMENT le contexte ci-dessus pour répondre. "
                    f"Si l'information n'y est pas, dis-le clairement.\n\n"
                    f"Question : {user_message}"
                )
                cloud_prompt = user_message
            logger.info(f"☁️ Local-fail fallback — user='{user_message[:60]}' | temp={cloud_temp} | rag={len(rag_context)} chars")
            async for token in self.cloud_llm.generate_stream(
                cloud_prompt, intent=intent, system_prompt=cloud_sys, temperature=cloud_temp
            ):
                yield token
