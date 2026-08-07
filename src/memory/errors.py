"""
NURU V9 — Mémoire des erreurs.

Enregistre les erreurs passées avec leur contexte et leur correction
pour éviter de les répéter.

error_types supportés:
  'hallucination', 'wrong_routing', 'tool_failure',
  'rag_miss', 'timeout', 'low_confidence', 'user_correction'

Inspiré des systèmes de mémoire d'erreurs dans MemGPT/Letta
et des boucles de rétroaction dans MIRIX.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Optional

import numpy as np

from src.memory.schema import MemorySchema
from src.embedder import Embedder

logger = logging.getLogger(__name__)


class ErrorMemory:
    """Mémoire des erreurs : enregistre les erreurs passées avec leur contexte
    et leur correction pour éviter de les répéter.

    Chaque erreur est stockée avec un timestamp, un type, une description,
    une cause racine, une correction, la requête associée, et un embedding
    768d pour la recherche par similarité.
    """

    def __init__(self, schema: MemorySchema):
        self.schema = schema
        self._embedder = None  # Lazy loading

    @property
    def embedder(self):
        if self._embedder is None:
            self._embedder = Embedder()
        return self._embedder

    # ── CRUD ──────────────────────────────────────────────────────────

    def add(
        self,
        error_type: str,
        description: str,
        root_cause: str = "",
        correction: str = "",
        related_query: str = "",
    ) -> str:
        """Enregistre une nouvelle erreur avec embedding du contexte.

        Args:
            error_type: Type d'erreur ('hallucination', 'tool_failure', etc.)
            description: Description détaillée de l'erreur
            root_cause: Cause racine identifiée
            correction: Correction appliquée
            related_query: Requête utilisateur associée

        Returns:
            ID unique de l'erreur
        """
        error_id = str(uuid.uuid4())
        now = time.time()

        # Génération de l'embedding à partir du contexte complet
        embed_text = f"{description} {root_cause} {correction}"
        embedding = self._compute_embedding(embed_text)

        conn = self.schema._get_conn()
        try:
            conn.execute(
                """INSERT INTO error_memory
                   (id, timestamp, error_type, description, root_cause,
                    correction, related_query, embedding, resolved)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    error_id,
                    now,
                    error_type,
                    description,
                    root_cause,
                    correction,
                    related_query,
                    embedding,
                    0,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        logger.debug("Erreur enregistrée : %s — %s (%s)", error_id, error_type, description[:60])
        return error_id

    async def recall(
        self,
        query: str,
        top_k: int = 5,
        error_types: Optional[list[str]] = None,
        only_unresolved: bool = False,
    ) -> list[dict[str, Any]]:
        """Recherche les erreurs similaires à une requête (asynchrone).

        Args:
            query: Texte de recherche
            top_k: Nombre max de résultats
            error_types: Filtre par type d'erreur (None = tous)
            only_unresolved: Si True, ne retourne que les erreurs non résolues

        Returns:
            Liste de dicts
        """
        query_emb = await asyncio.to_thread(self._embed_query, query)
        conn = self.schema._get_conn()
        try:
            sql = "SELECT id, timestamp, error_type, description, root_cause, correction, related_query, resolved, embedding FROM error_memory"
            params = []
            conditions = []

            if error_types:
                placeholders = ",".join("?" for _ in error_types)
                conditions.append(f"error_type IN ({placeholders})")
                params.extend(error_types)

            if only_unresolved:
                conditions.append("resolved = 0")

            if conditions:
                sql += " WHERE " + " AND ".join(conditions)

            sql += " ORDER BY timestamp DESC LIMIT ?"
            params.append(top_k * 5)  # Get more candidates for ranking

            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        if not rows:
            return []

        # Re-ranking par similarité cosinus
        scored = []
        for row in rows:
            if row["embedding"] is None:
                continue
            emb = self._deserialize_embedding(row["embedding"])
            score = self._cosine_similarity(query_emb, emb)
            scored.append({
                "id": row["id"],
                "timestamp": row["timestamp"],
                "error_type": row["error_type"],
                "description": row["description"],
                "root_cause": row["root_cause"] or "",
                "correction": row["correction"] or "",
                "related_query": row["related_query"] or "",
                "resolved": bool(row["resolved"]),
                "score": round(float(score), 4),
            })

        # Tri par score décroissant
        scored.sort(key=lambda x: x["score"], reverse=True)

        return scored[:top_k]

    def check_similar(self, query: str, threshold: float = 0.75) -> list[dict]:
        """Vérifie si une erreur similaire existe déjà.

        Recherche les erreurs avec un score de similarité > threshold.
        Utile avant une action risquée pour éviter de répéter une erreur.

        Args:
            query: Texte de la requête ou description de l'action à vérifier
            threshold: Seuil de similarité cosinus (défaut: 0.75)

        Returns:
            Liste des erreurs similaires (triées par score décroissant)
        """
        query_emb = self._embed_query(query)
        conn = self.schema._get_conn()
        try:
            rows = conn.execute(
                "SELECT id, timestamp, error_type, description, root_cause, correction, related_query, resolved, embedding FROM error_memory"
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            return []

        scored = []
        for row in rows:
            if row["embedding"] is None:
                continue
            emb = self._deserialize_embedding(row["embedding"])
            score = self._cosine_similarity(query_emb, emb)
            if score > threshold:
                scored.append({
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "error_type": row["error_type"],
                    "description": row["description"],
                    "root_cause": row["root_cause"] or "",
                    "correction": row["correction"] or "",
                    "related_query": row["related_query"] or "",
                    "resolved": bool(row["resolved"]),
                    "score": round(float(score), 4),
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored

    def mark_resolved(self, error_id: str) -> bool:
        """Marque une erreur comme résolue.

        Args:
            error_id: ID de l'erreur à marquer

        Returns:
            True si l'erreur a été trouvée et mise à jour, False sinon
        """
        conn = self.schema._get_conn()
        try:
            cursor = conn.execute(
                "UPDATE error_memory SET resolved = 1 WHERE id = ?",
                (error_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_stats(self) -> dict[str, Any]:
        """Statistiques détaillées sur les erreurs.

        Returns:
            dict avec :
            - total: nombre total d'erreurs
            - resolved: nombre d'erreurs résolues
            - unresolved: nombre d'erreurs non résolues
            - by_type: dict {error_type: count}
            - unresolved_by_type: dict {error_type: count} (non résolues)
            - top_types: liste des types les plus fréquents
        """
        conn = self.schema._get_conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM error_memory").fetchone()[0]
            resolved = conn.execute("SELECT COUNT(*) FROM error_memory WHERE resolved = 1").fetchone()[0]
            unresolved = total - resolved

            # Répartition par type
            by_type_rows = conn.execute(
                "SELECT error_type, COUNT(*) as cnt FROM error_memory GROUP BY error_type ORDER BY cnt DESC"
            ).fetchall()
            by_type = {row["error_type"]: row["cnt"] for row in by_type_rows}

            # Répartition par type (non résolues seulement)
            unresolved_by_type_rows = conn.execute(
                "SELECT error_type, COUNT(*) as cnt FROM error_memory WHERE resolved = 0 GROUP BY error_type ORDER BY cnt DESC"
            ).fetchall()
            unresolved_by_type = {row["error_type"]: row["cnt"] for row in unresolved_by_type_rows}

            top_types = [row["error_type"] for row in by_type_rows]

        finally:
            conn.close()

        return {
            "total": total,
            "resolved": resolved,
            "unresolved": unresolved,
            "by_type": by_type,
            "unresolved_by_type": unresolved_by_type,
            "top_types": top_types,
        }

    def get_by_id(self, error_id: str) -> Optional[dict[str, Any]]:
        """Récupère une erreur par son ID."""
        conn = self.schema._get_conn()
        try:
            row = conn.execute(
                "SELECT id, timestamp, error_type, description, root_cause, correction, related_query, resolved FROM error_memory WHERE id=?",
                (error_id,),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            return None
        return {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "error_type": row["error_type"],
            "description": row["description"],
            "root_cause": row["root_cause"] or "",
            "correction": row["correction"] or "",
            "related_query": row["related_query"] or "",
            "resolved": bool(row["resolved"]),
        }

    def delete(self, error_id: str) -> bool:
        """Supprime une erreur par son ID."""
        conn = self.schema._get_conn()
        try:
            cursor = conn.execute("DELETE FROM error_memory WHERE id=?", (error_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def count(self) -> int:
        """Retourne le nombre total d'erreurs enregistrées."""
        conn = self.schema._get_conn()
        try:
            row = conn.execute("SELECT COUNT(*) FROM error_memory").fetchone()
            return row[0]
        finally:
            conn.close()

    def list_unresolved(self) -> list[dict[str, Any]]:
        """Liste toutes les erreurs non résolues."""
        conn = self.schema._get_conn()
        try:
            rows = conn.execute(
                "SELECT id, timestamp, error_type, description, root_cause, correction, related_query, resolved FROM error_memory WHERE resolved = 0 ORDER BY timestamp DESC"
            ).fetchall()
        finally:
            conn.close()

        return [
            {
                "id": row["id"],
                "timestamp": row["timestamp"],
                "error_type": row["error_type"],
                "description": row["description"],
                "root_cause": row["root_cause"] or "",
                "correction": row["correction"] or "",
                "related_query": row["related_query"] or "",
                "resolved": bool(row["resolved"]),
            }
            for row in rows
        ]

    # ── Embedding ─────────────────────────────────────────────────────

    def _compute_embedding(self, text: str) -> bytes:
        """Génère un embedding et le sérialise en bytes pour stockage SQLite."""
        emb = self._embed_sync(text)
        return emb.astype(np.float32).tobytes()

    def _embed_query(self, text: str) -> np.ndarray:
        """Génère un embedding en tant que numpy array (pour similarité)."""
        emb = self._embed_sync(text)
        return emb.astype(np.float32).reshape(-1)

    def _embed_sync(self, text: str) -> np.ndarray:
        """Version synchrone du calcul d'embedding (utilitaire partage)."""
        from src.memory._embed_utils import embed_sync
        return embed_sync(text, self.embedder)

    @staticmethod
    def _deserialize_embedding(blob) -> np.ndarray:
        """Désérialise un embedding depuis SQLite en numpy array."""
        if isinstance(blob, memoryview):
            blob = bytes(blob)
        elif not isinstance(blob, (bytes, bytearray)):
            blob = bytes(blob)  # np.bytes_ → bytes
        return np.frombuffer(blob, dtype=np.float32)

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Similarité cosinus entre deux vecteurs."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))
