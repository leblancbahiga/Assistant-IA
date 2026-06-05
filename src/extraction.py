"""Extraction post-session — profil utilisateur et faits durables.

Analyse l'historique de conversation après chaque session pour extraire :
- Centres d'intérêt récurrents
- Préférences de style
- Faits durables sur l'utilisateur

Ces informations sont stockées dans MemoryStore (table facts)
et réinjectées dans le prompt système.
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Mots-clés qui signalent une préférence ou un fait sur l'utilisateur
PREFERENCE_PATTERNS = [
    (r"j'[aà]ime\s+(\w+)", "preference"),
    (r"je\s+(préfère|prefere)\s+(\w+)", "preference"),
    (r"mon\s+(\w+)\s+(est|préféré|prefere)", "preference"),
    (r"je\s+travaille\s+(sur|dans|chez)\s+(\w+)", "work"),
    (r"je\s+suis\s+(\w+)", "identity"),
    (r"j'utilise\s+(\w+)", "tool"),
    (r"mon\s+projet\s+(\w+)", "project"),
]


class PostSessionExtractor:
    """Analyse l'historique de conversation et extrait des faits durables.

    Usage:
        extractor = PostSessionExtractor()
        facts = extractor.extract(history)
        for fact in facts:
            memory_store.add_fact(fact, category='user_profile')
    """

    def extract(self, history: list[dict]) -> list[str]:
        """Analyse l'historique et retourne une liste de faits extraits.

        Args:
            history: Liste de dicts [{'role': 'user', 'content': '...'}, ...]

        Returns:
            Liste de chaînes de fait (ex: "L'utilisateur travaille sur YARID")
        """
        if not history:
            return []

        # Concaténer tous les messages utilisateur
        user_texts = []
        assistant_responses = []
        for msg in history:
            if isinstance(msg, dict):
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    user_texts.append(content)
                elif role == "assistant":
                    assistant_responses.append(content)

        full_user_text = " ".join(user_texts)
        facts = self._extract_preferences(full_user_text)

        # Extraire les entités nommées simples (mots en majuscules répétés)
        entities = self._extract_entities(full_user_text)
        for entity, context in entities[:3]:
            fact = f"L'utilisateur s'intéresse à {entity}"
            if fact not in facts:
                facts.append(fact)

        if facts:
            logger.info(f"📋 Session: {len(facts)} faits extraits")
        return facts

    def _extract_preferences(self, text: str) -> list[str]:
        """Extrait les préférences via patterns regex."""
        facts = []
        for pattern, category in PREFERENCE_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    term = match[-1]
                else:
                    term = match
                if len(term) > 2 and term.lower() not in {"que", "pas", "est", "sur", "dans"}:
                    fact = f"L'utilisateur s'intéresse à {term}"
                    if fact not in facts:
                        facts.append(fact)
        return facts

    def _extract_entities(self, text: str) -> list[tuple[str, str]]:
        """Extraction simple d'entités : mots en majuscules fréquents."""
        words = re.findall(r'\b[A-Z][a-zéèêëàâîïôûù]{2,}\b', text)
        from collections import Counter
        freq = Counter(words)
        # Filtrer les mots trop communs
        stop_entities = {"Bonjour", "Salut", "Merci", "Oui", "Non", "Ok", "Voici"}
        entities = [(word, "entity") for word, count in freq.most_common(10)
                    if count >= 2 and word not in stop_entities]
        return entities
