"""
NURU V15 Phase 3 — MemoryManager 6 couches unifié (Item 28).

Façade centrale intégrant les 6 couches mémoire :
1. WorkingMemory   — Contexte de session en RAM (Item 29)
2. EpisodicMemory  — Événements vécus avec contexte temporel
3. SemanticMemory  — Faits consolidés avec confidence score
4. UserMemory      — Profil utilisateur (key-value)
5. ProceduralMemory — Workflows et procédures réutilisables (Item 30)
6. ErrorMemory     — Erreurs passées et corrections

Remplace les anciens modules mémoire éparpillés :
- memory_bridge.py     → DEPRECATED (redirigé ici)
- long_term_memory.py  → DEPRECATED (redirigé ici)
- memory_store.py      → legacy V5 (conservé pour compatibilité, migration P2 #68)

Intègre le SleepCycleManager (Item 31) : les phases de sommeil déclenchent
automatiquement la consolidation (LIGHT → Working→Episodic, DEEP → full).
"""

import logging
import time
from typing import Any, Optional

from src.memory.schema import MemorySchema
from src.memory.episodic import EpisodicMemory
from src.memory.semantic import SemanticMemory
from src.memory.user import UserMemory
from src.memory.errors import ErrorMemory
from src.memory.working import WorkingMemory
from src.memory.procedural import ProceduralMemory
from src.memory.retriever import MemoryRetriever
from src.memory.sleep_cycle import SleepCycleManager, SleepPhase
from src.memory.consolidation import ConsolidationWorker

logger = logging.getLogger(__name__)


