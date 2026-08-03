# NURU V15 #25 : sqlite3 standard (pysqlite3-binary déprécié)
try:
    import sqlite3
except ImportError:
    import sqlite3  # devrait toujours fonctionner (stdlib)
    import logging
    logging.getLogger(__name__).warning("pysqlite3-binary non trouvé, utilisation sqlite3 standard (extensions désactivées)")
import sqlite_vec
import asyncio
import logging
import os
import re
import json
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
from dataclasses import dataclass, field
from pathlib import Path
from src.config import config
from src.embedder import Embedder
from src.rag.query_rewriter import CloudQueryRewriter
from src.reranker import CrossEncoderReranker
from src.llm_cloud import CloudLLM
from src.core.ram_budget import Priority, get_budget

logger = logging.getLogger(__name__)


# ── RAMBudgetManager global ─────────────────────────────────────────
# Initialisation unique : enregistre les composants NURU
def _init_budget() -> None:
    budget = get_budget()
    budget.hard_limit_gb = 6.0
    budget.soft_limit_gb = 5.0
    budget.register_component("embedder", Priority.EMBEDDER, estimated_mb=400)
    budget.register_component("reranker", Priority.RERANKER, estimated_mb=400)
    budget.register_component("llm", Priority.LLM, estimated_mb=3500)
    budget.register_component("cache_llm", Priority.CACHE, estimated_mb=200)
    logger.info("📊 RAMBudgetManager initialisé (hard=6.0 Go, soft=5.0 Go)")


_init_budget()


# ── PromptGuard V10.2 : Protection anti-injection RAG ──
_INJECTION_PATTERNS = [
    "Tu es NURU", "Tu es maintenant", "Ignore les instructions",
    "Ignore toutes", "Ignorez", "[SYSTEM]", "[INST]",
    "<<SYS>>", "<|im_start|>system", "<|im_start|>user",
    "<|im_start|>assistant", "<|assistant|>",
]


def sanitize_rag_query(query: str, max_chars: int = 10_000) -> str:
    """Nettoie une requête RAG contre l'injection de prompt.

    - Troncature à ``max_chars`` caractères
    - Échappement des délimiteurs de contexte RAG (===)
    - Échappement des blocs de code (```)
    - Neutralisation douce des motifs d'instruction système
    """
    if not query:
        return ""

    # 1. Troncature
    query = query[:max_chars]

    # 2. (supprimé V16 AUDIT QW18) : l'échappement de `===` cassait la recherche
    #    de documents contenant ce séparateur (ex: "RIKOLTO === BEACCOM").
    #    Le === n'est qu'un séparateur visuel dans _format_context(), pas un
    #    motif d'injection.
    
    # 3. (supprimé V16 AUDIT QW18) : l'échappement de ``` cassait la recherche
    #    de code source contenant des triple backticks.
    
    # 4. Neutralisation des motifs d'injection système
    #    Remplacement par homoglyphes pour casser la reconnaissance sans perdre le sens
    for pattern in _INJECTION_PATTERNS:
        if pattern in query:
            safe = pattern.replace("I", "Ī").replace("i", "ī")
            query = query.replace(pattern, safe)

    return query.strip()


def sanitize_chunk_content(content: str, max_chars: int = 4000) -> str:
    """Nettoie le contenu d'un chunk RAG avant injection dans le contexte.

    - Troncature
    - Échappement des marqueurs de début/fin de contexte
    """
    if not content:
        return ""

    content = content[:max_chars]
    content = content.replace("=== DÉBUT DU CONTEXTE ===", "(début contexte)")
    content = content.replace("=== FIN DU CONTEXTE ===", "(fin contexte)")
    content = content.replace("```", "(code block)")

    return content.strip()


@dataclass
class RAGResult:
    documents_found: int = 0
    chunks_retrieved: int = 0
    chunks_injected: int = 0
    top_score: float = 0.0
    all_scores: list[float] = field(default_factory=list)
    retrieval_time_ms: float = 0.0
    sources: list[dict] = field(default_factory=list)
    rejected_chunks: int = 0
    rejection_reason: str = ""
    query_rewritten: str = ""
    embedding_model: str = "Qwen3-Embedding-0.6B-4bit-DWQ"
    top_k_configured: int = 5
    top_k_actual: int = 0
    tokens_injected: int = 0
    diagnostic: Optional[dict] = None  # V8+ : RAGDiagnostic sérialisé
    confidence_label: str = "MOYENNE"  # V15 Phase 0B : défaut neutre

