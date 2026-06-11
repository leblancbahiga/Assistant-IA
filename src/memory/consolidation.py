"""
NURU V9 — ConsolidationWorker : daemon de consolidation mémoire.

Exécuté périodiquement (toutes les 6h par défaut), il :
1. Résume les épisodes anciens (> 30 jours, importance < 0.3)
2. Extrait les faits récurrents (≥ 3 épisodes similaires) → SemanticMemory
3. Détecte les workflows répétés → prépare pour ProceduralMemory (V10)
4. Fusionne les souvenirs redondants (cos > 0.90)
5. Archive les erreurs corrigées
6. Nettoie les entrées obsolètes (decay temporel)

Inspiré des mécanismes de consolidation dans MemGPT/Letta et
des systèmes de mémoire neuro-symboliques.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Constantes ──────────────────────────────────────────────────────────
THIRTY_DAYS_S = 30 * 86400          # 30 jours en secondes
COS_SIMILARITY_GROUP = 0.85         # Seuil pour groupement d'épisodes
COS_SIMILARITY_MERGE = 0.90         # Seuil pour fusion de faits
MIN_FACT_EPISODES = 3               # Épisodes minimum pour extraire un fait


class ConsolidationWorker:
    """Daemon de consolidation mémoire s'exécutant périodiquement.

    Toutes les 6 heures (ou sur demande via run_once()), il :
    - Marque les épisodes anciens et peu importants comme consolidés
    - Extrait des faits récurrents d'épisodes similaires
    - Fusionne les faits sémantiques redondants
    - Archive les erreurs corrigées et anciennes

    Args:
        schema: Instance de MemorySchema (accès direct à la DB)
        episodic: Instance de EpisodicMemory
        semantic: Instance de SemanticMemory
        error: Instance de ErrorMemory
    """

    def __init__(self, schema, episodic, semantic, error):
        self.schema = schema
        self.episodic = episodic
        self.semantic = semantic
        self.error = error
        self._running = False
        self._timer: Optional[asyncio.Task] = None

    # ── Exécution unique ───────────────────────────────────────────────

    async def run_once(self) -> dict[str, Any]:
        """Exécute UN cycle de consolidation complet.

        Returns:
            Rapport dict avec :
            - episodes_summarized : nb d'épisodes marqués consolidés
            - facts_extracted     : nb de faits extraits → SemanticMemory
            - redundant_merged    : nb de fusions de faits redondants
            - errors_archived     : nb d'erreurs nettoyées
            - duration_s          : temps d'exécution en secondes
        """
        start = time.time()
        report: dict[str, Any] = {
            "episodes_summarized": 0,
            "facts_extracted": 0,
            "redundant_merged": 0,
            "errors_archived": 0,
            "duration_s": 0.0,
        }

        conn = self.schema._get_conn()
        try:
            cutoff = time.time() - THIRTY_DAYS_S

            # ── 1. Résumer les épisodes anciens ────────────────────────
            report["episodes_summarized"] = self._summarize_old_episodes(
                conn, cutoff
            )

            # ── 2. Extraire les faits récurrents ────────────────────────
            report["facts_extracted"] = await self._extract_recurring_facts(
                conn, cutoff
            )

            # ── 3. Fusionner les faits sémantiques redondants ──────────
            report["redundant_merged"] = await self._merge_redundant_facts(conn)

            # ── 4. Archiver les erreurs résolues anciennes ─────────────
            report["errors_archived"] = self._archive_resolved_errors(
                conn, cutoff
            )

            conn.commit()
        finally:
            conn.close()

        report["duration_s"] = round(time.time() - start, 2)
        logger.info("Consolidation terminée : %s", report)
        return report

    # ── Étapes internes ────────────────────────────────────────────────

    def _summarize_old_episodes(self, conn, cutoff: float) -> int:
        """Marque consolidated=1 pour les épisodes anciens et peu importants.

        Critères : consolidated=0, timestamp < cutoff, importance < 0.3
        """
        rows = conn.execute(
            "SELECT id FROM episodic_memory "
            "WHERE consolidated=0 AND timestamp < ? AND importance < 0.3",
            (cutoff,),
        ).fetchall()

        count = 0
        for row in rows:
            conn.execute(
                "UPDATE episodic_memory SET consolidated=1 WHERE id=?",
                (row["id"],),
            )
            count += 1

        if count:
            logger.debug("Épisodes résumés (marqués consolidated=1) : %d", count)
        return count

    async def _extract_recurring_facts(self, conn, cutoff: float) -> int:
        """Extrait des faits récurrents d'épisodes conversationnels similaires.

        1. Récupère les épisodes 'conversation' non consolidés avec embedding
        2. Regroupe par similarité cosinus > 0.85
        3. Si ≥ 3 épisodes dans un groupe → extrait un fait → ajout sémantique
        4. Marque ces épisodes comme consolidés
        """
        conv_rows = conn.execute(
            "SELECT id, summary, embedding FROM episodic_memory "
            "WHERE consolidated=0 AND event_type='conversation' "
            "AND embedding IS NOT NULL"
        ).fetchall()

        if len(conv_rows) < MIN_FACT_EPISODES:
            return 0

        episodes = list(conv_rows)
        groups = self._cluster_by_similarity(
            episodes, COS_SIMILARITY_GROUP
        )

        facts_extracted = 0
        for group in groups:
            if len(group) >= MIN_FACT_EPISODES:
                summaries = [ep["summary"] for ep in group]
                fact_text = self._extract_fact_from_summaries(summaries)
                source_ids = [ep["id"] for ep in group]

                # Ajouter le fait via un appel thread-safe (évite conflit event loop)
                await self._insert_semantic_fact(
                    conn, fact_text, "general", 0.7, source_ids
                )
                facts_extracted += 1

                # Marquer les épisodes comme consolidés
                for ep in group:
                    conn.execute(
                        "UPDATE episodic_memory SET consolidated=1 WHERE id=?",
                        (ep["id"],),
                    )

        if facts_extracted:
            logger.debug(
                "Faits récurrents extraits : %d (à partir de %d épisodes)",
                facts_extracted, len(episodes),
            )
        return facts_extracted

    async def _merge_redundant_facts(self, conn) -> int:
        """Fusionne les faits sémantiques redondants (cos > 0.90).

        Compare par paires tous les faits. Si deux faits ont une
        similarité cosinus > 0.90 :
        - Prend le max confidence
        - Merge les source_episodes
        - Supprime les deux originaux
        - Ajoute un nouveau fait fusionné
        """
        rows = conn.execute(
            "SELECT id, fact, confidence, source_episodes, embedding "
            "FROM semantic_memory"
        ).fetchall()

        facts = list(rows)
        if len(facts) < 2:
            return 0

        merged_count = 0
        deleted_ids: set[str] = set()

        for i in range(len(facts)):
            if facts[i]["id"] in deleted_ids:
                continue
            if facts[i]["embedding"] is None:
                continue

            emb_i = self._deserialize_embedding(facts[i]["embedding"])

            for j in range(i + 1, len(facts)):
                if facts[j]["id"] in deleted_ids:
                    continue
                if facts[j]["embedding"] is None:
                    continue

                emb_j = self._deserialize_embedding(facts[j]["embedding"])
                sim = self._cosine_similarity(emb_i, emb_j)

                if sim > COS_SIMILARITY_MERGE:
                    # Préparer la fusion
                    fact_a = facts[i]
                    fact_b = facts[j]

                    merged_confidence = max(
                        fact_a["confidence"], fact_b["confidence"]
                    )
                    sources_a = (
                        json.loads(fact_a["source_episodes"])
                        if fact_a["source_episodes"]
                        else []
                    )
                    sources_b = (
                        json.loads(fact_b["source_episodes"])
                        if fact_b["source_episodes"]
                        else []
                    )
                    merged_sources = list(set(sources_a + sources_b))

                    # Prendre le fait le plus long comme texte de base
                    merged_text = (
                        fact_a["fact"]
                        if len(fact_a["fact"]) >= len(fact_b["fact"])
                        else fact_b["fact"]
                    )

                    # Supprimer les deux faits originaux
                    conn.execute(
                        "DELETE FROM semantic_memory WHERE id=?",
                        (fact_a["id"],),
                    )
                    conn.execute(
                        "DELETE FROM semantic_memory WHERE id=?",
                        (fact_b["id"],),
                    )
                    deleted_ids.add(fact_a["id"])
                    deleted_ids.add(fact_b["id"])

                    # Ajouter le nouveau fait fusionné
                    await self._insert_semantic_fact(
                        conn, merged_text, "general", merged_confidence, merged_sources
                    )
                    merged_count += 1
                    break  # Un seul merge par fact i

        if merged_count:
            logger.debug(
                "Faits redondants fusionnés : %d paires", merged_count
            )
        return merged_count

    async def _insert_semantic_fact(
        self,
        conn,
        fact: str,
        category: str,
        confidence: float,
        source_episodes: list[str],
    ):
        """Insère un fait dans semantic_memory avec embedding calculé.

        Utilise l'embedder de manière asynchrone (await) pour éviter
        les conflits d'event loop avec asyncio.run().
        """
        fact_id = str(uuid.uuid4())
        now = time.time()

        # Calculer l'embedding de manière asynchrone
        emb_array = await self.semantic.embedder.embed(fact, is_query=False)
        embedding = np.array(
            emb_array[0] if len(emb_array.shape) > 1 else emb_array,
            dtype=np.float32,
        ).tobytes()

        conn.execute(
            """INSERT INTO semantic_memory
               (id, fact, category, confidence, source_episodes,
                embedding, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fact_id,
                fact,
                category,
                confidence,
                json.dumps(source_episodes, ensure_ascii=False),
                embedding,
                now,
                now,
            ),
        )

    def _archive_resolved_errors(self, conn, cutoff: float) -> int:
        """Supprime les erreurs résolues anciennes (> 30 jours)."""
        cursor = conn.execute(
            "DELETE FROM error_memory WHERE resolved=1 AND timestamp < ?",
            (cutoff,),
        )
        count = cursor.rowcount
        if count:
            logger.debug("Erreurs archivées (supprimées) : %d", count)
        return count

    # ── Algorithmes de similarité ──────────────────────────────────────

    def _cluster_by_similarity(
        self, episodes: list, threshold: float
    ) -> list[list]:
        """Regroupe les épisodes par similarité cosinus.

        Chaque épisode est ajouté au premier groupe dont l'embedding
        dépasse le seuil de similarité (greedy clustering).
        """
        groups: list[list] = []
        used: set[int] = set()

        for i, ep_i in enumerate(episodes):
            if i in used:
                continue

            group = [ep_i]
            used.add(i)
            emb_i = self._deserialize_embedding(ep_i["embedding"])

            for j in range(i + 1, len(episodes)):
                if j in used:
                    continue
                if episodes[j]["embedding"] is None:
                    continue

                emb_j = self._deserialize_embedding(episodes[j]["embedding"])
                sim = self._cosine_similarity(emb_i, emb_j)

                if sim > threshold:
                    group.append(episodes[j])
                    used.add(j)

            groups.append(group)

        return groups

    @staticmethod
    def _extract_fact_from_summaries(summaries: list[str]) -> str:
        """Extrait un fait lisible à partir de résumés d'épisodes similaires.

        Stratégie simple : prend le résumé le plus long (le plus informatif).
        Dans une version future, utiliser un LLM pour résumer.

        Args:
            summaries: Liste des résumés d'épisodes similaires

        Returns:
            Texte du fait extrait
        """
        if not summaries:
            return ""
        return max(summaries, key=len)

    @staticmethod
    def _deserialize_embedding(blob) -> np.ndarray:
        """Désérialise un embedding depuis SQLite en numpy array."""
        if isinstance(blob, memoryview):
            blob = bytes(blob)
        elif not isinstance(blob, (bytes, bytearray)):
            blob = bytes(blob)
        return np.frombuffer(blob, dtype=np.float32)

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Similarité cosinus entre deux vecteurs."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    # ── Gestion du daemon ──────────────────────────────────────────────

    async def start(self, interval_hours: int = 6):
        """Démarre le daemon avec un intervalle donné.

        Lance une boucle asyncio qui exécute run_once() périodiquement.

        Args:
            interval_hours: Intervalle entre cycles de consolidation (défaut: 6h)
        """
        if self._running:
            logger.warning("ConsolidationWorker déjà en cours d'exécution")
            return
        self._running = True
        self._timer = asyncio.ensure_future(self._run_loop(interval_hours))
        logger.info(
            "ConsolidationWorker démarré (intervalle=%sh)", interval_hours
        )

    async def _run_loop(self, interval_hours: int):
        """Boucle périodique interne."""
        while self._running:
            try:
                await self.run_once()
            except Exception as e:
                logger.error(
                    "Erreur lors de la consolidation : %s", str(e),
                    exc_info=True,
                )
            await asyncio.sleep(interval_hours * 3600)

    async def stop(self):
        """Arrête le daemon de consolidation."""
        self._running = False
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        logger.info("ConsolidationWorker arrêté")

    def is_running(self) -> bool:
        """Retourne True si le daemon est en cours d'exécution."""
        return self._running
