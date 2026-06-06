try:
    import sqlite3
    sqlite3.connect(":memory:").enable_load_extension(True)
except (AttributeError, sqlite3.OperationalError):
    import pysqlite3 as sqlite3

import hashlib
import time
import logging
import json
from typing import List, Optional, Tuple
from src.config import config
import sqlite_vec
from src.embedder import Embedder

logger = logging.getLogger(__name__)

class MemoryStore:
    """Gestionnaire de mémoire SQLite : Faits, Historique, Procédures et Cache."""
    
    def __init__(self):
        self.db_path = config.index_path
        self.embedder = Embedder()
        self._init_db()
        self._init_feedback_tables()  # V4.5 Phase 3 : Feedback + Knowledge Cards
        self._memory_context = {} # Working Memory (RAM)

    def _get_conn(self):
        """Ouvre une nouvelle connexion (Thread-safe)."""
        return sqlite3.connect(str(self.db_path), timeout=20)

    def _init_db(self):
        conn = self._get_conn()
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        
        # Faits (Semantic Memory)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                category TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Faits utilisateur structurés (Long-Term Memory — NURU V4.5)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact_type TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT DEFAULT 'conversation',
                confidence REAL DEFAULT 0.8,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_facts_type
            ON user_facts (fact_type)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_facts_active
            ON user_facts (is_active)
        """)
        # Historique (Episodic Memory)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Préférences et Règles (Procedural Memory)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS procedural (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_name TEXT UNIQUE,
                instruction TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Auto-analyse (Reflection Memory)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reflection (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT,
                feedback TEXT,
                quality_score FLOAT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Semantic Cache (Vectorized)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS semantic_cache USING vec0(
                embedding FLOAT[768],
                query TEXT,
                response TEXT,
                hit_count INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

    # --- Semantic Cache (Vector) ---
    async def get_cache(self, query: str) -> Optional[str]:
        """Recherche sémantique dans le cache avec un seuil de 0.92."""
        embeddings = await self.embedder.embed(query, is_query=True)
        qvec = sqlite_vec.serialize_float32(embeddings[0])
        
        conn = self._get_conn()
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        
        row = conn.execute("""
            SELECT response, distance
            FROM semantic_cache
            WHERE embedding MATCH ?
            ORDER BY distance
            LIMIT 1
        """, [qvec]).fetchone()
        
        if row:
            response, dist = row
            similarity = 1 - dist
            if similarity > 0.92:
                logger.info(f"Semantic Cache Hit (Sim={similarity:.2f})")
                conn.execute("UPDATE semantic_cache SET hit_count = hit_count + 1 WHERE response = ?", [response])
                conn.commit()
                conn.close()
                return response
        
        conn.close()
        return None

    async def set_cache(self, query: str, response: str):
        """Enregistre une réponse dans le cache vectoriel."""
        embeddings = await self.embedder.embed(query, is_query=False)
        qvec = sqlite_vec.serialize_float32(embeddings[0])
        
        conn = self._get_conn()
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        
        conn.execute("""
            INSERT INTO semantic_cache (embedding, query, response, hit_count)
            VALUES (?, ?, ?, 0)
        """, [qvec, query, response])
        conn.commit()
        conn.close()

    # --- Historique de Session (Episodic) ---
    def add_message(self, role: str, content: str):
        conn = self._get_conn()
        conn.execute("INSERT INTO history (role, content) VALUES (?, ?)", (role, content))
        conn.commit()
        conn.close()

    def get_recent_history(self, limit: int = 5) -> List[dict]:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT role, content FROM history ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        history = [{"role": r, "content": c} for r, c in cursor.fetchall()]
        conn.close()
        return list(reversed(history))

    # --- Faits Utilisateur (Semantic) ---
    def add_fact(self, content: str, category: str = "general"):
        conn = self._get_conn()
        conn.execute("INSERT INTO facts (content, category) VALUES (?, ?)", (content, category))
        conn.commit()
        conn.close()
        logger.info(f"Nouveau fait mémorisé : {content}")

    def get_recent_facts(self, limit: int = 20) -> list[str]:
        """Récupère les faits les plus récents (par défaut 20)."""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT content FROM facts ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )
        facts = [row[0] for row in cursor.fetchall()]
        conn.close()
        return list(reversed(facts))

    def get_all_facts(self) -> str:
        """Déprécié : utiliser get_recent_facts()."""
        logger.warning("get_all_facts() is deprecated — use get_recent_facts(limit=20)")
        conn = self._get_conn()
        cursor = conn.execute("SELECT content FROM facts ORDER BY timestamp DESC")
        facts = [row[0] for row in cursor.fetchall()]
        conn.close()
        return "\n".join(reversed(facts)) if facts else ""

    # --- Procedural Memory (Rules) ---
    def add_procedure(self, name: str, instruction: str):
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO procedural (rule_name, instruction) VALUES (?, ?)",
            (name, instruction)
        )
        conn.commit()
        conn.close()

    def get_procedures(self) -> str:
        conn = self._get_conn()
        cursor = conn.execute("SELECT instruction FROM procedural")
        rules = [row[0] for row in cursor.fetchall()]
        conn.close()
        return "\n".join(rules) if rules else ""

    # --- Cache Stats ---
    def get_cache_stats(self) -> dict:
        """Retourne les statistiques complètes du cache sémantique."""
        conn = self._get_conn()
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        stats = {"total_entries": 0, "total_hits": 0, "hit_rate": 0.0, "avg_distance": 0.0}
        try:
            row = conn.execute("SELECT COUNT(*), COALESCE(SUM(hit_count), 0) FROM semantic_cache").fetchone()
            if row:
                stats["total_entries"] = row[0]
                stats["total_hits"] = row[1]
                stats["hit_rate"] = round(stats["total_hits"] / max(stats["total_entries"], 1), 2)
        except Exception:
            pass
        conn.close()
        return stats

    # ═══════════════════════════════════════════════
    # V4.5 Phase 3 : Feedback utilisateur
    # ═══════════════════════════════════════════════

    def _init_feedback_tables(self):
        """Crée les tables feedback et knowledge_cards si elles n'existent pas."""
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                response TEXT,
                vote TEXT NOT NULL CHECK(vote IN ('up', 'down')),
                correction TEXT,
                source_chunks TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                content TEXT NOT NULL,
                title TEXT DEFAULT '',
                use_count INTEGER DEFAULT 1,
                success_count INTEGER DEFAULT 1,
                confidence FLOAT DEFAULT 0.8,
                last_used DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source, content)
            )
        """)
        conn.commit()
        conn.close()

    def register_feedback(self, query: str, vote: str,
                          response: str = "", correction: str = "",
                          source_chunks: list[str] = None):
        """Enregistre un vote 👍/👎 avec correction optionnelle.

        Args:
            query: Requête utilisateur
            vote: 'up' (👍) ou 'down' (👎)
            response: Réponse de NURU (optionnelle)
            correction: Texte corrigé (si 👎)
            source_chunks: Liste des chunks sources utilisés
        """
        conn = self._get_conn()
        chunks_json = json.dumps(source_chunks or [])
        conn.execute("""
            INSERT INTO feedback (query, response, vote, correction, source_chunks)
            VALUES (?, ?, ?, ?, ?)
        """, (query, response, vote, correction, chunks_json))
        conn.commit()
        conn.close()

        # Si 👍, promouvoir les chunks utilisés
        if vote == "up" and source_chunks:
            for chunk_id in source_chunks:
                self._increment_knowledge_card(chunk_id, success=True)
        # Si 👎, enregistrer mais ne pas promouvoir
        elif vote == "down" and source_chunks:
            for chunk_id in source_chunks:
                self._increment_knowledge_card(chunk_id, success=False)

        logger.info(f"📝 Feedback {vote} enregistré pour: {query[:40]}")

    def get_feedback_stats(self) -> dict:
        """Statistiques du feedback utilisateur."""
        conn = self._get_conn()
        stats = {"total": 0, "up": 0, "down": 0, "corrections": 0}
        try:
            stats["total"] = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
            stats["up"] = conn.execute("SELECT COUNT(*) FROM feedback WHERE vote='up'").fetchone()[0]
            stats["down"] = conn.execute("SELECT COUNT(*) FROM feedback WHERE vote='down'").fetchone()[0]
            stats["corrections"] = conn.execute(
                "SELECT COUNT(*) FROM feedback WHERE correction IS NOT NULL AND correction != ''"
            ).fetchone()[0]
        except Exception:
            pass
        conn.close()
        return stats

    # ═══════════════════════════════════════════════
    # V4.5 Phase 3 : Knowledge Cards (chunks promus)
    # ═══════════════════════════════════════════════

    def _increment_knowledge_card(self, chunk_key: str, success: bool = True):
        """Incrémente le compteur d'usage d'un chunk.

        Si le chunk est nouveau, l'ajoute.
        Si le chunk existe et a assez de succès (>3), c'est une knowledge card.
        """
        conn = self._get_conn()
        existing = conn.execute(
            "SELECT id, use_count, success_count FROM knowledge_cards WHERE content = ?",
            (chunk_key,)
        ).fetchone()

        if existing:
            use_count = existing[1] + 1
            success_count = existing[2] + (1 if success else 0)
            conn.execute("""
                UPDATE knowledge_cards SET
                    use_count = ?, success_count = ?,
                    confidence = ROUND(CAST(? AS FLOAT) / ?, 3),
                    last_used = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (use_count, success_count, success_count, use_count, existing[0]))
        else:
            # Nouvelle entrée — on stocke le chunk_key comme contenu
            parts = chunk_key.split("|", 1)
            source = parts[0] if len(parts) > 1 else "unknown"
            content = parts[-1] if len(parts) > 1 else chunk_key
            conn.execute("""
                INSERT OR IGNORE INTO knowledge_cards (source, content, use_count, success_count)
                VALUES (?, ?, 1, ?)
            """, (source, content[:500], 1 if success else 0))

        conn.commit()
        conn.close()

    def get_knowledge_cards(self, min_confidence: float = 0.75,
                            min_uses: int = 3, limit: int = 20) -> list[dict]:
        """Récupère les knowledge cards (chunks les plus utiles).

        Une knowledge card est un chunk qui a été :
        - Utilisé > 3 fois
        - Avec un taux de succès > 75%
        """
        conn = self._get_conn()
        cards = []
        try:
            rows = conn.execute("""
                SELECT source, content, title, use_count, success_count,
                       confidence, last_used
                FROM knowledge_cards
                WHERE use_count >= ? AND confidence >= ?
                ORDER BY confidence DESC, use_count DESC
                LIMIT ?
            """, (min_uses, min_confidence, limit)).fetchall()

            for row in rows:
                cards.append({
                    "source": row[0],
                    "content": row[1][:200],
                    "title": row[2],
                    "use_count": row[3],
                    "success_rate": f"{row[4]}/{row[3]} ({row[5]:.0%})",
                    "last_used": row[6],
                })
        except Exception as e:
            logger.warning(f"Knowledge cards error: {e}")
        conn.close()
        return cards

    def purge_cache(self):
        """Vide le cache sémantique."""
        conn = self._get_conn()
        conn.execute("DELETE FROM semantic_cache")
        conn.commit()
        conn.close()
        logger.info("Cache sémantique purgé.")

    def purge_history(self, keep_last: int = 10):
        """Supprime l'historique ancien en gardant les N derniers messages."""
        conn = self._get_conn()
        conn.execute("""
            DELETE FROM history WHERE id NOT IN (
                SELECT id FROM history ORDER BY timestamp DESC LIMIT ?
            )
        """, (keep_last,))
        conn.commit()
        conn.close()
        logger.info(f"Historique purgé, {keep_last} messages conservés.")

    def get_total_facts_count(self) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) FROM facts").fetchone()
        conn.close()
        return row[0] if row else 0

    def get_total_history_count(self) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) FROM history").fetchone()
        conn.close()
        return row[0] if row else 0

    def get_memory_size(self) -> int:
        """Taille du fichier DB en octets."""
        try:
            return self.db_path.stat().st_size
        except Exception:
            return 0

    def analyze_memory(self) -> dict:
        """Analyse complète de la mémoire."""
        conn = self._get_conn()
        analysis = {}
        try:
            analysis["total_facts"] = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            analysis["total_history"] = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
            analysis["total_procedures"] = conn.execute("SELECT COUNT(*) FROM procedural").fetchone()[0]
            analysis["total_reflections"] = conn.execute("SELECT COUNT(*) FROM reflection").fetchone()[0]
            cache_row = conn.execute("SELECT COUNT(*), COALESCE(SUM(hit_count), 0) FROM semantic_cache").fetchone()
            analysis["cache_entries"] = cache_row[0] if cache_row else 0
            analysis["cache_hits"] = cache_row[1] if cache_row else 0
            analysis["db_size_kb"] = round(self.get_memory_size() / 1024, 1)
            analysis["recent_activity"] = conn.execute(
                "SELECT COUNT(*) FROM history WHERE timestamp > datetime('now', '-1 hour')"
            ).fetchone()[0]
        except Exception as e:
            analysis["error"] = str(e)
        conn.close()
        return analysis

    # --- Reflection Memory (Self-Improvement) ---
    def add_reflection(self, query: str, feedback: str, score: float):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO reflection (query, feedback, quality_score) VALUES (?, ?, ?)",
            (query, feedback, score)
        )
        conn.commit()
        conn.close()

    # ═══════════════════════════════════════════════
    # Long-Term Memory : user_facts CRUD
    # ═══════════════════════════════════════════════

    def store_user_fact(self, fact_type: str, content: str,
                        source: str = "conversation",
                        confidence: float = 0.8) -> int:
        """Insère un fait utilisateur dans user_facts. Retourne l'id."""
        conn = self._get_conn()
        existing = conn.execute(
            "SELECT id FROM user_facts WHERE content = ? AND is_active = 1",
            (content,)
        ).fetchone()
        if existing:
            conn.execute("""
                UPDATE user_facts
                SET updated_at = CURRENT_TIMESTAMP, confidence = MAX(confidence, ?)
                WHERE id = ?
            """, (confidence, existing[0]))
            conn.commit()
            conn.close()
            return existing[0]
        conn.execute("""
            INSERT INTO user_facts (fact_type, content, source, confidence)
            VALUES (?, ?, ?, ?)
        """, (fact_type, content, source, confidence))
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        conn.close()
        logger.info(f"🧠 Nouveau fait utilisateur mémorisé [{fact_type}]: {content[:60]}")
        return new_id

    def get_user_facts(self, fact_type: Optional[str] = None,
                       limit: int = 50) -> list[dict]:
        """Récupère les faits utilisateur actifs, filtrés par type optionnel."""
        conn = self._get_conn()
        if fact_type:
            rows = conn.execute("""
                SELECT id, fact_type, content, source, confidence, created_at, updated_at
                FROM user_facts
                WHERE is_active = 1 AND fact_type = ?
                ORDER BY updated_at DESC LIMIT ?
            """, (fact_type, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT id, fact_type, content, source, confidence, created_at, updated_at
                FROM user_facts
                WHERE is_active = 1
                ORDER BY updated_at DESC LIMIT ?
            """, (limit,)).fetchall()
        conn.close()
        return [
            {"id": r[0], "fact_type": r[1], "content": r[2],
             "source": r[3], "confidence": r[4],
             "created_at": r[5], "updated_at": r[6]}
            for r in rows
        ]

    def search_user_facts(self, keywords: list[str],
                          limit: int = 10) -> list[dict]:
        """Recherche textuelle simple dans les faits utilisateur actifs."""
        conn = self._get_conn()
        conditions = " AND ".join(["content LIKE ?" for _ in keywords])
        params = [f"%{kw}%" for kw in keywords]
        rows = conn.execute(f"""
            SELECT id, fact_type, content, source, confidence, created_at, updated_at
            FROM user_facts
            WHERE is_active = 1 AND {conditions}
            ORDER BY confidence DESC, updated_at DESC LIMIT ?
        """, (*params, limit)).fetchall()
        conn.close()
        return [
            {"id": r[0], "fact_type": r[1], "content": r[2],
             "source": r[3], "confidence": r[4],
             "created_at": r[5], "updated_at": r[6]}
            for r in rows
        ]

    def deactivate_user_fact(self, fact_id: int):
        """Désactive (soft-delete) un fait utilisateur."""
        conn = self._get_conn()
        conn.execute("UPDATE user_facts SET is_active = 0 WHERE id = ?", (fact_id,))
        conn.commit()
        conn.close()
