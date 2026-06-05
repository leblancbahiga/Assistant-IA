"""NURU V5 — Mode Strict RAG : bride le LLM aux seules sources documentaires.

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
    remplacée par un refus explicite.
    """

    def __init__(self, mode: str = "hybrid"):
        self.mode = ResponseMode(mode.lower())
        logger.info(f"🔒 StrictRAGGuard: mode={self.mode.value}")

    def set_mode(self, mode: str):
        """Change le mode à la volée (via settings UI)."""
        self.mode = ResponseMode(mode.lower())
        logger.info(f"🔒 StrictRAGGuard: mode changé → {self.mode.value}")

    @property
    def is_strict(self) -> bool:
        return self.mode == ResponseMode.STRICT

    @property
    def is_free(self) -> bool:
        return self.mode == ResponseMode.FREE

    def check_response(self, response: str, rag_context: str) -> bool:
        """Vérifie si la réponse est acceptable selon le mode actif.

        Args:
            response: Réponse générée par le LLM
            rag_context: Contexte RAG fourni au LLM

        Returns:
            True si acceptable, False si doit être refusée
        """
        if self.mode == ResponseMode.FREE:
            return True

        if self.mode == ResponseMode.STRICT:
            # En mode STRICT, on refuse si :
            # 1. Pas de contexte RAG fourni
            if not rag_context.strip():
                logger.warning("🔒 StrictRAG: refus — aucun contexte RAG")
                return False

            # 2. Aucune citation dans la réponse
            citations = re.findall(r'\[Source:\s*([^\]]+)\]', response)
            if not citations:
                logger.warning("🔒 StrictRAG: refus — aucune citation dans la réponse")
                return False

            # 3. Citation vide ou générique (AUCUNE SOURCE)
            valid = [c for c in citations if "AUCUNE SOURCE" not in c.upper()]
            if not valid:
                logger.warning("🔒 StrictRAG: refus — citations vides uniquement")
                return False

        # HYBRID : pas de blocage, même sans citation
        return True

    def refuse_message(self, query: str) -> str:
        """Message de refus selon le mode."""
        if self.mode == ResponseMode.STRICT:
            return (
                "⚠️ Je n'ai pas trouvé cette information dans vos documents.\n\n"
                "En mode STRICT, je ne peux répondre qu'à partir des documents "
                "indexés. Passez en mode HYBRID dans les Paramètres si vous "
                "voulez que j'utilise aussi mes connaissances générales."
            )
        return (
            "⚠️ Information absente de vos documents. "
            "Vérifiez que le fichier est indexé ou reformulez votre requête."
        )