class RAGEngine:
    """Moteur RAG Hybride : Recherche sémantique (sqlite-vec) + BM25."""
    
    def __init__(self, cloud_llm: Optional[CloudLLM] = None):
        self.db_path = config.index_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # V15 : détection sqlite-vec (indisponible sur Python 3.13+)
        self._has_vec0 = self._check_vec0()
        self.embedder = Embedder()
        # V16 AUDIT FIX QW1 : injecter cloud_llm existant (-40 Mo RAM, coût API tracé)
        # Si non fourni, créer un nouveau (comportement legacy)
        self.cloud = cloud_llm or CloudLLM()
        self.rewriter = CloudQueryRewriter(cloud_llm=self.cloud)
        self.reranker = CrossEncoderReranker()  # : Reranker sémantique
        self.reranker.set_embedder(self.embedder)  # Connecte l'embedder
        self.last_top_score = 0.0
        self._init_db()
        # Phase 0 : seuils configurés pour reranker conditionnel
        # V10.3k — audit Option C : seuil RAM lu depuis Config (surchargeable via yaml)
        self._rerank_min_score = 0.40   # En dessous : pas la peine
        self._rerank_max_score = 0.75   # Au dessus : déjà suffisant
        self._rerank_min_ram_mb = getattr(
            config, "rerank_min_ram_mb", 800
        )  # RAM minimale pour activer le cross-encoder
        # V8+ Sprint 4 : Orchestrateur multi-stratégie (initialisé paresseusement)
        self._multi_search = None
        # V12 — Intégration mémoire V9 (initialisé paresseusement)
        self._memory = None

    def _check_vec0(self) -> bool:
        """V15 : Vérifie si sqlite-vec est disponible (échoue sur Python 3.13+)."""
        try:
            conn = sqlite3.connect(":memory:")
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.close()
            logger.info("✅ sqlite-vec disponible (recherche vectorielle active)")
            return True
        except (AttributeError, Exception) as e:
            logger.info(f"sqlite-vec indisponible ({e}) — FTS5+BM25 actif")
            return False

    def _ensure_multi_search(self):
        """V8+ Sprint 4.8 : Initialise paresseusement le MultiSearchOrchestrator."""
        if self._multi_search is not None:
            return

        from src.rag.multi_search import MultiSearchOrchestrator
        from src.rag.file_search import grep_documents

        self._multi_search = MultiSearchOrchestrator(
            vector_search_fn=self._ms_vector_search,
            vector_search_vec_fn=self._ms_vector_search_vec,
            cloud_llm=self.cloud,
            embedder_fn=self.embedder.embed,
            grep_fn=grep_documents,
            get_doc_meta_fn=self.search_doc_meta,
        )

    # ── V12 Intégration mémoire V9 ──────────────────────────────────

    def _init_memory(self):
        """Initialisation paresseuse du MemoryManager V9.

        Appelée au premier besoin pour éviter de casser l'initialisation
        de RAGEngine si la base mémoire n'est pas encore disponible.
        """
        if self._memory is not None:
            return
        try:
            from src.memory.manager import MemoryManager
            self._memory = MemoryManager()
            logger.info("🧠 RAGEngine: MemoryManager V9 initialisé")
        except Exception as e:
            logger.warning("⚠️ RAGEngine: MemoryManager non disponible (%s)", e)
            self._memory = None

    @property
    def memory(self):
        """Accès paresseux au MemoryManager V9."""
        if self._memory is None:
            self._init_memory()
        return self._memory

    def _ms_vector_search(self, query: str, search_type: str = "vector") -> list:
        """Wrapper sync pour la recherche vectorielle/FTS (appelé par MultiSearchOrchestrator).

        Signature : fn(query, search_type='vector'|'fts') -> [(content, source, score)]
        """
        conn = self._get_conn()
        try:
            if search_type == "vector":
                if self._has_vec0:
                    # Embed la requête et chercher par vecteur
                    import sqlite_vec
                    embed = self.embedder.embed_sync(query, is_query=True)
                    # AUDIT V10.3k — B-Embed : le code testé `if not embed` sur np.ndarray 2D
                    # ce qui lève ValueError "truth value of array with more than one element
                    # is ambiguous" et fait silencieusement retomber _ms_vector_search à []
                    # → RAG vectoriel complètement cassé pour cet appel, sans message
                    # d'erreur clair.
                    # Fix : tester embed.size (méthode sûre np) au lieu de truthiness.
                    if embed is None or getattr(embed, 'size', 0) == 0 or len(embed) == 0:
                        return []
                    # embed est typiquement shape (1, 768) — index [0] est le vecteur
                    if embed.ndim >= 2:
                        qvec = sqlite_vec.serialize_float32(embed[0])
                    else:
                        qvec = sqlite_vec.serialize_float32(embed)
                    rows = conn.execute(
                        "SELECT content, source, 1 - distance as score FROM chunks "
                        "WHERE embedding MATCH ? ORDER BY distance LIMIT 15",
                        [qvec]
                    ).fetchall()
                    results = [(r[0], r[1], float(r[2])) for r in rows]
                else:
                    results = self._vector_search_numpy(query, conn)
            else:  # fts
                from src.query_rewriter import STOP_WORDS
                # `re` est importé au niveau module (ligne 7)
                words = [w for w in re.findall(r'\w{3,}', query.lower()) if w not in STOP_WORDS]
                if not words:
                    words = re.findall(r'\w{3,}', query.lower())
                fts_q = " OR ".join(f'"{w}"' for w in words)
                # V2.1 FIX : utiliser BM25 (colonne 'rank' FTS5) au lieu du score 1.0 factice.
                # rank FTS5 : négatif → plus négatif = meilleur match.
                # Conversion score = -rank / (1 + -rank) → [0, 0.95] pour matches, 0 sinon.
                try:
                    rows = conn.execute(
                        "SELECT content, source, rank FROM chunks_fts "
                        "WHERE content MATCH ? ORDER BY rank LIMIT 15",
                        [fts_q]
                    ).fetchall()
                except Exception:
                    # Fallback : rank indisponible → tri par rang
                    rows = conn.execute(
                        "SELECT content, source, 0.0 as score FROM chunks_fts "
                        "WHERE content MATCH ? LIMIT 15",
                        [fts_q]
                    ).fetchall()
                    results = [(r[0], r[1], max(0.0, 1.0 - i * 0.07)) for i, r in enumerate(rows)]
                    return results
                results = []
                for r in rows:
                    raw = float(r[2])
                    if raw < 0:
                        score = -raw / (1.0 + -raw)
                    else:
                        score = 0.0
                    results.append((r[0], r[1], score))
            return results
        except Exception as e:
            logger.warning(f"_ms_vector_search({search_type}) échoué — résultats vides: {e}")
            return []
        finally:
            conn.close()

    def _ms_vector_search_vec(self, qvec, top_k: int = 5) -> list:
        """Wrapper sync pour la recherche vectorielle à partir d'un vecteur
        (utilisé par HyDE dans MultiSearchOrchestrator).

        Signature : fn(qvec, top_k=N) -> [(content, source, score)]
        """
        if not self._has_vec0:
            return self._vector_search_numpy_vec(qvec, top_k)
        import sqlite_vec
        conn = self._get_conn()
        try:
            serialized = sqlite_vec.serialize_float32(qvec)
            rows = conn.execute(
                "SELECT content, source, 1 - distance as score FROM chunks "
                "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                [serialized, top_k]
            ).fetchall()
            return [(r[0], r[1], float(r[2])) for r in rows if r[0] and r[2] > 0]
        except Exception as e:
            logger.warning(f"_ms_vector_search_vec échoué (top_k={top_k}) — résultats vides: {e}")
            return []
        finally:
            conn.close()

    def _vector_search_numpy(self, query: str, conn) -> list:
        """V16+: Recherche vectorielle via numpy dot product (fallback sans sqlite-vec).

        Lit tous les vecteurs de chunk_vectors, calcule le cosinus en batch
        avec numpy (très rapide — ~15ms/1000 chunks sur M1 Accelerate).
        """
        import numpy as np
        embed = self.embedder.embed_sync(query, is_query=True)
        if embed is None or getattr(embed, 'size', 0) == 0 or len(embed) == 0:
            return []
        # Normaliser le vecteur requête
        qvec = np.asarray(embed[0] if embed.ndim >= 2 else embed, dtype=np.float32)
        qnorm = qvec / (np.linalg.norm(qvec) + 1e-12)
        dim = len(qvec)

        # Lire TOUS les vecteurs stockés
        rows = conn.execute(
            "SELECT content, source, embedding FROM chunk_vectors"
        ).fetchall()
        if not rows:
            return []

        # Construire la matrice (batch dot product)
        n = len(rows)
        matrix = np.frombuffer(
            b''.join(r[2] for r in rows), dtype=np.float32
        ).reshape(n, dim)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix_norm = matrix / (norms + 1e-12)

        # Cosinus = dot product sur vecteurs normalisés
        scores = matrix_norm @ qnorm  # (n,)

        # Top 15 (partition partielle O(n) au lieu de sort O(n log n))
        top_k = min(15, n)
        top_idx = np.argpartition(scores, -top_k)[-top_k:]
        top_idx = top_idx[np.argsort(scores[top_idx])[::-1]]

        return [(rows[i][0], rows[i][1], float(scores[i])) for i in top_idx]

    def _vector_search_numpy_vec(self, qvec, top_k: int = 5) -> list:
        """V16+: Recherche vectorielle à partir d'un vecteur (fallback numpy).

        Utilisé par HyDE dans MultiSearchOrchestrator.
        qvec est typiquement un ndarray shape (dim,) ou (1, dim).
        """
        import numpy as np
        q = np.asarray(qvec[0] if hasattr(qvec, 'ndim') and qvec.ndim >= 2 else qvec, dtype=np.float32)
        qnorm = q / (np.linalg.norm(q) + 1e-12)
        dim = len(q)

        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT content, source, embedding FROM chunk_vectors"
            ).fetchall()
            if not rows:
                return []
            n = len(rows)
            matrix = np.frombuffer(b''.join(r[2] for r in rows), dtype=np.float32).reshape(n, dim)
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            matrix_norm = matrix / (norms + 1e-12)
            scores = matrix_norm @ qnorm
            top = min(top_k, n)
            idx = np.argpartition(scores, -top)[-top:]
            idx = idx[np.argsort(scores[idx])[::-1]]
            return [(rows[i][0], rows[i][1], float(scores[i])) for i in idx]
        finally:
            conn.close()

    def _can_rerank(self, top1_score: float) -> bool:
        """V15 Phase 4 (Item 37) : Reranker SYSTÉMATIQUE.

        Supprime la gate RAM — le reranker est toujours activé dans le
        pipeline. Seule condition : un score minimal pour éviter de
        reranker du bruit.
        """
        if top1_score < 0.15:
            return False
        return True

    def _get_conn(self):
        """Ouvre une nouvelle connexion avec support sqlite-vec (Thread-safe).

        V8+ : Mode WAL activé pour supporter les accès concurrents 
        (multi-stratégie parallèle sans 'database is locked').
        V15+ : Fallback silencieux sur Python 3.13+ où enable_load_extension
        n'est pas disponible (FTS5 + BM25 seulement, pas de vectoriel).
        """
        conn = sqlite3.connect(str(self.db_path), timeout=20)
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
        except AttributeError:
            # Python 3.13+ : enable_load_extension désactivé dans le build
            # Fallback : FTS5 + BM25, pas de vectoriel
            pass
        # V8+ : WAL mode + synchronous NORMAL pour lectures concurrentes
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    @contextmanager
    def _conn_ctx(self):
        """Context manager garantissant la fermeture de la connexion SQLite."""
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        """Initialise la base de données SQLite avec l'extension vec0."""
        with self._conn_ctx() as conn:
            if self._has_vec0:
                conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING vec0(
                        embedding FLOAT[1024],
                        content TEXT,
                        source TEXT,
                        chunk_date TEXT
                    )
                """)
            # FTS5 pour BM25 (recherche par mots-clés)
            # V17.2: tokenizer 'unicode61 remove_diacritics' (français) au lieu de
            # 'porter' (stemmer ANGLAIS cassé sur le français — audit F-3)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    content, source, tokenize='unicode61 remove_diacritics 2'
                )
            """)
            # Migration one-shot : si l'index existant a été créé avec 'porter',
            # le reconstruire avec le tokenizer français (audit F-3)
            try:
                _row = conn.execute(
                    "SELECT sql FROM sqlite_master WHERE name='chunks_fts'"
                ).fetchone()
                if _row and "porter" in _row[0]:
                    conn.execute("ALTER TABLE chunks_fts RENAME TO chunks_fts_porter_old")
                    conn.execute("""
                        CREATE VIRTUAL TABLE chunks_fts USING fts5(
                            content, source, tokenize='unicode61 remove_diacritics 2'
                        )
                    """)
                    conn.execute(
                        "INSERT INTO chunks_fts(content, source) "
                        "SELECT content, source FROM chunks_fts_porter_old"
                    )
                    conn.execute("DROP TABLE chunks_fts_porter_old")
                    logger.info("🇫🇷 Migration FTS5 porter→unicode61 (français) effectuée")
            except Exception as e:
                logger.warning(f"⚠️ Migration FTS5 française ignorée: {e}")
            # Table de suivi des fichiers indexés
            conn.execute("""
                CREATE TABLE IF NOT EXISTS indexed_files (
                    filepath TEXT PRIMARY KEY,
                    mtime FLOAT,
                    hash TEXT
                )
            """)
            # V6 : Table Parent-Child pour remontée hiérarchique
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunk_hierarchy (
                    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT,
                    parent_id INTEGER DEFAULT NULL,
                    doc_summary TEXT DEFAULT '',
                    section_title TEXT DEFAULT '',
                    level TEXT DEFAULT 'section',
                    content TEXT,
                    FOREIGN KEY (parent_id) REFERENCES chunk_hierarchy(chunk_id)
                )
            """)
            # V6 : Table CV structuré (extraction LLM, pas de chunking vectoriel)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cv_structured (
                    source TEXT PRIMARY KEY,
                    file_hash TEXT,
                    json_data TEXT,
                    extracted_at TEXT
                )
            """)
            # V6 : Table métadonnées structurées pour TOUS les documents
            conn.execute("""
                CREATE TABLE IF NOT EXISTS doc_structured (
                    source TEXT PRIMARY KEY,
                    file_hash TEXT,
                    doc_type TEXT,
                    json_data TEXT,
                    extracted_at TEXT
                )
            """)
            # V10 : Table de correspondance source→rowid pour les DELETE sur vec0
            # (les VIRTUAL TABLE vec0 ne supportent pas DELETE WHERE source=?)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunk_rowids (
                    source TEXT,
                    rowid INTEGER UNIQUE
                )
            """)
            # V16+: Table de fallback vectoriel sans sqlite-vec (numpy dot product)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunk_vectors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    content TEXT,
                    chunk_date TEXT,
                    embedding BLOB
                )
            """)

    def is_file_up_to_date(self, filepath: str, mtime: float = 0, file_hash: str = "") -> bool:
        """Vérifie si le fichier a déjà été indexé avec le même hash SHA256 (V6.2).
        
        V6.2 : Vérifie d'abord par filepath, puis par hash global.
        Si le contenu existe déjà dans l'index (même hash à un autre chemin),
        on considère le fichier comme déjà indexé.
        """
        if not file_hash:
            return False
            
        with self._conn_ctx() as conn:
            # Défensif : créer la table si _init_db() ne l'a pas fait
            conn.execute("""
                CREATE TABLE IF NOT EXISTS indexed_files (
                    filepath TEXT PRIMARY KEY,
                    mtime FLOAT,
                    hash TEXT
                )
            """)
            # 1. Vérification par filepath (compatible )
            row = conn.execute(
                "SELECT hash FROM indexed_files WHERE filepath = ?", (filepath,)
            ).fetchone()
            
            if row and row[0] == file_hash:
                return True
            
            # 2. V6.2 : Vérification GLOBALE par hash (même contenu = déjà indexé)
            #    Indépendamment du chemin du fichier
            hash_row = conn.execute(
                "SELECT filepath FROM indexed_files WHERE hash = ? LIMIT 1", (file_hash,)
            ).fetchone()
            
            if hash_row:
                logger.info(f"🔄 Déduplication V6.2 : {os.path.basename(filepath)} déjà indexé "
                           f"sous {os.path.basename(hash_row[0])} (même hash SHA256)")
                return True
            
            return False

    def mark_file_indexed(self, filepath: str, mtime: float, file_hash: str = ""):
        """Enregistre un fichier comme indexé avec son hash SHA256 (V6.2).
        
        V6.2 : Si le hash existe déjà (même contenu ailleurs), on met à jour
        l'entrée existante au lieu d'en créer une nouvelle.
        Supprime aussi les entrées obsolètes pour le même filepath.
        """
        with self._conn_ctx() as conn:
            # Défensif : créer la table si _init_db() ne l'a pas fait
            conn.execute("""
                CREATE TABLE IF NOT EXISTS indexed_files (
                    filepath TEXT PRIMARY KEY,
                    mtime FLOAT,
                    hash TEXT
                )
            """)
            if file_hash:
                # V6.2 : Nettoyer les anciennes entrées pour ce hash (même contenu à d'autres chemins)
                conn.execute(
                    "DELETE FROM indexed_files WHERE hash = ? AND filepath != ?",
                    (file_hash, filepath)
                )
            conn.execute(
                "INSERT OR REPLACE INTO indexed_files (filepath, mtime, hash) VALUES (?, ?, ?)",
                (filepath, mtime, file_hash)
            )

    def dedup_indexed_files_by_hash(self):
        """V6.2 : Nettoie les doublons dans indexed_files (même hash, chemins différents).
        
        Pour chaque hash, ne garde que la première entrée.
        À appeler après une indexation complète ou lors du démarrage.
        """
        conn = self._get_conn()
        try:
            dups = conn.execute("""
                SELECT hash, COUNT(*) AS n
                FROM indexed_files
                GROUP BY hash
                HAVING n > 1
            """).fetchall()
            
            total_deleted = 0
            for hash_val, count in dups:
                first = conn.execute(
                    "SELECT filepath FROM indexed_files WHERE hash = ? ORDER BY filepath LIMIT 1",
                    (hash_val,)
                ).fetchone()
                if first:
                    deleted = conn.execute(
                        "DELETE FROM indexed_files WHERE hash = ? AND filepath != ?",
                        (hash_val, first[0])
                    ).rowcount
                    total_deleted += deleted
            
            conn.commit()
            if total_deleted > 0:
                logger.info(f"🧹 V6.2 : {total_deleted} entrées en double nettoyées dans indexed_files")
            return total_deleted
        except Exception as e:
            logger.warning(f"Erreur nettoyage indexed_files: {e}")
            return 0
        finally:
            conn.close()

    def remove_file_index(self, source_name: str):
        """Supprime tous les chunks associés à une source.

        V10.1 : timeout 30s + BEGIN IMMEDIATE + retry pour éviter
        "database is locked" quand le dashboard maintient une connexion.
        """
        for attempt in range(3):
            conn = sqlite3.connect(str(self.db_path), timeout=30)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=30000")
                conn.execute("BEGIN IMMEDIATE")
                # 1. Récupérer les rowid via la table de mapping
                rows = conn.execute(
                    "SELECT rowid FROM chunk_rowids WHERE source = ?", (source_name,)
                ).fetchall()
                for (rowid,) in rows:
                    conn.execute("DELETE FROM chunks WHERE rowid = ?", (rowid,))
                # 2. Nettoyer la table de mapping
                conn.execute("DELETE FROM chunk_rowids WHERE source = ?", (source_name,))
                # 3. Supprimer les entrées FTS
                try:
                    conn.execute("DELETE FROM chunks_fts WHERE source = ?", (source_name,))
                except Exception:
                    pass  # table peut ne pas exister
                conn.execute("COMMIT")
                logger.info(f"Supprimé {len(rows)} chunks pour {source_name}")
                return True
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < 2:
                    import time
                    logger.warning(f"DB verrouillée (tentative {attempt+1}), retry...")
                    time.sleep(2 * (attempt + 1))
                    continue
                logger.warning(f"Erreur suppression {source_name}: {e}")
                return False
            except Exception as e:
                logger.warning(f"Erreur suppression {source_name}: {e}")
                return False
            finally:
                conn.close()
        return False

    # ════════════════════════════════════════════
    # V6 : CV Structuré (extraction LLM directe)
    # ════════════════════════════════════════════
    def save_cv(self, source: str, file_hash: str, json_data: str):
        """Enregistre un CV structuré dans la table dédiée."""
        from datetime import datetime
        with self._conn_ctx() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cv_structured (source, file_hash, json_data, extracted_at) VALUES (?, ?, ?, ?)",
                (source, file_hash, json_data, datetime.now().isoformat())
            )
        logger.info(f"✅ CV structuré sauvegardé : {source}")

    def get_cv(self, source: str) -> Optional[str]:
        """Retourne le JSON d'un CV structuré par nom de source."""
        with self._conn_ctx() as conn:
            row = conn.execute(
                "SELECT json_data FROM cv_structured WHERE source = ?", (source,)
            ).fetchone()
        return row[0] if row else None

    def is_cv_indexed(self, source: str, file_hash: str = "") -> bool:
        """Vérifie si un CV est déjà indexé avec le même hash."""
        with self._conn_ctx() as conn:
            if file_hash:
                row = conn.execute(
                    "SELECT 1 FROM cv_structured WHERE source = ? AND file_hash = ?",
                    (source, file_hash)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT 1 FROM cv_structured WHERE source = ?",
                    (source,)
                ).fetchone()
        return row is not None

    def remove_cv(self, source: str):
        """Supprime un CV structuré de la table dédiée."""
        with self._conn_ctx() as conn:
            conn.execute("DELETE FROM cv_structured WHERE source = ?", (source,))
        logger.info(f"🗑️ CV supprimé : {source}")

    def get_all_cv_data(self) -> list[dict]:
        """Retourne tous les CVs structurés (source + json_data)."""
        with self._conn_ctx() as conn:
            rows = conn.execute(
                "SELECT source, json_data FROM cv_structured ORDER BY source"
            ).fetchall()
        return [{"source": r[0], "json_data": r[1]} for r in rows]

    # ════════════════════════════════════════════
    # V6 : Métadonnées structurées (tous documents)
    # ════════════════════════════════════════════

    def save_doc_meta(self, source: str, file_hash: str, doc_type: str, json_data: str):
        """Enregistre les métadonnées structurées d'un document."""
        from datetime import datetime
        with self._conn_ctx() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO doc_structured (source, file_hash, doc_type, json_data, extracted_at) VALUES (?, ?, ?, ?, ?)",
                (source, file_hash, doc_type, json_data, datetime.now().isoformat())
            )
        logger.info(f"📄 Métadonnées sauvegardées : {source} ({doc_type})")

    def get_doc_meta(self, source: str) -> Optional[str]:
        """Retourne le JSON des métadonnées d'un document."""
        with self._conn_ctx() as conn:
            row = conn.execute(
                "SELECT json_data FROM doc_structured WHERE source = ?", (source,)
            ).fetchone()
        return row[0] if row else None

    def is_doc_indexed(self, source: str, file_hash: str = "") -> bool:
        """Vérifie si un document a déjà ses métadonnées structurées."""
        with self._conn_ctx() as conn:
            if file_hash:
                row = conn.execute(
                    "SELECT 1 FROM doc_structured WHERE source = ? AND file_hash = ?",
                    (source, file_hash)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT 1 FROM doc_structured WHERE source = ?", (source,)
                ).fetchone()
        return row is not None

    def get_all_doc_meta(self, doc_type: str = "") -> list[dict]:
        """Retourne toutes les métadonnées structurées, filtrées par type si demandé."""
        with self._conn_ctx() as conn:
            if doc_type:
                rows = conn.execute(
                    "SELECT source, doc_type, json_data FROM doc_structured WHERE doc_type = ? ORDER BY source",
                    (doc_type,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT source, doc_type, json_data FROM doc_structured ORDER BY source"
                ).fetchall()
        return [{"source": r[0], "doc_type": r[1], "json_data": r[2]} for r in rows]

    def search_doc_meta(self, keyword: str) -> list[dict]:
        """Recherche textuelle dans les métadonnées structurées (FTS-like simple)."""
        with self._conn_ctx() as conn:
            like = f"%{keyword}%"
            rows = conn.execute(
                "SELECT source, doc_type, json_data FROM doc_structured "
                "WHERE source LIKE ? OR json_data LIKE ? ORDER BY source",
                (like, like)
            ).fetchall()
        return [{"source": r[0], "doc_type": r[1], "json_data": r[2]} for r in rows]

    def remove_doc_meta(self, source: str):
        """Supprime les métadonnées structurées d'un document."""
        with self._conn_ctx() as conn:
            conn.execute("DELETE FROM doc_structured WHERE source = ?", (source,))
        logger.info(f"🗑️ Métadonnées supprimées : {source}")

    async def retrieve(self, query: str, k: int = None) -> Tuple[str, RAGResult]:
        '''Recherche hybride avec confidence gate dynamique V8+.
        Retourne (contexte_formaté, RAGResult) pour le dashboard.'''
        t_start = time.time()

        # V10.2 PromptGuard : Sanitization anti-injection
        raw_query = query
        query = sanitize_rag_query(query)
        if query != raw_query:
            logger.info(f'🔒 PromptGuard: requête sanitizée ({len(raw_query)}→{len(query)} chars)')

        if k is None:
            k = config.rag_k

        result = RAGResult(top_k_configured=k, query_rewritten="")

        # V8+ : Diagnostic RAG temps réel
        from src.rag.diagnostics import RAGDiagnostic
        diag = RAGDiagnostic(query=query[:200])
        diag.start()

        # 1. Optimisation de la requête (synonymes + LLM Cloud)
        optimized_query = self.rewriter.rewrite(query)
        result.query_rewritten = optimized_query

        # 2. V8+ P2 : MultiSearch orchestrateur — source unique de recherche documentaire
        self._ensure_multi_search()
        ms_results, ms_diag = await self._multi_search.search(
            query=query,
            rewritten_query=optimized_query,
            top_k=k * 2,               # surplus pour que le reranker ait de la matière
        )

        result.chunks_retrieved = len(ms_results)

        # Log des stratégies multi_search dans le diagnostic RAG
        for strat in ms_diag.strategies_tried:
            count = ms_diag.results_per_strategy.get(strat, 0)
            diag.log_strategy(strat, count, 0.0, count > 0, 0)

        if not ms_results:
            result.confidence_label = "ABSENT"  # V10.2: forcer ABSENT sur recherche vide
            diag.set_verdict("VIDE (aucun résultat)")
            diag.stop()
            result.diagnostic = diag.to_dict()
            result.retrieval_time_ms = (time.time() - t_start) * 1000
            return "", result

        # ── V8+ : SCORE GATE DYNAMIQUE (3 niveaux) ===
        # V16+ FIX: utiliser le raw_score (similarité vectorielle/BM25 brute) pour la 
        # porte de confiance, PAS le score RRF normalisé qui est arbitrairement bas
        # (RRF normalise par le nombre de stratégies — un excellent résultat donne 0.07)
        top1_raw = max(r.raw_score for r in ms_results) if any(r.raw_score > 0 for r in ms_results) else 0.0
        top1_score = max(top1_raw, ms_results[0].score) if top1_raw > ms_results[0].score else ms_results[0].score
        self.last_top_score = top1_score
        result.top_score = top1_score
        result.all_scores = [r.score for r in ms_results]

        # V16 FIX: Seuils abaissés pour M1 8Go + embeddings locaux (bge-small, etc.)
        # Les scores cosinus sur petits modèles sont plus bas mais pertinents
        MIN_ABSOLUTE_SCORE = 0.22   # Était 0.30 - abaissé pour ne pas jeter le pertinent
        FALLBACK_THRESHOLD = 0.18   # Était 0.25
        RAG_MIN_USABLE_SCORE = 0.12 # Était 0.20 - seuil plancher absolue

        if top1_score >= MIN_ABSOLUTE_SCORE:
            confidence_label = "HAUTE"
            effective_k = k
        elif top1_score >= FALLBACK_THRESHOLD:
            confidence_label = "MOYENNE"
            # V16 FIX : plus de chunks quand confiance moyenne (inversé)
            effective_k = min(k * 2, k * 3 // 2)
            logger.info(
                f"RAG V8+ : confiance MOYENNE (score={top1_score:.2f}), "
                f"top_k élargi à {effective_k}"
            )
        else:
            confidence_label = "FAIBLE"
            # V16 FIX : 2× plus de chunks quand confiance faible (inversé)
            effective_k = k * 2
            logger.info(
                f"RAG V8+ : confiance FAIBLE (score={top1_score:.2f}), "
                f"top_k élargi à {effective_k}"
            )

        # ── V10 Audit: Rejeter les résultats clairement non pertinents ──
        # AVERTISSEMENT: placée APRES Profile Boost (ligne ~620), pas ici.
        # Les résultats bruts ms_results ne sont pas encore boostés.

        # Convertir SearchResult → tuples (content, source, score) pour post-processing
        # V16 FIX : utiliser raw_score (similarité cosinus réelle) et non r.score
        # (RRF normalisé ~0.07). Le RRF normalisé écrasait artificiellement les scores
        # et faisait rejeter des chunks valides par le reranker + BM25.
        combined_results = [(r.content, r.source, r.raw_score) for r in ms_results]

        # Profile Boost (V8+ P2 : freshness bonus supprimé — pas de chunk_date depuis multi_search)
        # Déduplication simple (tous les fichiers ont la même importance)
        seen_contents = set()
        source_counts = {}
        deduped_results = []

        for content, source, score in combined_results:
            if content not in seen_contents:
                count = source_counts.get(source, 0)
                if count < 5:  # V16 AUDIT FIX QW17 : 2→5 chunks/source (perte info documents multi-pages)
                    deduped_results.append((content, source, score))
                    source_counts[source] = count + 1
                    seen_contents.add(content)

        combined_results = deduped_results

        # ── V10 Audit: Rejeter les résultats non pertinents ──
        # Vérifie si le top résultat contient des mots-clés de la requête.
        # V17: paramétrable via config.rag_keyword_rejection (defaut: True)
        ENABLE_KEYWORD_REJECTION = getattr(config, "rag_keyword_rejection", True)
        
        if ENABLE_KEYWORD_REJECTION and combined_results:
            query_keywords = set(
                w.lower() for w in re.findall(r'\w+', query)
                if len(w) > 2 and w.lower() not in {
                    'de', 'la', 'le', 'les', 'du', 'des', 'un', 'une', 'et', 'ou',
                    'est', 'sont', 'dans', 'sur', 'par', 'pour', 'avec', 'que', 'qui',
                    'parle', 'moi', 'peux', 'tu', 'je', 'ne', 'pas', 'the', 'a', 'an',
                }
            )
            should_reject = False
            rejection_reason = ""

            # Règle 1: Score trop bas
            if top1_score < RAG_MIN_USABLE_SCORE:
                should_reject = True
                rejection_reason = f"score insuffisant ({top1_score:.2f} < {RAG_MIN_USABLE_SCORE})"

            # Règle 2: Aucun mot-clé dans le TOP résultat boosté
            # V17: seuil de correspondance relevé de 30% → 50%
            if not should_reject and query_keywords:
                found_relevant = False
                for rank, (top_content, top_source, _) in enumerate(combined_results[:3]):
                    top_text = (top_content + " " + top_source).lower()
                    keyword_matches = sum(1 for kw in query_keywords if kw in top_text)
                    if keyword_matches >= max(1, len(query_keywords) * 0.5):
                        found_relevant = True
                        break
                if not found_relevant:
                    should_reject = True
                    rejection_reason = (
                        f"hors-sujet: aucun des 3 premiers chunks ne contient "
                        f"les mots-clés de la requête"
                    )

            if should_reject:
                logger.warning(f"RAG V10: rejet — {rejection_reason}")
                result.confidence_label = confidence_label
                result.rejection_reason = rejection_reason
                result.diagnostic = {"rejected": True, "reason": rejection_reason}
                result.retrieval_time_ms = (time.time() - t_start) * 1000
                return "", result

        # ── V17 Hybrid Scoring: Blend RRF + Reranker ─────────────
        # Sauvegarder les scores RRF avant de les remplacer par le reranker
        rrf_score_map: dict[str, float] = {}
        for content, source, score in combined_results:
            rrf_score_map[content] = score

        #  Phase 0 : Reranker SYSTÉMATIQUE
        # V15 Phase 4 (Item 37) : toujours activé dans le pipeline.
        # V15 Phase 5 (Item 40) : vérification budget RAM avant chargement.
        should_rerank = self._can_rerank(top1_score)
        reranked: list = []
        
        if should_rerank:
            budget = get_budget()
            # V16 FIX : Skip reranker si swap > 50% (M1 8 Go — thrashing évité)
            probe = budget.probe()
            if probe.swap_percent > 80:
                logger.info(
                    f"⏭️ Reranker sauté : swap {probe.swap_percent:.0f}% > 80% → BM25 direct"
                )
                should_rerank = False
            # Vérifier si on peut charger le reranker dans le budget
            elif not budget.can_load("reranker"):
                logger.warning(
                    "⏭️ Reranker sauté : budget RAM insuffisant "
                    f"(swap {budget.probe().swap_percent:.0f}%)"
                )
                budget.evict(priority_below=Priority.CACHE)
            else:
                # V16 AUDIT FIX (QW15) : Ne plus décharger l'embedder systématiquement.
                # L'unload causait un rechargement (2-3s) à la prochaine requête.
                budget.mark_loaded("reranker")

                try:
                    self.reranker.load_model()
                    reranked = await self.reranker.rerank(query, combined_results, top_k=effective_k) or []
                    # V17: Blend RRF (80%) + Reranker (20%) — le Cross-Encoder est
                    # ms-marco (anglais) → scores degrades sur le français. Le RRF
                    # (embedder multilingue + BM25) est plus fiable en FR.
                    if reranked:
                        blended = []
                        for content, source, score in reranked:
                            rrf_score = rrf_score_map.get(content, 0.0)
                            blended_score = 0.80 * rrf_score + 0.20 * min(score, 1.0)
                            blended.append((content, source, blended_score))
                        reranked = blended
                finally:
                    # V16 AUDIT FIX QW16 : Garder le cross-encoder chargé entre requêtes
                    # pour éviter les 5-15s de chargement à chaque appel RAG.
                    # Le déchargement est géré par :
                    # 1. RAMMonitor → clear_reranker() si RAM critique
                    # 2. Schedule_unload timer (120s d'inactivité)
                    # self.reranker.unload()  ← supprimé
                    # budget.mark_unloaded("reranker")  ← supprimé
                    self._schedule_reranker_unload()
        
        # Fallback BM25 si reranker non disponible ou désactivé
        if not reranked and combined_results:
            if not should_rerank:
                logger.info("↪️ Utilisation BM25 direct (pas de reranker).")
            else:
                logger.warning("⚠️ Fallback: reranker vide, utilisation BM25 à la place.")
            reranked = self.bm25_rerank(query, combined_results, top_k=effective_k)
        
        # Seconde confidence gate APRÈS reranking (uniquement si reranker a été utilisé)
        if should_rerank and reranked and reranked[0][2] < 0.10:
            logger.warning(f"🗑️ Tous les chunks rejetés par reranker (top1={reranked[0][2]:.2f})")
            if top1_score >= 0.35:
                logger.info("↪️ Fallback BM25 pour éviter un rejet injustifié.")
                reranked = self.bm25_rerank(query, combined_results, top_k=3)
        
        # V15 #39 : Small-to-Big — expandre les chunks trop courts avec le contexte parent
        if reranked:
            expanded = []
            for content, source, score in reranked:
                if len(content) < 2000:
                    parent = self._fetch_parent_context(source, content)
                    if parent and parent != content:
                        logger.debug(f"↗️ Small-to-Big: {source} ({len(content)}→{len(parent)} chars)")
                        content = parent
                expanded.append((content, source, score))
            reranked = expanded
        
        result.chunks_injected = len(reranked)
        result.top_k_actual = len(reranked)
        # V10.1 : Utiliser le score du reranker (pas le RRF normalisé)
        if reranked:
            result.top_score = max(r[2] for r in reranked)
            result.all_scores = [r[2] for r in reranked]
            self.last_top_score = result.top_score
            # Recalculer le confidence_label avec le vrai score reranké
            if result.top_score >= 0.7:
                confidence_label = "HAUTE"
            elif result.top_score >= 0.4:
                confidence_label = "MOYENNE"
            else:
                confidence_label = "FAIBLE"
        # V8+ : Propager le niveau de confiance
        result.confidence_label = confidence_label

        # Build sources list
        source_list = []
        for content, source, score in reranked:
            source_list.append({
                "name": source,
                "score": round(score, 2),
                "ext": source.rsplit(".", 1)[-1].upper() if "." in source else "TXT",
                "preview": content[:150],
            })
        result.sources = source_list
        result.documents_found = len(set(s["name"] for s in source_list))

        # V17.2: Boost CV identité sur l'ORDRE FINAL (après reranking) — les
        # questions d'identité doivent mettre le CV en tête du contexte.
        _is_identity_q = ("qui est" in query.lower()) or (
            "son " in query.lower() or "sa " in query.lower() or "ses " in query.lower()
        )
        if _is_identity_q and reranked:
            _CV_MARKERS = ("cv", "curriculum", "vitae", "profil", "biograph", "mudarhi", "bahiga")
            _cv_list = []
            _other_list = []
            for _item in reranked:
                _src = _item[1].lower()
                if any(m in _src for m in _CV_MARKERS):
                    _cv_list.append(_item)
                else:
                    _other_list.append(_item)
            if _cv_list:
                reranked = _cv_list + _other_list
                logger.info("🧑‍🌾 Boost CV (ordre final): %d source(s) CV en tête", len(_cv_list))

        context = self._format_context(reranked)
        # V8+ : En-tête de confiance dans le contexte — TOUJOURS présent
        confidence_header = (
            f"[CONFIANCE RAG: {confidence_label}] "
        )
        if not context.strip() or "[AUCUNE SOURCE]" in context:
            context = confidence_header + "Aucun document pertinent trouvé dans l'index."
        else:
            context = confidence_header + "\n" + context

        # V17: mémoire NON injectée dans le contexte RAG (contaminait les réponses
        # avec des souvenirs/instructions/fragments précédents). La mémoire est
        # gérée séparément par BuildContext → prompt_builder.)

        result.tokens_injected = len(context) // 4
        result.retrieval_time_ms = (time.time() - t_start) * 1000

        # V6 : Injection des métadonnées structurées dans le contexte
        # V16 FIX : Filtrer par sources présentes dans les résultats de recherche
        try:
            from src.document_extractor import DocumentMetadata, format_doc_for_context

            # Récupérer UNIQUEMENT les métadonnées des documents trouvés par la recherche
            relevant_sources = set()
            if combined_results:
                for _, src, _ in combined_results:
                    if src:
                        relevant_sources.add(src)

            injected = 0
            meta_sections = []
            if relevant_sources:
                for source in relevant_sources:
                    try:
                        json_str = self.get_doc_meta(source)
                        if not json_str:
                            continue
                        data = json.loads(json_str)
                        meta = DocumentMetadata(
                            source_file=source,
                            doc_type=data.get("doc_type", "document"),
                            title=data.get("title", ""),
                            summary=data.get("summary", ""),
                            key_topics=data.get("key_topics", []),
                            entities=data.get("entities", []),
                            dates_mentioned=data.get("dates_mentioned", []),
                            language=data.get("language", ""),
                            word_count=data.get("word_count", 0),
                        )
                        meta.structured_json = json_str
                        meta_sections.append(format_doc_for_context(meta))
                        injected += 1
                    except Exception as e:
                        logger.debug(f"Formatage métadonnées ignoré: {e}")
                        pass

            if meta_sections:
                    meta_context = "\n\n===\n".join(meta_sections)
                    # Ajouter un marqueur clair pour le LLM
                    meta_block = "\n\n=== FICHES STRUCTURÉES DES DOCUMENTS ===\n" + meta_context
                    context += meta_block
                    result.tokens_injected += len(meta_block) // 4
                    result.sources.append({
                        "name": "METADATA",
                        "score": 1.0,
                        "ext": "STRUCTURED",
                        "preview": f"{injected} fiche(s) structurée(s)",
                    })
                    logger.info(f"📋 {injected} fiche(s) structurée(s) injectée(s)")
        except Exception as e:
            logger.debug(f"Injection métadonnées ignorée (première fois ou vide) : {e}")

        # V8+ : Finaliser le diagnostic et l'attacher au résultat
        diag.set_verdict(
            f"{'✅' if context else '❌'} "
            f"{'contexte injecté' if context else 'recherche vide'}"
        )
        diag.stop()
        result.diagnostic = diag.to_dict()

        return context, result

    def _search_db(self, qvec: bytes, fts_query: str) -> Tuple:
        """Exécute les recherches vectorielle et FTS dans un thread séparé."""
        try:
            conn = self._get_conn()
            
            # Phase 0 : top_k réduit de 30 à 15 (moins de bruit, plus rapide)
            # V6.1 : on récupère aussi chunk_date pour le freshness bonus
            vec_results = conn.execute("""\
                SELECT content, source, distance, chunk_date
                FROM chunks
                WHERE embedding MATCH ?
                ORDER BY distance
                LIMIT 15
            """, [qvec]).fetchall()
            
            fts_results = []
            if fts_query:
                try:
                    fts_results = conn.execute("""\
                        SELECT content, source, 1.0 as distance, '' as chunk_date
                        FROM chunks_fts
                        WHERE content MATCH ?
                        LIMIT 15
                    """, [fts_query]).fetchall()
                except sqlite3.OperationalError:
                    pass
            
            return vec_results, fts_results
        finally:
            conn.close()

    def bm25_rerank(self, query: str, results: List[Tuple], top_k: int = 5) -> List[Tuple]:
        """BM25 simplifié — Zéro dépendance externe, avec filtrage de stop words et bonus source."""
        # re importé au niveau module (ligne 7)
        STOP_WORDS = {
            # French
            "de", "la", "le", "les", "est", "un", "une", "en", "que", "qui", "dans", "par", "pour", "sur", "avec", "du", "des", 
            "se", "ses", "sa", "son", "ce", "cette", "ces", "et", "ou", "mais", "donc", "car", "ni", "ne", "pas", "plus", "aux", 
            "au", "combien", "comment", "quel", "quelle", "quels", "quelles", "sans", "sous", "parce", "alors", "tout", "tous", 
            "toute", "toutes", "fait", "faire", "suis", "es", "sommes", "etes", "sont", "avoir", "etre", "a", "l", "d", "qu", "c",
            # English
            "the", "a", "an", "and", "or", "but", "for", "with", "in", "on", "at", "of", "to", "is", "are", "was", "were", "this", "that"
        }
        
        query_terms = [t for t in re.findall(r'\w+', query.lower()) if t not in STOP_WORDS]
        if not query_terms:
            query_terms = re.findall(r'\w+', query.lower())
            
        scored = []
        for content, source, vec_dist in results:
            # Ignorer les fichiers de cache système
            if source.lower() == "indexed_hashes.json":
                continue
                
            content_lower = content.lower()
            # Score basé sur la fréquence des termes de recherche importants
            bm25 = sum(content_lower.count(t) for t in query_terms)
            bm25_norm = min(bm25 / 10.0, 1.0)
            
            # Bonus si le nom de la source contient un des termes importants (ex: "CV", "Leblanc")
            source_lower = source.lower()
            source_bonus = 0.0
            if any(t in source_lower for t in query_terms):
                source_bonus = 0.15
                
            # Combinaison : 60% sémantique, 40% mots-clés + bonus source
            # V16 FIX : vec_dist est une similarité (plus grand = mieux),
            # PAS une distance. Utiliser (1-vec_dist) était un bug qui
            # inversait le score (pénalisait les meilleurs chunks).
            final_score = 0.6 * vec_dist + 0.4 * bm25_norm + source_bonus
            scored.append((content, source, min(final_score, 1.0)))
            
        # Trier par score décroissant
        return sorted(scored, key=lambda x: -x[2])[:top_k]

    def _format_context(self, results: List[Tuple]) -> str:
        '''Formate les résultats avec marqueurs CONTEXTE clairs pour forcer le grounding.'''
        context_parts = []
        for i, (content, source, score) in enumerate(results, 1):
            # V16 AUDIT FIX QW19 : ajouter section_title/level si disponibles
            meta = self._get_chunk_metadata(source, content)
            section_info = ""
            if meta:
                title = meta.get("section_title", "")
                level = meta.get("level", "")
                if title:
                    section_info = f" [{level}] {title}"
            context_parts.append(
                f"[SOURCE {i}] {source}{section_info}\n"
                f"{sanitize_chunk_content(content)}\n"
            )
        return "=== DÉBUT DU CONTEXTE ===\n" + "\n".join(context_parts) + "\n=== FIN DU CONTEXTE ==="

    def _get_chunk_metadata(self, source: str, content: str) -> Optional[dict]:
        """Récupère section_title/level depuis chunk_hierarchy pour un chunk.
        V16 AUDIT FIX QW19.
        """
        try:
            conn = self._get_conn()
            row = conn.execute(
                """SELECT section_title, level FROM chunk_hierarchy
                   WHERE source = ? AND content = ? LIMIT 1""",
                (source, content[:1000])
            ).fetchone()
            if row and (row[0] or row[1]):
                return {"section_title": row[0] or "", "level": row[1] or ""}
        except Exception:
            pass
        return None

    def add_chunks(self, chunks: List[dict], dedup_source: bool = True):
        """Ajoute des chunks à l'index vectoriel et FTS (V6.2 : avec déduplication).
        
        V6.2 : Avant d'insérer, supprime les anciens chunks de la même source
        pour éviter les doublons. Utilise dedup_source=False pour ajouter
        sans supprimer (usage interne).

        V10 : Utilise la table chunk_rowids car les VIRTUAL TABLE vec0
        ne supportent pas DELETE WHERE source = ? ni SELECT COUNT(*) FROM chunks WHERE source = ?.
        """
        if not chunks:
            return
            
        source_name = chunks[0].get("source", "")
        try:
            conn = self._get_conn()

            # V10 : Supprimer les anciens chunks via la table de mapping rowid
            if dedup_source and source_name:
                # Défensif : créer la table si _init_db() ne l'a pas fait
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS chunk_rowids (
                        source TEXT,
                        rowid INTEGER UNIQUE
                    )
                """)
                old_rows = conn.execute(
                    "SELECT rowid FROM chunk_rowids WHERE source = ?", (source_name,)
                ).fetchall()
                old_count = len(old_rows)
                if old_count > 0:
                    if self._has_vec0:
                        for (rowid,) in old_rows:
                            conn.execute("DELETE FROM chunks WHERE rowid = ?", (rowid,))
                    else:
                        conn.execute("DELETE FROM chunk_vectors WHERE source = ?", (source_name,))
                    conn.execute("DELETE FROM chunk_rowids WHERE source = ?", (source_name,))
                    conn.execute("DELETE FROM chunks_fts WHERE source = ?", (source_name,))
                    logger.info(f"🔄 V10 Déduplication : {old_count} anciens chunks de '{source_name}' remplacés")
            
            for chunk in chunks:
                # V6.1 : date par défaut = aujourd'hui
                chunk_date = chunk.get("date", "") or datetime.now().strftime("%Y-%m-%d")
                if self._has_vec0:
                    # Insertion Vectorielle — récupérer le rowid pour le mapping
                    cur = conn.execute(
                        "INSERT INTO chunks(embedding, content, source, chunk_date) VALUES (?, ?, ?, ?)",
                        [sqlite_vec.serialize_float32(chunk["embedding"]), chunk["content"], chunk["source"], chunk_date]
                    )
                    # V10 : Stocker la correspondance source → rowid
                    chunk_rowid = cur.lastrowid
                    conn.execute(
                        "INSERT INTO chunk_rowids(source, rowid) VALUES (?, ?)",
                        [chunk["source"], chunk_rowid]
                    )
                else:
                    # V16+: Fallback chunk_vectors (numpy, pas de sqlite-vec)
                    import numpy as np
                    emb = np.asarray(chunk["embedding"], dtype=np.float32)
                    conn.execute(
                        "INSERT INTO chunk_vectors(source, content, chunk_date, embedding) VALUES (?, ?, ?, ?)",
                        [chunk["source"], chunk["content"], chunk_date, emb.tobytes()]
                    )
                # Insertion FTS
                conn.execute(
                    "INSERT INTO chunks_fts(content, source) VALUES (?, ?)",
                    [chunk["content"], chunk["source"]]
                )
            
            # V15 #39 : Small-to-Big — stocker la hiérarchie des sections
            prev_section_id = {}
            for chunk in chunks:
                level = chunk.get("level", "section")
                source = chunk["source"]
                section_title = chunk.get("title", "")
                cur_hi = conn.execute(
                    """INSERT INTO chunk_hierarchy 
                       (source, parent_id, doc_summary, section_title, level, content) 
                       VALUES (?, ?, NULL, ?, ?, ?)""",
                    [source, prev_section_id.get(source),
                     section_title, level, chunk["content"]]
                )
                if level in ("document", "section"):
                    prev_section_id[source] = cur_hi.lastrowid
            
            conn.commit()
        except Exception:
            logger.exception(f"Erreur insertion chunks pour {source_name}")
            raise
        finally:
            conn.close()
        logger.info(f"{len(chunks)} chunks ajoutés à l'index (source: {source_name}).")

    def add_chunks_with_parents(self, chunks: List[dict], doc_summary: str = ""):
        """V6 : Ajoute des chunks avec hiérarchie Parent-Child.
        
        Chaque chunk peut avoir un parent_id. Lors du retrieval, si un enfant
        match, on remonte au parent pour fournir un contexte complet.

        V10 : Stocke les rowid vec0 dans chunk_rowids pour permettre les suppressions.
        """
        if not chunks:
            return
        try:
            conn = self._get_conn()
            
            for chunk in chunks:
                level = chunk.get("level", "section")
                
                # Insérer dans la table hiérarchique
                cur = conn.execute(
                    """INSERT INTO chunk_hierarchy 
                       (source, parent_id, doc_summary, section_title, level, content) 
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    [
                        chunk["source"],
                        chunk.get("parent_id"),
                        doc_summary,
                        chunk.get("title", ""),
                        level,
                        chunk["content"],
                    ]
                )
                chunk_id = cur.lastrowid
                
                # Si c'est un document/résumé (pas de parent), c'est le parent de référence
                if level in ("document", "section") and not chunk.get("parent_id"):
                    chunk["chunk_hierarchy_id"] = chunk_id
                
                # V6.1 : date par défaut = aujourd'hui
                chunk_date = chunk.get("date", "") or datetime.now().strftime("%Y-%m-%d")
                if self._has_vec0:
                    # Insertion Vectorielle — récupérer le rowid pour le mapping
                    cur_vec = conn.execute(
                        "INSERT INTO chunks(embedding, content, source, chunk_date) VALUES (?, ?, ?, ?)",
                        [sqlite_vec.serialize_float32(chunk["embedding"]), chunk["content"], chunk["source"], chunk_date]
                    )
                    # V10 : Stocker la correspondance source → rowid
                    chunk_rowid = cur_vec.lastrowid
                    conn.execute(
                        "INSERT INTO chunk_rowids(source, rowid) VALUES (?, ?)",
                        [chunk["source"], chunk_rowid]
                    )
                else:
                    import numpy as np
                    emb = np.asarray(chunk["embedding"], dtype=np.float32)
                    conn.execute(
                        "INSERT INTO chunk_vectors(source, content, chunk_date, embedding) VALUES (?, ?, ?, ?)",
                        [chunk["source"], chunk["content"], chunk_date, emb.tobytes()]
                    )
                # Insertion FTS
                conn.execute(
                    "INSERT INTO chunks_fts(content, source) VALUES (?, ?)",
                    [chunk["content"], chunk["source"]]
                )
            
            conn.commit()
        except Exception:
            logger.exception("Erreur insertion chunks avec hiérarchie")
            raise
        finally:
            conn.close()
        logger.info(f"{len(chunks)} chunks (avec hiérarchie) ajoutés à l'index.")

    def _fetch_parent_context(self, source: str, chunk_text: str) -> str:
        """V6 + V15 #39 : Remonte au parent d'un chunk pour enrichir le contexte.
        
        Si le chunk actuel est trop court (< 2000 chars), on fetch
        la section parente (ou le résumé document) pour donner
        plus de contexte au LLM (Small-to-Big).
        """
        if len(chunk_text) > 2000:
            return chunk_text  # Déjà assez long
        
        try:
            # V15 #39 : chercher un parent via la hiérarchie stockée
            with self._conn_ctx() as conn:
                parent = conn.execute(
                    """SELECT content FROM chunk_hierarchy 
                       WHERE source = ? AND level IN ('document', 'section')
                       AND LENGTH(content) > 1000
                       ORDER BY LENGTH(content) DESC LIMIT 1""",
                    (source,)
                ).fetchone()
            if parent and parent[0] != chunk_text:
                return parent[0]
        except Exception as e:
            logger.debug(f"⚠️ _fetch_parent_context: {e}")

        return chunk_text
    
    def clear_reranker(self, force: bool = False):
        """Décharge le reranker cross-encoder pour libérer la RAM.
        Connecté au RAMBudgetManager en cas de mémoire critique.
        V17 FIX : guard — skip si déjà déchargé (évite le spam log).
        """
        if not self.reranker or not getattr(self.reranker, '_loaded', False):
            return
        self.reranker.unload()
        self._reranker_unload_timer = None
        logger.info("🧹 Reranker cross-encoder déchargé (RAMBudgetManager).")

    def _schedule_reranker_unload(self):
        """Planifie le déchargement du reranker après 120s d'inactivité.
        V16 AUDIT FIX QW16 : garde le modèle chaud entre les requêtes RAG.
        """
        import asyncio
        # Annuler le timer précédent s'il existe
        try:
            if hasattr(self, '_reranker_unload_timer') and self._reranker_unload_timer is not None:
                self._reranker_unload_timer.cancel()
        except Exception:
            pass

        async def _do_unload():
            try:
                await asyncio.sleep(120)  # 120s d'inactivité
                if hasattr(self, 'reranker') and self.reranker:
                    self.reranker.unload()
                    logger.info("🧹 Reranker déchargé après 120s d'inactivité.")
            except asyncio.CancelledError:
                pass  # Timer annulé → nouveau RAG request

        self._reranker_unload_timer = asyncio.ensure_future(_do_unload())
