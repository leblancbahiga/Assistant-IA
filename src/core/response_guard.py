"""
V10.3e — StrictRAGGuard : 3 modes, post‑génération, is_free intégré.

3 modes de réponse :
  - STRICT : refuse toute réponse non ancrée dans les chunks
  - HYBRID (défaut) : RAG d'abord, connaissances générales si pas de preuves
  - FREE : pas de grounding, conversation libre
"""
import enum
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class ResponseMode(enum.Enum):
    STRICT = "strict"   # Uniquement documents. Refus si pas de preuves.
    HYBRID = "hybrid"   # (DÉFAUT) RAG d'abord, puis modèle si pas de preuves.
    FREE = "free"       # Pas de grounding. Conversation libre.


class StrictRAGGuard:
    """Bride la génération du LLM selon le mode configuré.

    En mode STRICT, toute réponse sans citation documentaire valide est
    remplacée par un refus explicite.  En mode FREE, la recherche RAG est
    contournée (conversation libre).
    """

    def __init__(self, mode: str = "hybrid"):
        self.mode = ResponseMode(mode.lower())
        logger.info("🔒 StrictRAGGuard: mode=%s", self.mode.value)

    def set_mode(self, mode: str):
        self.mode = ResponseMode(mode.lower())
        logger.info("🔒 StrictRAGGuard: mode → %s", self.mode.value)

    # ── Propriétés ──────────────────────────────────────────────────────

    @property
    def is_strict(self) -> bool:
        return self.mode == ResponseMode.STRICT

    @property
    def is_free(self) -> bool:
        return self.mode == ResponseMode.FREE

    # ── Post‑génération ─────────────────────────────────────────────────

    def check_response(self, response: str, rag_context: str) -> bool:
        """Vérifie si la réponse est acceptable selon le mode actif.

        Retourne True si acceptable, False si doit être refusée.
        Redondances avec EvidenceVerifier, mais sert de garde‑fou en
        HYBRID mode (où EvidenceVerifier ne bloque pas).
        """
        if self.mode == ResponseMode.FREE:
            return True

        if self.mode == ResponseMode.STRICT:
            if not rag_context.strip():
                logger.warning("🔒 StrictRAG: refus — aucun contexte RAG")
                return False
            citations = re.findall(r"\[Source:\s*([^\]]+)\]", response)
            if not citations:
                logger.warning("🔒 StrictRAG: refus — aucune citation")
                return False
            valid = [c for c in citations if "AUCUNE SOURCE" not in c.upper()]
            if not valid:
                logger.warning("🔒 StrictRAG: refus — citations vides uniquement")
                return False

        # HYBRID : pas de blocage, même sans citation
        return True

    # ── Messages ─────────────────────────────────────────────────────────

    def refuse_message(self, query: str) -> str:
        """Message de refus.  Le paramètre ``query`` est ignoré en STRICT."""
        if self.mode == ResponseMode.STRICT:
            return (
                "⚠️ Je n'ai pas trouvé cette information dans vos documents.\n\n"
                "En mode STRICT, je ne peux répondre qu'à partir des documents "
                "indexés.  Passez en mode HYBRID dans les Paramètres si vous "
                "voulez que j'utilise aussi mes connaissances générales."
            )
        return (
            "⚠️ Information absente de vos documents.  "
            "Vérifiez que le fichier est indexé ou reformulez votre requête."
        )
