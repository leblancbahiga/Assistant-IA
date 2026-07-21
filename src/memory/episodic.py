"""
NURU V9 — Mémoire épisodique.

Stocke les événements vécus (conversations, actions, résultats)
avec timestamp, contexte, et embedding sémantique pour recherche
par similarité.

Inspiré de MemGPT/Letta (episodic memory) et MIRIX.
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


class EpisodicMemory:
    """Stockage des événements vécus avec recherche sémantique.

    Chaque épisode est un événement avec un résumé, un contexte JSON,
    un score d'importance, et un embedding 768d pour la recherche.
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
        event_type: str,
        summary: str,
        context: Optional[dict] = None,
        importance: float = 0.5,
    ) -> str:
        """Ajoute un épisode à la mémoire.

        Args:
            event_type: Type d'événement ('conversation', 'action', 'tool_use', etc.)
            summary: Résumé lisible de l'épisode
            context: Contexte détaillé (dict JSON-serializable)
            importance: Score d'importance (0–1)

        Returns:
            ID unique de l'épisode
        """
        episode_id = str(uuid.uuid4())
        now = time.time()

        # Génération de l'embedding à partir du résumé
        embedding = self._compute_embedding(summary)

        conn = self.schema._get_conn()
        try:
            conn.execute(
                """INSERT INTO episodic_memory
                   (id, timestamp, event_type, summary, context, embedding, importance)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    episode_id,
                    now,
                    event_type,
                    summary,
                    json.dumps(context or {}, ensure_ascii=False),
                    embedding,
                    importance,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        logger.debug("Épisode ajouté : %s — %s", episode_id, summary[:60])
        return episode_id

    async def recall(
        self,
        query: str,
        top_k: int = 5,
        min_importance: float = 0.0,
        event_types: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Recherche les épisodes les plus similaires à une requête (asynchrone).

        Args:
            query: Texte de recherche
            top_k: Nombre max de résultats
            min_importance: Filtre d'importance minimale
            event_types: Filtre par type d'événement (None = tous)

        Returns:
            Liste de dicts : {id, timestamp, event_type, summary, context, importance, score}
        """
        # L'embedding est CPU-bound (MLX) → exécuté dans un thread pour ne pas
        # bloquer l'event loop. V17 Phase 2.
        query_emb = await asyncio.to_thread(self._embed_query, query)
        conn = self.schema._get_conn()
        try:
            # Récupère les candidats (avec embedding) pour similarité cosinus
            sql = "SELECT id, timestamp, event_type, summary, context, importance, embedding FROM episodic_memory"
            params = []
            conditions = []

            if min_importance > 0.0:
                conditions.append("importance >= ?")
                params.append(min_importance)

            if event_types:
                placeholders = ",".join("?" for _ in event_types)
                conditions.append(f"event_type IN ({placeholders})")
                params.extend(event_types)

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
                "event_type": row["event_type"],
                "summary": row["summary"],
                "context": json.loads(row["context"]) if row["context"] else {},
                "importance": row["importance"],
                "score": round(float(score), 4),
            })

        # Tri par score décroissant
        scored.sort(key=lambda x: x["score"], reverse=True)

        # Mise à jour access_count et last_accessed
        self._update_access_stats([s["id"] for s in scored[:top_k]])

        return scored[:top_k]

    def get_by_id(self, episode_id: str) -> Optional[dict[str, Any]]:
        """Récupère un épisode par son ID."""
        conn = self.schema._get_conn()
        try:
            row = conn.execute(
                "SELECT id, timestamp, event_type, summary, context, importance FROM episodic_memory WHERE id=?",
                (episode_id,),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            return None
        return {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "event_type": row["event_type"],
            "summary": row["summary"],
            "context": json.loads(row["context"]) if row["context"] else {},
            "importance": row["importance"],
        }

    def delete(self, episode_id: str) -> bool:
        """Supprime un épisode par son ID."""
        conn = self.schema._get_conn()
        try:
            cursor = conn.execute("DELETE FROM episodic_memory WHERE id=?", (episode_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def count(self) -> int:
        """Retourne le nombre total d'épisodes."""
        conn = self.schema._get_conn()
        try:
            row = conn.execute("SELECT COUNT(*) FROM episodic_memory").fetchone()
            return row[0]
        finally:
            conn.close()

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
        """Version synchrone du calcul d'embedding (appel direct, pas d'asyncio.run)."""
        return self.embedder.embed_sync(text, is_query=False)

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

    def _update_access_stats(self, ids: list[str]):
        """Met à jour access_count et last_accessed pour les IDs donnés."""
        if not ids:
            return
        conn = self.schema._get_conn()
        try:
            now = time.time()
            for eid in ids:
                conn.execute(
                    "UPDATE episodic_memory SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                    (now, eid),
                )
            conn.commit()
        finally:
            conn.close()
