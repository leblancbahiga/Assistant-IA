"""
NURU V8+ — Décomposeur de questions complexes (Sprint 4.3).

Scinde une question multi-parties en sous-requêtes exécutables séparément.
Chaque sous-quête passe par le pipeline RAG indépendamment et les
résultats sont fusionnés.

Règles :
- MAX_SUB_QUERIES = 3 (circuit breaker anti-explosion)
- Ne décomposer QUE si len(query) > 10 mots ET connecteurs présents
- Fallback : retourne [query] si pas de décomposition nécessaire
"""

import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constantes ──
MAX_SUB_QUERIES = 3
MIN_WORDS_FOR_DECOMPOSE = 10

# Connecteurs indiquant une question multi-parties
CONNECTORS = {
    "et", "ainsi que", "ainsi qu'", "ou", "puis", "ensuite",
    "ainsi", "également", "de plus", "par ailleurs",
    "ainsi qu’",  # typographic apostrophe
    # English
    "and", "or", "as well as", "then",
}

# Indicateurs de questions listant des critères multiples
LIST_INDICATORS = {
    "compare", "comparer", "difference", "différence",
    "liste", "list", "enumere", "énumère",
}


def should_decompose(query: str) -> bool:
    """Détermine si une requête mérite d'être décomposée.

    1. Assez longue (> 10 mots)
    2. Contient des connecteurs de coordination
    """
    if not query or not query.strip():
        return False

    words = query.lower().split()
    if len(words) < MIN_WORDS_FOR_DECOMPOSE:
        return False

    # Vérifier la présence de connecteurs
    q_lower = query.lower()
    for conn in CONNECTORS:
        if conn in q_lower:
            return True

    # Vérifier les indicateurs de listage
    for indicator in LIST_INDICATORS:
        if indicator in q_lower:
            return True

    return False


class QueryDecomposer:
    """Décompose une question complexe en sous-requêtes simples.

    Chaque sous-quête doit pouvoir être répondue par UN document.
    Les sous-requêtes sont ensuite exécutées en parallèle par le
    MultiSearchOrchestrator.
    """

    def __init__(self, cloud_llm: Optional[object] = None):
        self._cloud = cloud_llm

    async def decompose(self, query: str) -> list[str]:
        """Décompose une question si nécessaire.

        Returns:
            list[str] : sous-requêtes (1 seule si pas de décomposition)
        """
        if not should_decompose(query):
            return [query]

        # Essayer Cloud LLM
        if self._cloud:
            try:
                sub_queries = await self._decompose_with_cloud(query)
                if sub_queries and len(sub_queries) > 1:
                    # Appliquer le circuit breaker
                    sub_queries = sub_queries[:MAX_SUB_QUERIES]
                    logger.info(
                        f"🔀 Décomposition : '{query[:60]}' -> {len(sub_queries)} sous-requêtes"
                    )
                    for i, sq in enumerate(sub_queries):
                        logger.info(f"   [{i+1}] {sq[:80]}")
                    return sub_queries
            except Exception as e:
                logger.warning(f"Décomposition cloud échouée: {e}")

        # Fallback : décomposition naïve par connecteurs
        return self._decompose_naive(query)

    async def _decompose_with_cloud(self, query: str) -> list[str]:
        """Décomposition via LLM Cloud — retourne un JSON array de strings."""
        prompt = (
            "Tu es un assistant qui décompose les questions complexes en sous-questions.\n"
            "\n"
            "Règles :\n"
            "- Chaque sous-question doit être SIMPLE et ne concerner qu'UN sujet\n"
            "- Chaque sous-question doit pouvoir être répondue par UN document\n"
            "- Maximum 3 sous-questions\n"
            "- Si la question est déjà simple, retourne UNE SEULE sous-question (l'originale)\n"
            "- Réponds UNIQUEMENT avec un JSON array de strings\n"
            "\n"
            "Exemple 1:\n"
            'Question : "Quels sont les rendements du riz et du maïs à Palabek en 2023?"\n'
            'Réponse : ["rendement riz Palabek 2023", "rendement maïs Palabek 2023"]\n'
            "\n"
            "Exemple 2:\n"
            'Question : "Quelle est la superficie de Palabek?"\n'
            'Réponse : ["Quelle est la superficie de Palabek?"]\n'
            "\n"
            f"Question : {query}\n"
            "\n"
            "Réponse (JSON array uniquement) :"
        )

        try:
            response = self._cloud.generate(prompt, timeout=5.0)
            if not response or not response.strip():
                return [query]

            # Parser le JSON
            cleaned = response.strip()
            # Nettoyer les éventuels marqueurs de code
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s*```$', '', cleaned)

            sub_queries = json.loads(cleaned)

            if not isinstance(sub_queries, list):
                return [query]

            # Nettoyer chaque sous-requête
            sub_queries = [
                sq.strip().strip('"\'„"')
                for sq in sub_queries
                if isinstance(sq, str) and sq.strip()
            ]

            if len(sub_queries) > MAX_SUB_QUERIES:
                sub_queries = sub_queries[:MAX_SUB_QUERIES]

            if len(sub_queries) <= 1:
                return [query]

            return sub_queries

        except (json.JSONDecodeError, Exception) as e:
            logger.debug(f"Décomposition cloud parse error: {e}")
            return [query]

    def _decompose_naive(self, query: str) -> list[str]:
        """Décomposition naïve basée sur les connecteurs (fallback)."""
        import re as _re

        # Diviser sur "et" ou "ou" si la phrase a une structure claire
        # Ex: "compétences en X et expérience en Y" → ["compétences X", "expérience Y"]
        q = query.strip().rstrip("?.")

        # Stratégie simple : diviser par " et " / " ou " si 2 thèmes distincts
        # après un verbe principal
        patterns = [
            _re.compile(r'(?:et|ou)\s+(?:(?:de|du|des|d\'|l\'|la|le|les)\s+)?(\w+)'),
        ]

        # Version simple : couper au premier connecteur
        for conn in sorted(CONNECTORS, key=len, reverse=True):
            if conn in q.lower():
                parts = q.lower().split(conn, 1)
                if len(parts) == 2 and all(len(p.split()) >= 3 for p in parts):
                    logger.info(
                        f"🔀 Décomposition naïve : '{query[:50]}' -> 2 sous-requêtes"
                    )
                    return [parts[0].strip(), parts[1].strip()]

        return [query]
