"""
MemoryBridge V10.1 — Connecte la mémoire V9 (MemoryManager) au pipeline NURU.

Utilise la mémoire V9 comme source primaire pour les faits utilisateur,
avec fallback sur la mémoire V5 (MemoryStore).
"""
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class MemoryBridge:
    """Pont entre mémoire V9 et le pipeline orchestrator."""

    def __init__(self, v5_memory_store=None, v9_db_path: str = None):
        self.v5 = v5_memory_store
        self.v9 = None
        
        # Initialiser V9 si le chemin est fourni
        if v9_db_path:
            try:
                from src.memory.manager import MemoryManager
                self.v9 = MemoryManager(db_path=v9_db_path)
                logger.info("🧠 MemoryBridge: V9 MemoryManager initialisé")
            except Exception as e:
                logger.warning(f"MemoryBridge: V9 non disponible: {e}")
        
        # Vérifier que V5 est fourni
        if not self.v5:
            logger.warning("MemoryBridge: V5 MemoryStore non fourni")

    # ── Interface unifiée ────────────────────────────────────────────────

    def get_user_facts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Récupère les faits utilisateur depuis V9 (priorité) ou V5."""
        facts = []
        
        # V9 en priorité
        if self.v9:
            try:
                v9_facts = self.v9.user.get_all()
                for f in v9_facts[:limit]:
                    facts.append({
                        "key": f.get("key", ""),
                        "value": f.get("value", ""),
                        "category": f.get("category", "general"),
                    })
            except Exception as e:
                logger.debug(f"V9 get_user_facts error: {e}")
        
        # Fallback V5 si V9 vide ou indisponible
        if not facts and self.v5:
            try:
                v5_facts = self.v5.get_recent_facts(limit=limit)
                for f in v5_facts:
                    facts.append({"key": "fact", "value": f, "category": "general"})
            except Exception as e:
                logger.debug(f"V5 get_recent_facts error: {e}")
        
        return facts

    def add_fact(self, key: str, value: str, category: str = "user_profile"):
        """Ajoute un fait aux deux mémoires."""
        # V9
        if self.v9:
            try:
                self.v9.user.set(key, value, category=category)
            except Exception as e:
                logger.debug(f"V9 add_fact error: {e}")
        
        # V5 (compatible)
        if self.v5:
            try:
                self.v5.add_fact(f"{key}: {value}", category=category)
            except Exception as e:
                logger.debug(f"V5 add_fact error: {e}")

    def get_procedures(self) -> str:
        """Récupère les procédures (V5 pour l'instant)."""
        if self.v5:
            try:
                return self.v5.get_procedures()
            except Exception:
                pass
        return ""

    def format_for_prompt(self, facts: List[Dict[str, Any]]) -> str:
        """Formate les faits pour injection dans le prompt."""
        if not facts:
            return ""
        lines = []
        for f in facts:
            value = f.get("value", "")
            if value:
                lines.append(f"- {value}")
        return "\n".join(lines) if lines else ""