class MemoryManager:
    """Façade unifiée des 6 couches mémoire V15 + SleepCycle.

    Couches :
    1. working    — Contexte de session en RAM (TTL)
    2. episodic   — Événements conversation/actions
    3. semantic   — Faits consolidés
    4. user       — Profil utilisateur
    5. procedural — Procédures réutilisables
    6. error      — Erreurs passées

    SleepCycleManager déclenche consolidation automatique :
    - LIGHT : WorkingMemory → EpisodicMemory (résumé)
    - DEEP  : ConsolidationWorker.run_once() (full)
    - REM   : (réservé synthèse future)
    """

    def __init__(self, db_path: Optional[str] = None):
        self.schema = MemorySchema(db_path)
        self.schema.init_db()

        # V15 P3 : 6 couches mémoire
        self.working = WorkingMemory()
        self.episodic = EpisodicMemory(self.schema)
        self.semantic = SemanticMemory(self.schema)
        self.user = UserMemory(self.schema)
        self.procedural = ProceduralMemory(self.schema)
        self.error = ErrorMemory(self.schema)

        self.retriever = MemoryRetriever(
            self.schema,
            episodic=self.episodic,
            semantic=self.semantic,
            user=self.user,
            error=self.error,
        )

        # V15 P3 #31 : SleepCycle + Consolidation
        self.sleep_cycle = SleepCycleManager()
        self.consolidation = ConsolidationWorker(
            self.schema, self.episodic, self.semantic, self.error,
        )
        self._last_consolidation: float = 0.0
        self._consolidation_cooldown_s: float = 3600.0  # 1h min entre cycles

        self._message_history: list[dict[str, str]] = []

        logger.info(
            "🧠 MemoryManager V15 initialisé (db: %s) — 6 couches + SleepCycle actifs",
            self.schema.db_path,
        )

    # ── Interface compatible memory_store ─────────────────────────────

    def add_message(self, role: str, content: str):
        """Ajoute un message à l'historique et déclenche la consolidation
        épisodique pour les réponses assistant."""
        self._message_history.append({"role": role, "content": content})
        if role == "assistant":
            try:
                self.episodic.add(
                    event_type="conversation",
                    summary=content[:200],
                )
            except Exception as e:
                logger.debug("episodic.add error: %s", e)

    def get_message_history(self, limit: int = 50) -> list[dict[str, str]]:
        """Retourne les derniers messages."""
        return self._message_history[-limit:]

    def clear_history(self):
        """Vide l'historique en RAM."""
        self._message_history.clear()
        self.working.clear()

    # ── SleepCycle & Consolidation (Item 31) ──────────────────────────

    def user_activity_detected(self):
        """Délègue au SleepCycleManager : réveil immédiat."""
        self.sleep_cycle.user_activity_detected()

    async def sleep_cycle_tick(self) -> Optional[str]:
        """Tick du cycle de sommeil → déclenche consolidation si nécessaire.

        Appelé périodiquement (ex: toutes les 30s par le sleep_monitor).

        Returns:
            Message de rapport si consolidation exécutée, None sinon.
        """
        phase = self.sleep_cycle.tick()

        if phase == SleepPhase.AWAKE:
            return None

        now = time.time()
        if now - self._last_consolidation < self._consolidation_cooldown_s:
            return None

        self._last_consolidation = now

        if phase == SleepPhase.LIGHT:
            return await self._light_sleep_consolidation()
        elif phase == SleepPhase.DEEP:
            return await self._deep_sleep_consolidation()

        return None

    async def _light_sleep_consolidation(self) -> str:
        """Consolidation légère : WorkingMemory → EpisodicMemory."""
        entries = self.working.all()
        count = len(entries)
        if count == 0:
            return "🌙 Sommeil léger : rien à consolider"

        # Résumer le contenu du working memory en un épisode
        keys = list(entries.keys())
        summary = f"Session context: {', '.join(keys[:10])}" + (
            f" +{len(keys)-10} autres" if len(keys) > 10 else ""
        )
        self.episodic.add(
            event_type="consolidation_light",
            summary=summary,
            context={"working_keys": keys, "working_count": count},
        )
        self.working.clear()

        logger.info("🌙 SleepCycle: consolidation légère (%d entrées Working→Episodic)", count)
        return f"🌙 Consolidation légère : {count} entrées Working → Episodic"

    async def _deep_sleep_consolidation(self) -> str:
        """Consolidation complète : ConsolidationWorker."""
        logger.info("🌙 SleepCycle: consolidation profonde...")
        try:
            report = await self.consolidation.run_once()
            parts = []
            for k, v in report.items():
                if k != "duration_s" and v:
                    parts.append(f"{k}={v}")
            parts.append(f"durée={report.get('duration_s', 0):.1f}s")
            msg = f"🌙 Consolidation profonde : {', '.join(parts)}"
            logger.info(msg)
            return msg
        except Exception as e:
            logger.warning("⚠️ SleepCycle: consolidation profonde échouée: %s", e)
            return f"⚠️ Consolidation profonde échouée: {e}"

    # ── Helpers utilitaire ────────────────────────────────────────────

    def store_user_fact(self, key: str, value: str, category: str = "general"):
        """Stocke un fait utilisateur (couche 4)."""
        self.user.set(key, value, category=category)

    def get_user_facts(self, limit: int = 20) -> list[dict]:
        """Récupère les faits utilisateur (couche 4)."""
        return self.user.get_all()[:limit]

    def store_episode(self, event_type: str, summary: str, **context):
        """Stocke un épisode (couche 2)."""
        self.episodic.add(event_type=event_type, summary=summary, context=context or None)

    # ── Statistiques ──────────────────────────────────────────────────

    def stats(self) -> dict[str, int]:
        """Retourne les effectifs de chaque couche mémoire."""
        conn = self.schema._get_conn()
        try:
            episodic = conn.execute("SELECT COUNT(*) FROM episodic_memory").fetchone()[0]
            semantic = conn.execute("SELECT COUNT(*) FROM semantic_memory").fetchone()[0]
            user = conn.execute("SELECT COUNT(*) FROM user_memory").fetchone()[0]
            procedural = conn.execute("SELECT COUNT(*) FROM procedural_memory").fetchone()[0]
            error = conn.execute("SELECT COUNT(*) FROM error_memory").fetchone()[0]
            return {
                "working": self.working.count(),
                "episodic": episodic,
                "semantic": semantic,
                "user": user,
                "procedural": procedural,
                "error": error,
            }
        finally:
            conn.close()
