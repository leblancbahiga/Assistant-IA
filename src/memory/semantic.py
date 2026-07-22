"""
NURU V9 — Mémoire sémantique.

Stocke des faits consolidés avec confidence score, extraits des
épisodes et autres sources. Chaque fait est un morceau de connaissance
stable (ex: "Leblanc travaille pour YARID") associé à une catégorie,
un score de confiance, et les IDs des épisodes sources.

Inspiré de MemGPT/Letta (core memory) et MIRIX.
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


class SemanticMemory:
    """Stockage de faits consolidés avec recherche sémantique.

    Chaque fait est stocké avec :
    - fact         : le fait lui-même (ex: "Leblanc travaille pour YARID")
    - category     : 'personal', 'professional', 'technical', 'general'
    - confidence   : 0–1 (combien on est sûr de ce fait)
    - source_episodes : IDs des épisodes qui ont généré ce fait
    - embedding    : pour recherche par similarité
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
        fact: str,
        category: str = "general",
        confidence: float = 0.8,
        source_episodes: Optional[list[str]] = None,
    ) -> str:
        """Ajoute un fait à la mémoire sémantique.

        Args:
            fact: Le fait à stocker (ex: "Leblanc travaille pour YARID")
            category: Catégorie ('personal', 'professional', 'technical', 'general')
            confidence: Score de confiance (0–1)
            source_episodes: IDs des épisodes sources

        Returns:
            ID unique du fait
        """
        fact_id = str(uuid.uuid4())
        now = time.time()

        # Génération de l'embedding à partir du fait
        embedding = self._compute_embedding(fact)

        conn = self.schema._get_conn()
        try:
            conn.execute(
                """INSERT INTO semantic_memory
                   (id, fact, category, confidence, source_episodes, embedding, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    fact_id,
                    fact,
                    category,
                    confidence,
                    json.dumps(source_episodes or [], ensure_ascii=False),
                    embedding,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        logger.debug("Fait ajouté : %s — %s", fact_id, fact[:60])
        return fact_id

    async def recall(
        self,
        query: str,
        top_k: int = 5,
        min_confidence: float = 0.0,
        categories: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Recherche les faits les plus pertinents par similarité sémantique (asynchrone).

        Args:
            query: Texte de recherche
            top_k: Nombre max de résultats
            min_confidence: Filtre de confiance minimale
            categories: Filtre par catégories (None = toutes)

        Returns:
            Liste de dicts : {id, fact, category, confidence, source_episodes,
                             created_at, updated_at, score}
        """
        # L'embedding est CPU-bound (MLX) → exécuté dans un thread pour ne pas
        # bloquer l'event loop. V17 Phase 2.
        query_emb = await asyncio.to_thread(self._embed_query, query)
        conn = self.schema._get_conn()
        try:
            sql = "SELECT id, fact, category, confidence, source_episodes, created_at, updated_at, embedding FROM semantic_memory"
            params = []
            conditions = []

            if min_confidence > 0.0:
                conditions.append("confidence >= ?")
                params.append(min_confidence)

            if categories:
                placeholders = ",".join("?" for _ in categories)
                conditions.append(f"category IN ({placeholders})")
                params.extend(categories)

            if conditions:
                sql += " WHERE " + " AND ".join(conditions)

            sql += " ORDER BY created_at DESC LIMIT ?"
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
                "fact": row["fact"],
                "category": row["category"],
                "confidence": row["confidence"],
                "source_episodes": json.loads(row["source_episodes"]) if row["source_episodes"] else [],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "score": round(float(score), 4),
            })

        # Tri par score décroissant
        scored.sort(key=lambda x: x["score"], reverse=True)

        # Mise à jour access_count
        self._update_access_stats([s["id"] for s in scored[:top_k]])

        return scored[:top_k]

    def consolidate(self, facts: list[dict]) -> Optional[str]:
        """Consolide des faits redondants (similarité cosinus > 0.90).

        Compare chaque fait de la liste avec les faits existants.
        Si un fait existant a une similarité cosinus > 0.90, fusion :
        - Prend le max confidence
        - Merge les source_episodes (union dédupliquée)
        - Supprime l'ancien, ajoute le nouveau

        Returns:
            ID du nouveau fait consolidé, ou None si rien à consolider
        """
        if not facts:
            return None

        conn = self.schema._get_conn()
        try:
            # Récupère tous les faits existants avec leur embedding
            existing = conn.execute(
                "SELECT id, fact, category, confidence, source_episodes, created_at, embedding FROM semantic_memory"
            ).fetchall()
        finally:
            conn.close()

        if not existing:
            return None

        consolidated_id = None

        for fact_data in facts:
            fact_text = fact_data.get("fact", "")
            if not fact_text:
                continue

            # Embedding du nouveau fait
            new_emb = self._embed_query(fact_text)

            for existing_row in existing:
                if existing_row["embedding"] is None:
                    continue
                old_emb = self._deserialize_embedding(existing_row["embedding"])
                sim = self._cosine_similarity(new_emb, old_emb)

                if sim > 0.90:
                    # Fusion : max confidence, merge source_episodes, keep earlier created_at
                    new_confidence = max(
                        fact_data.get("confidence", 0.8),
                        existing_row["confidence"],
                    )
                    old_sources = (
                        json.loads(existing_row["source_episodes"])
                        if existing_row["source_episodes"]
                        else []
                    )
                    new_sources = fact_data.get("source_episodes", [])
                    merged_sources = list(set(old_sources + new_sources))
                    created_at = min(
                        fact_data.get("created_at", time.time()),
                        existing_row["created_at"],
                    )
                    category = existing_row["category"] or fact_data.get("category", "general")

                    # Supprime l'ancien
                    self.delete(existing_row["id"])

                    # Ajoute le nouveau consolidé
                    consolidated_id = self.add(
                        fact=fact_text,
                        category=category,
                        confidence=new_confidence,
                        source_episodes=merged_sources,
                    )

                    logger.info(
                        "Fait consolidé : %s ↔ %s (sim=%.3f, conf=%s)",
                        existing_row["id"],
                        consolidated_id,
                        sim,
                        new_confidence,
                    )
                    break  # Un seul doublon par itération

        return consolidated_id

    def get_by_id(self, fact_id: str) -> Optional[dict[str, Any]]:
        """Récupère un fait par son ID."""
        conn = self.schema._get_conn()
        try:
            row = conn.execute(
                "SELECT id, fact, category, confidence, source_episodes, created_at, updated_at FROM semantic_memory WHERE id=?",
                (fact_id,),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            return None
        return {
            "id": row["id"],
            "fact": row["fact"],
            "category": row["category"],
            "confidence": row["confidence"],
            "source_episodes": json.loads(row["source_episodes"]) if row["source_episodes"] else [],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def delete(self, fact_id: str) -> bool:
        """Supprime un fait par son ID.

        Returns:
            True si supprimé, False si inexistant
        """
        conn = self.schema._get_conn()
        try:
            cursor = conn.execute("DELETE FROM semantic_memory WHERE id=?", (fact_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def count(self) -> int:
        """Retourne le nombre total de faits."""
        conn = self.schema._get_conn()
        try:
            row = conn.execute("SELECT COUNT(*) FROM semantic_memory").fetchone()
            return row[0]
        finally:
            conn.close()

    def list_by_category(self, category: str) -> list[dict[str, Any]]:
        """Liste tous les faits d'une catégorie donnée.

        Returns:
            Liste de dicts triés par updated_at décroissant
        """
        conn = self.schema._get_conn()
        try:
            rows = conn.execute(
                "SELECT id, fact, category, confidence, source_episodes, created_at, updated_at FROM semantic_memory WHERE category=? ORDER BY updated_at DESC",
                (category,),
            ).fetchall()
        finally:
            conn.close()

        return [
            {
                "id": row["id"],
                "fact": row["fact"],
                "category": row["category"],
                "confidence": row["confidence"],
                "source_episodes": json.loads(row["source_episodes"]) if row["source_episodes"] else [],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def update_confidence(self, fact_id: str, new_confidence: float) -> bool:
        """Met à jour le score de confiance d'un fait.

        Args:
            fact_id: ID du fait à mettre à jour
            new_confidence: Nouveau score de confiance (0–1)

        Returns:
            True si mis à jour, False si inexistant
        """
        conn = self.schema._get_conn()
        try:
            now = time.time()
            cursor = conn.execute(
                "UPDATE semantic_memory SET confidence=?, updated_at=? WHERE id=?",
                (new_confidence, now, fact_id),
            )
            conn.commit()
            return cursor.rowcount > 0
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

    def _update_access_stats(self, ids: list[str]):
        """Met à jour access_count pour les IDs donnés."""
        if not ids:
            return
        conn = self.schema._get_conn()
        try:
            for fid in ids:
                conn.execute(
                    "UPDATE semantic_memory SET access_count = access_count + 1 WHERE id = ?",
                    (fid,),
                )
            conn.commit()
        finally:
            conn.close()
