"""
Long-Term Memory Adapter V10.1 — Connecte MemoryStore au pipeline orchestrator.

Fournit l'interface attendue par NuruOrchestrator :
- get_relevant_facts(query, limit) → list[str]
- extract_facts(history) → list[dict]
- store_fact(fact_type, content) → None
- format_facts_for_prompt(facts) → str
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class LongTermMemory:
    """Adaptateur entre MemoryStore et le pipeline orchestrator."""

    def __init__(self, memory_store):
        self.memory_store = memory_store

    async def get_relevant_facts(self, query: str, limit: int = 10) -> list[str]:
        """Récupère les faits les plus récents (pas de recherche sémantique pour l'instant)."""
        try:
            facts = self.memory_store.get_recent_facts(limit=limit)
            return facts if facts else []
        except Exception as e:
            logger.debug(f"get_relevant_facts error: {e}")
            return []

    async def extract_facts(self, history: list[dict]) -> list[dict]:
        """Extrait des faits depuis l'historique de conversation."""
        try:
            from src.extraction import PostSessionExtractor
            extractor = PostSessionExtractor()
            raw_facts = extractor.extract(history)
            return [{"fact_type": "user_profile", "content": f} for f in raw_facts]
        except Exception as e:
            logger.debug(f"extract_facts error: {e}")
            return []

    def store_fact(self, fact_type: str, content: str):
        """Stocke un fait dans la base."""
        try:
            self.memory_store.add_fact(content, category=fact_type)
        except Exception as e:
            logger.debug(f"store_fact error: {e}")

    def format_facts_for_prompt(self, facts: list) -> str:
        """Formate les faits pour injection dans le prompt système."""
        if not facts:
            return ""
        lines = []
        for f in facts:
            if isinstance(f, str):
                lines.append(f"- {f}")
            elif isinstance(f, dict):
                content = f.get("content", "")
                if content:
                    lines.append(f"- {content}")
        return "\n".join(lines) if lines else ""
