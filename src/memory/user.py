"""
NURU V9 — Mémoire utilisateur.

Stocke les préférences, habitudes, contexte personnel sous forme
de paires clé-valeur avec catégorisation et niveau de confiance.

Catégories : 'preference', 'habit', 'context', 'identity', 'skill'

Exemples:
- key="language", value="fr", category="preference"
- key="name", value="Leblanc", category="identity"
- key="employer", value="YARID", category="context"
"""

import logging
import time
from typing import Any, Optional

from src.memory.schema import MemorySchema

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"preference", "habit", "context", "identity", "skill", "general"}


class UserMemory:
    """
    Mémoire utilisateur : préférences, habitudes, contexte personnel.
    Stockage key-value avec catégorisation et niveau de confiance.

    Catégories : 'preference', 'habit', 'context', 'identity', 'skill'
    """

    def __init__(self, schema: MemorySchema):
        self.schema = schema

    # ── CRUD ──────────────────────────────────────────────────────────

    def set(
        self,
        key: str,
        value: str,
        category: str = "general",
        confidence: float = 0.8,
        source: str = "conversation",
    ) -> None:
        """Définit une information utilisateur (INSERT OR REPLACE).

        Met à jour updated_at automatiquement avec time.time().

        Args:
            key: Clé unique de l'information.
            value: Valeur associée.
            category: Catégorie (preference, habit, context, identity, skill, general).
            confidence: Niveau de confiance (0–1).
            source: Source de l'information.
        """
        now = time.time()
        conn = self.schema._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO user_memory
                   (key, value, category, confidence, updated_at, source)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (key, value, category, confidence, now, source),
            )
            conn.commit()
        finally:
            conn.close()
        logger.debug("UserMemory set : %s = %s… [%s]", key, value[:8], category)

    def get(self, key: str) -> Optional[str]:
        """Récupère la valeur d'une clé.

        Args:
            key: Clé à rechercher.

        Returns:
            La valeur si trouvée, None sinon.
        """
        conn = self.schema._get_conn()
        try:
            row = conn.execute(
                "SELECT value FROM user_memory WHERE key = ?",
                (key,),
            ).fetchone()
        finally:
            conn.close()

        return row["value"] if row else None

    def get_full(self, key: str) -> Optional[dict[str, Any]]:
        """Récupère toutes les informations d'une clé.

        Args:
            key: Clé à rechercher.

        Returns:
            Dict avec key, value, category, confidence, updated_at, source,
            ou None si la clé n'existe pas.
        """
        conn = self.schema._get_conn()
        try:
            row = conn.execute(
                "SELECT key, value, category, confidence, updated_at, source "
                "FROM user_memory WHERE key = ?",
                (key,),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            return None
        return dict(row)

    def delete(self, key: str) -> bool:
        """Supprime une clé de la mémoire utilisateur.

        Args:
            key: Clé à supprimer.

        Returns:
            True si une ligne a été supprimée, False sinon.
        """
        conn = self.schema._get_conn()
        try:
            cursor = conn.execute("DELETE FROM user_memory WHERE key = ?", (key,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ── Recherche et filtrage ─────────────────────────────────────────

    def list_by_category(self, category: str) -> list[dict[str, Any]]:
        """Liste toutes les entrées d'une catégorie.

        Args:
            category: Catégorie à filtrer.

        Returns:
            Liste de dicts (key, value, category, confidence, updated_at, source).
        """
        conn = self.schema._get_conn()
        try:
            rows = conn.execute(
                "SELECT key, value, category, confidence, updated_at, source "
                "FROM user_memory WHERE category = ? ORDER BY updated_at DESC",
                (category,),
            ).fetchall()
        finally:
            conn.close()

        return [dict(r) for r in rows]

    def search(self, query: str) -> list[dict[str, Any]]:
        """Recherche textuelle dans les clés et valeurs (LIKE %query%).

        Args:
            query: Terme de recherche (insensible à la casse).

        Returns:
            Liste de dicts (key, value, category, confidence, updated_at, source).
        """
        pattern = f"%{query}%"
        conn = self.schema._get_conn()
        try:
            rows = conn.execute(
                "SELECT key, value, category, confidence, updated_at, source "
                "FROM user_memory WHERE key LIKE ? OR value LIKE ? "
                "ORDER BY updated_at DESC",
                (pattern, pattern),
            ).fetchall()
        finally:
            conn.close()

        return [dict(r) for r in rows]

    # ── Mise à jour spécifique ────────────────────────────────────────

    def update_confidence(self, key: str, confidence: float) -> bool:
        """Met à jour le niveau de confiance d'une entrée.

        Met également à jour updated_at automatiquement.

        Args:
            key: Clé à mettre à jour.
            confidence: Nouveau niveau de confiance (0–1).

        Returns:
            True si la clé existe et a été mise à jour, False sinon.
        """
        now = time.time()
        conn = self.schema._get_conn()
        try:
            cursor = conn.execute(
                "UPDATE user_memory SET confidence = ?, updated_at = ? WHERE key = ?",
                (confidence, now, key),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_all(self) -> list[dict[str, Any]]:
        """Retourne toutes les entrées de la mémoire utilisateur.

        Returns:
            Liste de tous les dicts (key, value, category, confidence, updated_at, source).
        """
        conn = self.schema._get_conn()
        try:
            rows = conn.execute(
                "SELECT key, value, category, confidence, updated_at, source "
                "FROM user_memory ORDER BY updated_at DESC"
            ).fetchall()
        finally:
            conn.close()

        return [dict(r) for r in rows]

    # ── Statistiques ──────────────────────────────────────────────────

    def count(self) -> int:
        """Retourne le nombre total d'entrées."""
        conn = self.schema._get_conn()
        try:
            row = conn.execute("SELECT COUNT(*) FROM user_memory").fetchone()
            return row[0]
        finally:
            conn.close()

    def count_by_category(self) -> dict[str, int]:
        """Retourne le nombre d'entrées par catégorie.

        Returns:
            Dict {category: count}.
        """
        conn = self.schema._get_conn()
        try:
            rows = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM user_memory GROUP BY category"
            ).fetchall()
        finally:
            conn.close()

        return {r["category"]: r["cnt"] for r in rows}

    # ── Opérations en masse ───────────────────────────────────────────

    def bulk_set(self, entries: list[dict]) -> int:
        """Définit plusieurs entrées en une seule transaction.

        Chaque entrée est un dict avec les clés :
        key (obligatoire), value (obligatoire), category, confidence, source.

        Args:
            entries: Liste de dicts représentant les entrées à insérer/replacer.

        Returns:
            Nombre d'entrées traitées.
        """
        now = time.time()
        conn = self.schema._get_conn()
        try:
            for entry in entries:
                conn.execute(
                    """INSERT OR REPLACE INTO user_memory
                       (key, value, category, confidence, updated_at, source)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        entry["key"],
                        entry["value"],
                        entry.get("category", "general"),
                        entry.get("confidence", 0.8),
                        now,
                        entry.get("source", "conversation"),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

        logger.debug("UserMemory bulk_set : %d entrées traitées", len(entries))
        return len(entries)
