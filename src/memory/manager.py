"""
NURU V9 — MemoryManager : façade intégrant les modules V9 dans le pipeline existant.

Wrapper de l'interface de memory_store (add_message, set_cache, add_reflection)
tout en exposant les nouvelles capacités V9 (episodic, semantic, user, error).
"""

import logging
import time
from typing import Any, Optional

from src.memory.schema import MemorySchema
from src.memory.episodic import EpisodicMemory
from src.memory.semantic import SemanticMemory
from src.memory.user import UserMemory
from src.memory.errors import ErrorMemory
from src.memory.retriever import MemoryRetriever

logger = logging.getLogger(__name__)


class MemoryManager:
    """Façade intégrant les modules V9 dans le pipeline existant."""

    def __init__(self, db_path: Optional[str] = None):
        self.schema = MemorySchema(db_path)
        self.schema.init_db()

        self.episodic = EpisodicMemory(self.schema)
        self.semantic = SemanticMemory(self.schema)
        self.user = UserMemory(self.schema)
        self.error = ErrorMemory(self.schema)
        self.retriever = MemoryRetriever(
            self.schema, episodic=self.episodic, semantic=self.semantic,
            user=self.user, error=self.error,
        )

        self._working: dict[int, dict] = {}
        self._message_history: list[dict[str, str]] = []

        logger.info("MemoryManager V9 initialise (db: %s)", self.schema.db_path)

    # ── Compatibilité memory_store ───────────────────────────────

    def add_message(self, role: str, content: str):
        self._message_history.append({"role": role, "content": content})
        if role == "assistant":
            try:
                self.episodic.add(
                    event_type="conversation", summary=content[:200],
                    context={"role": role}, importance=0.5,
                )
            except Exception as e:
                logger.debug("MemoryManager: echec enregistrement episodique (%s)", e)

    def set_cache(self, query: str, response: str):
        cache_key = hash(query)
        self._working[cache_key] = {
            "query": query, "response": response,
            "ttl": time.time() + 3600,
        }
        try:
            self.episodic.add(
                event_type="cache_set", summary=response[:100],
                context={"query": query}, importance=0.3,
            )
        except Exception as e:
            logger.debug("MemoryManager: echec cache episodique (%s)", e)

    async def async_set_cache(self, query: str, response: str, diagnostic: Optional[dict] = None):
        self.set_cache(query, response)

    def add_reflection(self, query: str, feedback: str, score: float):
        try:
            self.episodic.add(
                event_type="reflection", summary=feedback[:200],
                context={"query": query, "score": score}, importance=score,
            )
        except Exception as e:
            logger.debug("MemoryManager: echec ajout reflexion (%s)", e)

    def get_context(self, window: int = 5) -> str:
        recent = self._message_history[-window:] if window > 0 else self._message_history
        return "\n".join(f"{m['role']}: {m['content']}" for m in recent)

    def clear_history(self):
        self._message_history = []

    async def get_cache(self, query: str) -> tuple[Optional[str], Optional[dict]]:
        cache_key = hash(query)
        entry = self._working.get(cache_key)
        if entry is not None and entry["ttl"] > time.time():
            return entry["response"], None
        if entry is not None:
            del self._working[cache_key]
        return None, None

    # ── Nouvelles capacites V9 ───────────────────────────────────

    def record_conversation(self, query: str, response: str, importance: float = 0.5) -> str:
        return self.episodic.add(
            event_type="conversation", summary=response[:100],
            context={"query": query, "response": response}, importance=importance,
        )

    def add_episode(self, session_id: str, goal: str, status: str,
                    steps: list[dict], importance: float = 0.5) -> str:
        """Enregistre une session agent complète dans EpisodicMemory.

        Args:
            session_id: Identifiant de session
            goal: Objectif original
            status: Statut final ('success', 'error', 'interrupted')
            steps: Résultats des étapes exécutées
            importance: Score d'importance

        Returns:
            ID de l'épisode créé
        """
        summary = f"Agent: {goal[:80]} — {status}"
        step_summaries = [
            f"  {s.get('status', '?')}: {s.get('description', '')[:60]}"
            for s in (steps or [])
        ]
        context = {
            "session_id": session_id,
            "goal": goal,
            "status": status,
            "step_count": len(steps or []),
            "steps": step_summaries,
        }
        return self.episodic.add(
            event_type="agent_session",
            summary=summary,
            context=context,
            importance=importance,
        )

    def record_error(self, error_type: str, description: str,
                     root_cause: str = "", correction: str = "") -> str:
        return self.error.add(
            error_type=error_type, description=description,
            root_cause=root_cause, correction=correction,
        )

    def check_errors(self, query: str) -> list[dict]:
        return self.error.check_similar(query, threshold=0.75)

    def get_user_profile(self) -> str:
        all_user = self.user.get_all()
        if not all_user:
            return ""
        lines = []
        for entry in all_user:
            lines.append(
                f"- {entry['key']}: {entry['value']} "
                f"({entry['category']}, confiance: {entry['confidence']})"
            )
        return "Profil utilisateur :\n" + "\n".join(lines)

    def get_full_context(self, query: str) -> str:
        return self.retriever.get_context_for_query(query)

    def get_recent_history(self, limit: int = 5) -> list[dict]:
        recent = self._message_history[-limit:] if limit > 0 else self._message_history
        return list(recent)

    # ── Statistiques ────────────────────────────────────────────

    def get_memory_stats(self) -> dict[str, Any]:
        return self.retriever.count_all()

    def get_working_memory_size(self) -> int:
        return len(self._working)

    def get_message_history_size(self) -> int:
        return len(self._message_history)
