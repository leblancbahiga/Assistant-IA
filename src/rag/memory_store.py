"""Semantic cache for RAG results with diagnostic storage (Sprint 6.2).

Stores query → (response, diagnostic) pairs using plain sqlite3
with MD5 hash as key. Independent from src/memory_store.py (which
uses vec0 vector search).

Used by the orchestrator for fast cache lookups and by the dashboard
for diagnostic inspection.
"""
import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SemanticCache:
    """Cache sémantique pour les résultats RAG avec diagnostic embarqué.

    Utilise sqlite3 avec hash MD5 de la requête comme clé.
    Stocke : query, response, rag_diagnostic (JSON), timestamp.

    Methods:
        get_cache(query_hash) -> (response, diagnostic) or (None, None)
        set_cache(query_hash, response, diagnostic)
        get_diagnostics(limit=50) -> list[dict] pour inspection dashboard
        get_stats() -> dict
        clear()
    """

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            from src.config import config
            db_path = config.index_path.parent / "semantic_cache.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(str(self._db_path), timeout=10)

    def _init_db(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS semantic_cache (
                query_hash TEXT PRIMARY KEY,
                query_sample TEXT,
                response TEXT NOT NULL,
                diagnostic TEXT,
                created_at REAL NOT NULL,
                hit_count INTEGER DEFAULT 0,
                last_hit_at REAL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_semantic_cache_hash
            ON semantic_cache (query_hash)
        """)
        conn.commit()
        conn.close()
        logger.info(f"📦 SemanticCache initialisé: {self._db_path}")

    # ── Hachage ──────────────────────────────────────────────────────────

    @staticmethod
    def hash_query(query: str) -> str:
        """Calcule le hash MD5 d'une requête."""
        return hashlib.md5(query.encode("utf-8")).hexdigest()

    # ─── Accès en lecture ─────────────────────────────────────────────────

    def get_cache(self, query_hash: str) -> tuple[Optional[str], Optional[dict]]:
        """Récupère (response, diagnostic) par query_hash.

        Args:
            query_hash: MD5 hash de la requête (via SemanticCache.hash_query())

        Returns:
            (response, diagnostic_dict) ou (None, None) si absence.
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT response, diagnostic FROM semantic_cache WHERE query_hash = ?",
                (query_hash,),
            ).fetchone()

            if row is None:
                return None, None

            response, diagnostic_json = row
            # Incrémenter le compteur de hits
            conn.execute(
                "UPDATE semantic_cache SET hit_count = hit_count + 1, last_hit_at = ? WHERE query_hash = ?",
                (time.time(), query_hash),
            )
            conn.commit()

            diagnostic = json.loads(diagnostic_json) if diagnostic_json else None
            logger.debug(f"📦 SemanticCache hit: {query_hash[:12]}...")
            return response, diagnostic
        finally:
            conn.close()

    # ─── Accès en écriture ────────────────────────────────────────────────

    def set_cache(
        self,
        query_hash: str,
        response: str,
        diagnostic: Optional[dict] = None,
        query_sample: str = "",
    ):
        """Stocke une entrée dans le cache.

        Args:
            query_hash: MD5 hash de la requête
            response: Réponse générée
            diagnostic: Diagnostic RAG (strategies_tried, scores, timing…)
            query_sample: Extrait de la requête originale (pour inspection)
        """
        diagnostic_json = (
            json.dumps(diagnostic, ensure_ascii=False) if diagnostic else None
        )
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO semantic_cache
                   (query_hash, query_sample, response, diagnostic, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (query_hash, query_sample[:200], response, diagnostic_json, time.time()),
            )
            conn.commit()
            logger.debug(f"📦 SemanticCache set: {query_hash[:12]}...")
        finally:
            conn.close()

    # ─── Inspection (pour dashboard) ─────────────────────────────────────

    def get_diagnostics(self, limit: int = 50) -> list[dict]:
        """Récupère les diagnostics récents pour inspection.

        Returns:
            Liste de dicts avec les clés : query_hash, query_sample,
            response_truncated, diagnostic, created_at, hit_count.
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT query_hash, query_sample, response,
                          diagnostic, created_at, hit_count
                   FROM semantic_cache
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()

            results = []
            for row in rows:
                entry = {
                    "query_hash": row[0],
                    "query_sample": row[1] or "",
                    "response_truncated": (row[2] or "")[:150],
                    "diagnostic": json.loads(row[3]) if row[3] else None,
                    "created_at": row[4],
                    "hit_count": row[5],
                }
                results.append(entry)
            return results
        finally:
            conn.close()

    # ─── Statistiques ────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Retourne les statistiques du cache.

        Returns:
            dict avec total_entries et total_hits.
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(hit_count), 0) FROM semantic_cache"
            ).fetchone()
            return {
                "total_entries": row[0] if row else 0,
                "total_hits": row[1] if row else 0,
            }
        finally:
            conn.close()

    def clear(self):
        """Vide complètement le cache."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM semantic_cache")
            conn.commit()
            logger.info("📦 SemanticCache vidé")
        finally:
            conn.close()
