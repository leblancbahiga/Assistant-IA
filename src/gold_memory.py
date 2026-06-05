"""Gold Memory — Corrections utilisateur persistantes et rejouables.

Quand l'utilisateur corrige une réponse de NURU, la correction
est stockée ici et peut être rejouée pour des requêtes similaires.
"""
import time
import hashlib
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GoldRecord:
    """Une correction utilisateur enregistrée."""
    query: str
    bad_response: str
    corrected_response: str
    timestamp: float = 0.0
    query_hash: str = ""
    use_count: int = 0

    def __post_init__(self):
        if not self.query_hash:
            self.query_hash = hashlib.sha256(self.query.encode()).hexdigest()[:16]
        if not self.timestamp:
            self.timestamp = time.time()


class GoldMemory:
    """Corrections utilisateur stockées et rejouables.

    Stockage : SQLite (table gold_memory)
    Recherche : par hash exact ou embedding si threshold < 0.92

    Usage:
        gold = GoldMemory()
        gold.store(query, bad, corrected)
        best = await gold.find(similar_query)
    """

    def __init__(self, db_path=None):
        if db_path is None:
            from src.config import config
            db_path = config.index_path
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        import sqlite3
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gold_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_hash TEXT UNIQUE,
                query TEXT NOT NULL,
                bad_response TEXT,
                corrected_response TEXT NOT NULL,
                timestamp FLOAT DEFAULT 0,
                use_count INTEGER DEFAULT 0,
                embedding BLOB
            )
        """)
        conn.commit()
        conn.close()
        logger.debug("🧠 Table gold_memory initialisée")

    def store(self, query: str, bad_response: str,
              corrected_response: str, embedding: Optional[bytes] = None):
        """Stocke une correction utilisateur."""
        qhash = hashlib.sha256(query.encode()).hexdigest()[:16]
        conn = self._get_conn()

        # Vérifier si une correction existe déjà pour cette requête
        existing = conn.execute(
            "SELECT id FROM gold_memory WHERE query_hash = ?", (qhash,)
        ).fetchone()

        if existing:
            conn.execute("""
                UPDATE gold_memory SET
                    corrected_response = ?,
                    use_count = use_count + 1,
                    timestamp = strftime('%s','now')
                WHERE query_hash = ?
            """, (corrected_response, qhash))
            logger.info(f"🔄 Gold memory mise à jour: {query[:40]}")
        else:
            conn.execute("""
                INSERT INTO gold_memory
                    (query_hash, query, bad_response, corrected_response, timestamp, embedding)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (qhash, query, bad_response, corrected_response, time.time(), embedding))
            logger.info(f"💎 Nouvelle gold memory: {query[:40]}")

        conn.commit()
        conn.close()

    async def find(self, query: str) -> Optional[GoldRecord]:
        """Cherche une correction correspondant à une requête.

        Stratégie :
        1. Hash exact → retour immédiat
        2. Embedding si embedder disponible → similarité > 0.92
        """
        qhash = hashlib.sha256(query.encode()).hexdigest()[:16]
        conn = self._get_conn()

        # 1. Hash exact
        row = conn.execute("""
            SELECT query, bad_response, corrected_response, timestamp, use_count
            FROM gold_memory WHERE query_hash = ?
        """, (qhash,)).fetchone()

        if row:
            conn.close()
            return GoldRecord(
                query=row["query"],
                bad_response=row["bad_response"],
                corrected_response=row["corrected_response"],
                timestamp=row["timestamp"],
                query_hash=qhash,
                use_count=row["use_count"],
            )

        # 2. Embedding search (si un embedder est disponible)
        try:
            from src.embedder import Embedder
            embedder = Embedder()
            embeddings = await embedder.embed(query, is_query=True)
            import sqlite_vec
            qvec = sqlite_vec.serialize_float32(embeddings[0])

            conn.enable_load_extension(True)
            sqlite_vec.load(conn)

            # Chercher dans les embeddings gold_memory
            vec_row = conn.execute("""
                SELECT query, bad_response, corrected_response, timestamp, use_count, distance
                FROM gold_memory
                WHERE embedding IS NOT NULL
                  AND embedding MATCH ?
                ORDER BY distance
                LIMIT 1
            """, [qvec]).fetchone()

            if vec_row:
                similarity = 1 - vec_row["distance"]
                if similarity > 0.92:
                    conn.close()
                    return GoldRecord(
                        query=vec_row["query"],
                        bad_response=vec_row["bad_response"],
                        corrected_response=vec_row["corrected_response"],
                        timestamp=vec_row["timestamp"],
                        query_hash=qhash,
                        use_count=vec_row["use_count"],
                    )
        except Exception as e:
            logger.warning(f"⚠️ Gold memory embedding search failed: {e}")

        conn.close()
        return None

    def get_stats(self) -> dict:
        """Retourne les statistiques de la gold memory."""
        conn = self._get_conn()
        stats = {"total": 0, "total_uses": 0}
        try:
            row = conn.execute("""
                SELECT COUNT(*), COALESCE(SUM(use_count), 0)
                FROM gold_memory
            """).fetchone()
            if row:
                stats["total"] = row[0]
                stats["total_uses"] = row[1]
        except Exception:
            pass
        conn.close()
        return stats
