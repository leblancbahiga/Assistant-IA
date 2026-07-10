"""NURU V15 Phase 3 — ProceduralMemory (P1 #35).

Mémoire procédurale : workflows, patterns de raisonnement et séquences
d'outils appris par l'usage. Stocke les procédures qui ont fonctionné
avec leur taux de succès pour réutilisation.

Couche 5/6 du MemoryManager unifié (Item 28).
"""

import json
import logging
import time
import uuid
from typing import Any, Optional

import numpy as np

from src.memory.schema import MemorySchema
from src.embedder import Embedder

logger = logging.getLogger(__name__)

# Nombre max de pas par procédure
MAX_STEPS = 50
# Taille max d'un pas (caractères)
MAX_STEP_LENGTH = 2000


class ProceduralMemory:
    """Stockage de procédures réutilisables avec taux de succès.

    Chaque procédure est une séquence d'étapes (steps) associée à un type
    de tâche, avec un taux de succès et une durée moyenne d'exécution.

    La recherche se fait par similarité sémantique du task_type.
    """

    def __init__(self, schema: MemorySchema):
        self.schema = schema
        self._embedder = None

    @property
    def embedder(self):
        if self._embedder is None:
            self._embedder = Embedder()
        return self._embedder

    def _embed_sync(self, text: str) -> np.ndarray:
        """Version synchrone du calcul d'embedding (compatible event loop MLX)."""
        try:
            import asyncio
            return asyncio.run(self.embedder.embed(text, is_query=False))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self.embedder.embed(text, is_query=False))
            finally:
                loop.close()

    # ── CRUD ──────────────────────────────────────────────────────────

    def add(
        self,
        task_type: str,
        steps: list[str],
        tools_required: Optional[list[str]] = None,
    ) -> str:
        """Ajoute une procédure à la mémoire.

        Args:
            task_type: Type de tâche (ex: 'rag_search', 'code_generation')
            steps: Liste ordonnée des étapes
            tools_required: Outils nécessaires (ex: ['rag', 'embedder'])

        Returns:
            ID unique de la procédure
        """
        proc_id = str(uuid.uuid4())
        steps_json = json.dumps(steps[:MAX_STEPS])
        tools_json = json.dumps(tools_required or [])

        # Embedding du task_type pour la recherche
        embedding = self._embed_sync(task_type)
        embedding_blob = np.array(embedding, dtype=np.float32).tobytes()

        conn = self.schema._get_conn()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO procedural_memory
                   (id, task_type, steps, tools_required, success_rate,
                    avg_duration_ms, last_used, embedding)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (proc_id, task_type, steps_json, tools_json,
                 0.0, 0.0, time.time(), embedding_blob),
            )
            conn.commit()
        finally:
            conn.close()

        logger.info("🧠 ProceduralMemory.add(%s) → %s", task_type, proc_id)
        return proc_id

    def update_success(
        self,
        proc_id: str,
        success: bool,
        duration_ms: float,
    ) -> None:
        """Met à jour le taux de succès et la durée après exécution.

        Args:
            proc_id: ID de la procédure
            success: True si l'exécution a réussi
            duration_ms: Durée d'exécution en millisecondes
        """
        conn = self.schema._get_conn()
        try:
            row = conn.execute(
                "SELECT success_rate, avg_duration_ms, use_count FROM procedural_memory WHERE id=?",
                (proc_id,),
            ).fetchone()

            if row is None:
                return

            # Si pas de colonne use_count, fallback sur la moyenne simple
            old_rate = row["success_rate"] or 0.0
            old_dur = row["avg_duration_ms"] or 0.0

            # Moyenne exponentielle (poids plus fort pour les récents)
            alpha = 0.3
            new_rate = old_rate * (1 - alpha) + (1.0 if success else 0.0) * alpha
            new_dur = old_dur * (1 - alpha) + duration_ms * alpha

            conn.execute(
                """UPDATE procedural_memory
                   SET success_rate=?, avg_duration_ms=?, last_used=?
                   WHERE id=?""",
                (new_rate, new_dur, time.time(), proc_id),
            )
            conn.commit()
        finally:
            conn.close()

    def search(self, task_type: str, limit: int = 5) -> list[dict[str, Any]]:
        """Recherche des procédures par similarité sémantique.

        Args:
            task_type: Description de la tâche
            limit: Nombre max de résultats

        Returns:
            Liste de dicts : {id, task_type, steps, tools_required,
                             success_rate, avg_duration_ms, similarity}
        """
        query_emb = self._embed_sync(task_type)
        results: list[dict[str, Any]] = []

        conn = self.schema._get_conn()
        try:
            rows = conn.execute(
                "SELECT id, task_type, steps, tools_required, "
                "success_rate, avg_duration_ms, embedding "
                "FROM procedural_memory ORDER BY last_used DESC"
            ).fetchall()

            for row in rows:
                stored_emb = row["embedding"]
                if stored_emb is None:
                    continue

                emb_array = np.frombuffer(stored_emb, dtype=np.float32)
                if emb_array.shape != np.array(query_emb).shape:
                    continue

                sim = float(np.dot(emb_array, query_emb) /
                            (np.linalg.norm(emb_array) * np.linalg.norm(query_emb) + 1e-10))

                results.append({
                    "id": row["id"],
                    "task_type": row["task_type"],
                    "steps": json.loads(row["steps"]),
                    "tools_required": json.loads(row["tools_required"] or "[]"),
                    "success_rate": row["success_rate"],
                    "avg_duration_ms": row["avg_duration_ms"],
                    "similarity": sim,
                })

            results.sort(key=lambda r: r["similarity"], reverse=True)
            return results[:limit]

        finally:
            conn.close()

    def get_by_task_type(self, task_type: str) -> Optional[dict[str, Any]]:
        """Récupère la meilleure procédure pour un type de tâche exact."""
        conn = self.schema._get_conn()
        try:
            row = conn.execute(
                "SELECT id, task_type, steps, tools_required, "
                "success_rate, avg_duration_ms "
                "FROM procedural_memory WHERE task_type=? "
                "ORDER BY success_rate DESC LIMIT 1",
                (task_type,),
            ).fetchone()

            if row is None:
                return None
            return {
                "id": row["id"],
                "task_type": row["task_type"],
                "steps": json.loads(row["steps"]),
                "tools_required": json.loads(row["tools_required"] or "[]"),
                "success_rate": row["success_rate"],
                "avg_duration_ms": row["avg_duration_ms"],
            }
        finally:
            conn.close()

    def get_all(self, limit: int = 50) -> list[dict]:
        """Liste toutes les procédures (pour débogage/admin)."""
        conn = self.schema._get_conn()
        try:
            rows = conn.execute(
                "SELECT id, task_type, success_rate, avg_duration_ms, last_used "
                "FROM procedural_memory ORDER BY last_used DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def delete(self, proc_id: str) -> bool:
        """Supprime une procédure."""
        conn = self.schema._get_conn()
        try:
            cur = conn.execute("DELETE FROM procedural_memory WHERE id=?", (proc_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
