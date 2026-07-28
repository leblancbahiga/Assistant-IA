"""DynamicPromptBuilder V12 — Fusion des _build_prompt() d'orchestrator et context_manager."""
import logging
from typing import Optional, Callable, Any

from src.core.prompt_guard import (
    sanitize_for_prompt_injection,
    sanitize_document_content,
    build_safe_user_facts_block,
)

logger = logging.getLogger(__name__)


class DynamicPromptBuilder:
    """Build prompts dynamiquement avec budget tokens + formatage modèle.

    Fusionne les logiques de:
      - orchestrator._build_prompt() (routing, sanitization, context allocation)
      - context_manager._build_prompt() (formatage par tags modèle)
    """

    def build_prompt(
        self,
        intent: str,
        query: str,
        rag_context: Optional[str] = None,
        web_context: Optional[str] = None,
        user_facts_str: str = "",
        session_id: Optional[str] = None,
        system_prompt_builder: Optional[Callable] = None,
        memory_store: Optional[Any] = None,
        session_store: Optional[Any] = None,
        context_budget: Optional[Any] = None,
        session_max_context: int = 8,
        model_family: str = "phi",
        confidence_label: str | None = None,  # V16 FIX
    ):
        """Build le prompt complet — copie exacte de orchestrator._build_prompt() lignes 471-570.

        Parameters
        ----------
        intent : str
            Type d'intention (COMPLEX, GENERAL, RAG, etc.)
        query : str
            Requête utilisateur
        rag_context : str, optional
            Contexte documentaire RAG
        web_context : str, optional
            Contexte web (pour COMPLEX)
        user_facts_str : str
            Faits utilisateur
        session_id : str, optional
            ID de session pour contexte conversationnel
        system_prompt_builder : Callable, optional
            Callback pour construire le prompt système (self._system_prompt_builder)
        memory_store : Any, optional
            Store mémoire avec get_recent_facts(), get_procedures(), get_recent_history()
        session_store : Any, optional
            Store session avec build_context()
        context_budget : Any, optional
            Gestionnaire de budget tokens avec allocate()
        session_max_context : int
            Nombre max de messages de contexte de session (self._session_max_context)
        model_family : str
            Famille de modèle pour le formatage des tags
        """
        full_rag = ""
        if intent == "COMPLEX":
            full_rag = web_context + ("\n\n" + rag_context if rag_context else "")
        else:
            full_rag = rag_context

        # AUDIT V10.3 — S-002b : sanitiser le contenu RAG avant injection dans le prompt.
        # Le contenu vient de documents indexés potentiellement contrôlés par des tiers
        # (CVs, rapports, fichiers publiques) et constitue la surface d'injection #1.
        if full_rag:
            full_rag = sanitize_document_content(full_rag, max_chars=4000)

        # AUDIT V10.3 — S-002 : sanitiser la query AVANT l'injection dans le template.
        safe_query = sanitize_for_prompt_injection(query, max_chars=1000)

        # Construire le prompt système via le callback NuruCore
        if system_prompt_builder:
            system_prompt = system_prompt_builder(
                intent=intent,
                facts=memory_store.get_recent_facts(limit=20) if memory_store else [],
                procedures=memory_store.get_procedures() if memory_store else [],
                confidence_label=confidence_label,  # V16 FIX
            )
        else:
            from src.identity_manager import IdentityManager
            identity = IdentityManager.load()
            system_prompt = (
                f"Tu es NURU, assistant personnel de {identity['user_name']}."
                " Tu réponds TOUJOURS en français, de manière naturelle et fluide."
            )

        # V10.3f : Injection contexte conversationnel de session
        if session_id:
            try:
                session_ctx = session_store.build_context(
                    session_id, max_messages=session_max_context)
                if session_ctx:
                    # AUDIT V10.3c — sanitiser le contexte de session aussi (historique user)
                    sanitized_session = sanitize_for_prompt_injection(session_ctx, max_chars=2000)
                    system_prompt += f"\n\n{sanitized_session}"
            except Exception:
                logger.debug("SessionStore: erreur injection contexte", exc_info=True)

        # AUDIT V10.3 — wrap user_facts_str dans un bloc sécurisé
        # Avant : `f"... {user_facts_str}"` injectait les faits tels quels.
        # Maintenant : wrap avec délimiteurs + sanitization par fait.
        if user_facts_str:
            facts_list = [
                line.strip("- ").strip()
                for line in user_facts_str.split("\n")
                if line.strip()
            ]
            safe_facts_block = build_safe_user_facts_block(facts_list)
            if safe_facts_block:
                system_prompt += f"\n\n{safe_facts_block}"

        if context_budget:
            # Formater user_facts en liste pour le budget
            user_facts_lines = user_facts_str.split("\n") if user_facts_str else []
            full_prompt = context_budget.allocate(
                system=system_prompt,
                rag=full_rag,
                facts=memory_store.get_recent_facts(limit=20) if memory_store else [],
                history=memory_store.get_recent_history(limit=8) if memory_store else [],
                user_facts=user_facts_lines,
                include_system=(intent != "COMPLEX"),
            )
        else:
            full_prompt = f"{system_prompt}\n\n{full_rag}"

        if intent == "COMPLEX":
            full_prompt += f"\n## QUESTION À TRAITER :\n{safe_query}"
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
            # AUDIT V10.3 — utiliser safe_query
            full_prompt += (
                f"\n\n## QUESTION (connaissances générales)\n"
                f"Réponds avec tes connaissances. Si tu n'es pas certain, dis-le.\n\n"
                f"{safe_query}"
            )
        elif intent == "RAG" and full_rag.strip() and "AUCUNE SOURCE" not in full_rag:
            full_prompt += (
                f"\n\n## INSTRUCTION — CONTEXTE DISPONIBLE\n"
                f"Le CONTEXTE ci-dessus contient des documents de l'utilisateur.\n"
                f"Utilise-le en priorité pour répondre.\n"
                f"- Si le contexte contient l'information, base-toi dessus.\n"
                f"- Si le contexte ne contient pas l'information, utilise tes connaissances.\n"
                f"- Si l'utilisateur énonce une information à retenir, "
                f"accuse réception et propose de la mémoriser.\n"
                f"- Cite la source quand tu utilises le contexte. [Source: fichier]\n\n"
                f"{safe_query}"
            )
        else:
            # AUDIT V10.3 — utiliser safe_query
            full_prompt += f"{safe_query}"
        return system_prompt, full_prompt

    def _format_with_model_tags(
        self,
        system: str,
        rag: str,
        facts: str,
        history: str,
        user_facts: str = "",
        include_system: bool = True,
        model_family: str = "phi",
    ) -> str:
        """Assemble le prompt final.

        Copie exacte de context_manager._build_prompt() lignes 41-64.
        """
        parts = []
        if include_system:
            parts.append(f"{system}\n")

        if rag.strip():
            parts.append(f"## CONTEXTE DOCUMENTAIRE (SOURCES)\n{rag.strip()}\n")
        else:
            parts.append(f"## CONTEXTE DOCUMENTAIRE (SOURCES)\n[AUCUNE SOURCE DOCUMENTAIRE PERTINENTE TROUVÉE]\n")

        if user_facts.strip():
            parts.append(f"## INFORMATIONS SUR L'UTILISATEUR\n{user_facts.strip()}\n")

        if history.strip():
            parts.append(f"## HISTORIQUE RÉCENT\n{history.strip()}\n")

        if not include_system:
             parts.append("\n--- FIN DU CONTEXTE ---\n")

        return "".join(parts)
