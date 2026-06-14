# NURU V5 : pysqlite3 avec support d'extensions (nécessaire pour sqlite-vec sur macOS)
try:
    import pysqlite3 as sqlite3
except ImportError:
    import sqlite3  # fallback standard (sans support extensions)
    import logging
    logging.getLogger(__name__).warning("pysqlite3-binary non trouvé, utilisation sqlite3 standard (extensions désactivées)")
import sqlite_vec
import asyncio
import logging
import os
import re
import json
import time
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
from dataclasses import dataclass, field
from pathlib import Path
from src.config import config
from src.embedder import Embedder
from src.rag.query_rewriter import CloudQueryRewriter
from src.reranker import CrossEncoderReranker
from src.llm_cloud import CloudLLM

logger = logging.getLogger(__name__)


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

    # 2. Échappement des délimiteurs de contexte RAG
    query = query.replace("===", "(triple égal)")

    # 3. Échappement des blocs de code (empêche la fermeture prématurée du format)
    query = query.replace("```", "(code block)")

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
    embedding_model: str = "multilingual-e5-base-mlx"
    top_k_configured: int = 5
    top_k_actual: int = 0
    tokens_injected: int = 0
    diagnostic: Optional[dict] = None  # V8+ : RAGDiagnostic sérialisé
    confidence_label: str = "HAUTE"  # V8+ : HAUTE | MOYENNE | FAIBLE | ABSENT

class RAGEngine:
    """Moteur RAG Hybride : Recherche sémantique (sqlite-vec) + BM25."""
    
    def __init__(self):
        self.db_path = config.index_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = Embedder()
        self.cloud = CloudLLM()  # Cloud LLM pour l'expansion de requête
        self.rewriter = CloudQueryRewriter(cloud_llm=self.cloud)
        self.reranker = CrossEncoderReranker()  # V4 : Reranker sémantique
        self.reranker.set_embedder(self.embedder)  # Connecte l'embedder
        self.last_top_score = 0.0
        self._init_db()
        # V4.5 Phase 0 : seuils configurés pour reranker conditionnel
        self._rerank_min_score = 0.40   # En dessous : pas la peine
        self._rerank_max_score = 0.75   # Au dessus : déjà suffisant
        self._rerank_min_ram_mb = 1500  # RAM minimale pour activer le cross-encoder
        # V8+ Sprint 4 : Orchestrateur multi-stratégie (initialisé paresseusement)
        self._multi_search = None

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

    def _ms_vector_search(self, query: str, search_type: str = "vector") -> list:
        """Wrapper sync pour la recherche vectorielle/FTS (appelé par MultiSearchOrchestrator).

        Signature : fn(query, search_type='vector'|'fts') -> [(content, source, score)]
        """
        conn = self._get_conn()
        try:
            if search_type == "vector":
                # Embed la requête et chercher par vecteur
                import sqlite_vec
                embed = self.embedder.embed_sync(query, is_query=True)
                if not embed or not embed[0]:
                    return []
                qvec = sqlite_vec.serialize_float32(embed[0])
                rows = conn.execute(
                    "SELECT content, source, 1 - distance as score FROM chunks "
                    "WHERE embedding MATCH ? ORDER BY distance LIMIT 15",
                    [qvec]
                ).fetchall()
            else:  # fts
                from src.query_rewriter import STOP_WORDS
                # `re` est importé au niveau module (ligne 7)
                words = [w for w in re.findall(r'\w{3,}', query.lower()) if w not in STOP_WORDS]
                if not words:
                    words = re.findall(r'\w{3,}', query.lower())
                fts_q = " OR ".join(f'"{w}"' for w in words)
                rows = conn.execute(
                    "SELECT content, source, 1.0 as score FROM chunks_fts "
                    "WHERE content MATCH ? LIMIT 15",
                    [fts_q]
                ).fetchall()
            return [(r[0], r[1], float(r[2])) for r in rows]
        except Exception as e:
            logger.warning(f"⚠️ _ms_vector_search({search_type}) a échoué: {e}")
            return []
        finally:
            conn.close()

    def _ms_vector_search_vec(self, qvec, top_k: int = 5) -> list:
        """Wrapper sync pour la recherche vectorielle à partir d'un vecteur
        (utilisé par HyDE dans MultiSearchOrchestrator).

        Signature : fn(qvec, top_k=N) -> [(content, source, score)]
        """
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
            logger.warning(f"⚠️ _ms_vector_search_vec a échoué (top_k={top_k}): {e}")
            return []
        finally:
            conn.close()

    def _should_use_reranker(self, top1_score: float) -> bool:
        """V6.1 : Reranking SYSTÉMATIQUE — toujours actif si RAM suffisante.

        Le reranker cross-encoder améliore la pertinence de tous les résultats,
        pas seulement ceux de la zone grise. Seules restrictions :
        1. Score minimum 0.15 (pas la peine de reranker du bruit)
        2. RAM disponible > 1.5 Go (évite le swap)
        """
        if top1_score < 0.15:
            return False

        # Vérification RAM
        try:
            import psutil
            ram_free_mb = psutil.virtual_memory().available / (1024 * 1024)
            if ram_free_mb < self._rerank_min_ram_mb:
                logger.info(
                    f"⏭️ Reranker désactivé : RAM insuffisante "
                    f"({ram_free_mb:.0f} MB < {self._rerank_min_ram_mb} MB requis)"
                )
                return False
        except Exception as e:
            logger.warning(f"⚠️ _should_use_reranker: psutil a échoué: {e}")
            return False

        return True

    def _get_conn(self):
        """Ouvre une nouvelle connexion avec support sqlite-vec (Thread-safe).
        
        V8+ : Mode WAL activé pour supporter les accès concurrents 
        (multi-stratégie parallèle sans 'database is locked').
        """
        conn = sqlite3.connect(str(self.db_path), timeout=20)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        # V8+ : WAL mode + synchronous NORMAL pour lectures concurrentes
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self):
        """Initialise la base de données SQLite avec l'extension vec0."""
        conn = self._get_conn()
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING vec0(
                embedding FLOAT[768],
                content TEXT,
                source TEXT,
                chunk_date TEXT
            )
        """)
        # FTS5 pour BM25 (recherche par mots-clés)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                content, source, tokenize='porter'
            )
        """)
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
        conn.commit()
        conn.close()

    def is_file_up_to_date(self, filepath: str, mtime: float = 0, file_hash: str = "") -> bool:
        """Vérifie si le fichier a déjà été indexé avec le même hash SHA256 (V6.2).
        
        V6.2 : Vérifie d'abord par filepath, puis par hash global.
        Si le contenu existe déjà dans l'index (même hash à un autre chemin),
        on considère le fichier comme déjà indexé.
        """
        if not file_hash:
            return False
            
        conn = self._get_conn()
        
        # 1. Vérification par filepath (compatible V4)
        row = conn.execute(
            "SELECT hash FROM indexed_files WHERE filepath = ?", (filepath,)
        ).fetchone()
        
        if row and row[0] == file_hash:
            conn.close()
            return True
        
        # 2. V6.2 : Vérification GLOBALE par hash (même contenu = déjà indexé)
        #    Indépendamment du chemin du fichier
        hash_row = conn.execute(
            "SELECT filepath FROM indexed_files WHERE hash = ? LIMIT 1", (file_hash,)
        ).fetchone()
        
        if hash_row:
            logger.info(f"🔄 Déduplication V6.2 : {os.path.basename(filepath)} déjà indexé "
                       f"sous {os.path.basename(hash_row[0])} (même hash SHA256)")
            conn.close()
            return True
        
        conn.close()
        return False

    def mark_file_indexed(self, filepath: str, mtime: float, file_hash: str = ""):
        """Enregistre un fichier comme indexé avec son hash SHA256 (V6.2).
        
        V6.2 : Si le hash existe déjà (même contenu ailleurs), on met à jour
        l'entrée existante au lieu d'en créer une nouvelle.
        Supprime aussi les entrées obsolètes pour le même filepath.
        """
        conn = self._get_conn()
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
        conn.commit()
        conn.close()

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
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO cv_structured (source, file_hash, json_data, extracted_at) VALUES (?, ?, ?, ?)",
            (source, file_hash, json_data, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        logger.info(f"✅ CV structuré sauvegardé : {source}")

    def get_cv(self, source: str) -> Optional[str]:
        """Retourne le JSON d'un CV structuré par nom de source."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT json_data FROM cv_structured WHERE source = ?", (source,)
        ).fetchone()
        conn.close()
        return row[0] if row else None

    def is_cv_indexed(self, source: str, file_hash: str = "") -> bool:
        """Vérifie si un CV est déjà indexé avec le même hash."""
        conn = self._get_conn()
        if file_hash:
            row = conn.execute(
                "SELECT 1 FROM cv_structured WHERE source = ? AND file_hash = ?",
                (source, file_hash)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM cv_structured WHERE source = ?", (source,)
            ).fetchone()
        conn.close()
        return row is not None

    def remove_cv(self, source: str):
        """Supprime un CV structuré de la table dédiée."""
        conn = self._get_conn()
        conn.execute("DELETE FROM cv_structured WHERE source = ?", (source,))
        conn.commit()
        conn.close()
        logger.info(f"🗑️ CV supprimé : {source}")

    def get_all_cv_data(self) -> list[dict]:
        """Retourne tous les CVs structurés (source + json_data)."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT source, json_data FROM cv_structured ORDER BY source"
        ).fetchall()
        conn.close()
        return [{"source": r[0], "json_data": r[1]} for r in rows]

    # ════════════════════════════════════════════
    # V6 : Métadonnées structurées (tous documents)
    # ════════════════════════════════════════════

    def save_doc_meta(self, source: str, file_hash: str, doc_type: str, json_data: str):
        """Enregistre les métadonnées structurées d'un document."""
        from datetime import datetime
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO doc_structured (source, file_hash, doc_type, json_data, extracted_at) VALUES (?, ?, ?, ?, ?)",
            (source, file_hash, doc_type, json_data, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        logger.info(f"📄 Métadonnées sauvegardées : {source} ({doc_type})")

    def get_doc_meta(self, source: str) -> Optional[str]:
        """Retourne le JSON des métadonnées d'un document."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT json_data FROM doc_structured WHERE source = ?", (source,)
        ).fetchone()
        conn.close()
        return row[0] if row else None

    def is_doc_indexed(self, source: str, file_hash: str = "") -> bool:
        """Vérifie si un document a déjà ses métadonnées structurées."""
        conn = self._get_conn()
        if file_hash:
            row = conn.execute(
                "SELECT 1 FROM doc_structured WHERE source = ? AND file_hash = ?",
                (source, file_hash)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM doc_structured WHERE source = ?", (source,)
            ).fetchone()
        conn.close()
        return row is not None

    def get_all_doc_meta(self, doc_type: str = "") -> list[dict]:
        """Retourne toutes les métadonnées structurées, filtrées par type si demandé."""
        conn = self._get_conn()
        if doc_type:
            rows = conn.execute(
                "SELECT source, doc_type, json_data FROM doc_structured WHERE doc_type = ? ORDER BY source",
                (doc_type,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT source, doc_type, json_data FROM doc_structured ORDER BY source"
            ).fetchall()
        conn.close()
        return [{"source": r[0], "doc_type": r[1], "json_data": r[2]} for r in rows]

    def search_doc_meta(self, keyword: str) -> list[dict]:
        """Recherche textuelle dans les métadonnées structurées (FTS-like simple)."""
        conn = self._get_conn()
        like = f"%{keyword}%"
        rows = conn.execute(
            "SELECT source, doc_type, json_data FROM doc_structured "
            "WHERE source LIKE ? OR json_data LIKE ? ORDER BY source",
            (like, like)
        ).fetchall()
        conn.close()
        return [{"source": r[0], "doc_type": r[1], "json_data": r[2]} for r in rows]

    def remove_doc_meta(self, source: str):
        """Supprime les métadonnées structurées d'un document."""
        conn = self._get_conn()
        conn.execute("DELETE FROM doc_structured WHERE source = ?", (source,))
        conn.commit()
        conn.close()
        logger.info(f"🗑️ Métadonnées supprimées : {source}")

    async def retrieve(self, query: str, k: int = None) -> Tuple[str, RAGResult]:
        '''Recherche hybride avec confidence gate dynamique V4.
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
            confidence_label="HAUTE",  # multi_search décide du early stopping via scores
            top_k=k * 2,               # surplus pour que le reranker ait de la matière
        )

        result.chunks_retrieved = len(ms_results)

        # Log des stratégies multi_search dans le diagnostic RAG
        for strat in ms_diag.strategies_tried:
            count = ms_diag.results_per_strategy.get(strat, 0)
            diag.log_strategy(strat, count, 0.0, count > 0, 0)

        if not ms_results:
            diag.set_verdict("VIDE (aucun résultat)")
            diag.stop()
            result.diagnostic = diag.to_dict()
            result.retrieval_time_ms = (time.time() - t_start) * 1000
            return "", result

        # === V8+ : SCORE GATE DYNAMIQUE (3 niveaux) ===
        top1_score = ms_results[0].score
        self.last_top_score = top1_score
        result.top_score = top1_score
        result.all_scores = [r.score for r in ms_results]

        MIN_ABSOLUTE_SCORE = config.rag_score_threshold   # 0.40
        FALLBACK_THRESHOLD = config.rag_score_fallback     # 0.25
        RAG_MIN_USABLE_SCORE = 0.20  # Seuil en dessous duquel le contexte est vidé

        if top1_score >= MIN_ABSOLUTE_SCORE:
            confidence_label = "HAUTE"
            effective_k = k
        elif top1_score >= FALLBACK_THRESHOLD:
            confidence_label = "MOYENNE"
            effective_k = max(2, k // 2)
            logger.info(f"RAG V8+ : confiance MOYENNE (score={top1_score:.2f}), top_k réduit à {effective_k}")
        else:
            confidence_label = "FAIBLE"
            effective_k = max(1, k // 3)
            logger.info(f"RAG V8+ : confiance FAIBLE (score={top1_score:.2f}), top_k réduit à {effective_k}")

        # ── V10 Audit: Rejeter les résultats clairement non pertinents ──
        # AVERTISSEMENT: placée APRES Profile Boost (ligne ~620), pas ici.
        # Les résultats bruts ms_results ne sont pas encore boostés.

        # Convertir SearchResult → tuples (content, source, score) pour post-processing
        combined_results = [(r.content, r.source, r.score) for r in ms_results]

        # Profile Boost (V8+ P2 : freshness bonus supprimé — pas de chunk_date depuis multi_search)
        # Déduplication simple (tous les fichiers ont la même importance)
        seen_contents = set()
        source_counts = {}
        deduped_results = []

        for content, source, score in combined_results:
            if content not in seen_contents:
                count = source_counts.get(source, 0)
                if count < 2:
                    deduped_results.append((content, source, score))
                    source_counts[source] = count + 1
                    seen_contents.add(content)

        combined_results = deduped_results

        # ── V10 Audit: Rejeter les résultats non pertinents ──
        # Vérifie si le top résultat contient des mots-clés de la requête.
        if combined_results:
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
            # On scanne les 3 meilleurs résultats pour trouver un chunk pertinent
            if not should_reject and query_keywords:
                found_relevant = False
                for rank, (top_content, top_source, _) in enumerate(combined_results[:3]):
                    top_text = (top_content + " " + top_source).lower()
                    keyword_matches = sum(1 for kw in query_keywords if kw in top_text)
                    if keyword_matches >= max(1, len(query_keywords) * 0.3):
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

        # V4.5 Phase 0 : Reranker CONDITIONNEL
        # N'active le cross-encoder QUE si le score est dans la zone grise
        # ET que la RAM disponible est suffisante.
        should_rerank = self._should_use_reranker(top1_score)
        reranked: list = []
        
        if should_rerank:
            # V4.5 FIX PyTorch/MLX Conflict : Décharger l'embedder (MLX) AVANT
            # de charger le reranker (PyTorch/MPS) pour éviter le conflit GPU
            # entre les deux frameworks sur M1 8 Go.
            self.embedder.unload()
            
            try:
                self.reranker.load_model()
                reranked = await self.reranker.rerank(query, combined_results, top_k=effective_k) or []
            finally:
                # IMMÉDIATEMENT après usage, décharger le reranker PyTorch/MPS
                # pour libérer la mémoire GPU avant que le LLM (MLX) ne charge.
                self.reranker.unload()
        
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

        context = self._format_context(reranked)
        # V8+ : En-tête de confiance dans le contexte — TOUJOURS présent
        confidence_header = (
            f"[CONFIANCE RAG: {confidence_label}] "
        )
        if not context.strip() or "[AUCUNE SOURCE]" in context:
            context = confidence_header + "Aucun document pertinent trouvé dans l'index."
        else:
            context = confidence_header + "\n" + context
        result.tokens_injected = len(context) // 4
        result.retrieval_time_ms = (time.time() - t_start) * 1000

        # V6 : Injection des métadonnées structurées dans le contexte
        # Tous les documents avec des métadonnées (summary, sujets) sont injectés
        try:
            from src.document_extractor import DocumentMetadata, format_doc_for_context

            # Récupérer TOUTES les métadonnées structurées disponibles
            all_meta = self.get_all_doc_meta()
            if all_meta:
                injected = 0
                meta_sections = []

                for entry in all_meta:
                    try:
                        data = json.loads(entry["json_data"])
                        meta = DocumentMetadata(
                            source_file=entry["source"],
                            doc_type=entry.get("doc_type", "document"),
                            title=data.get("title", ""),
                            summary=data.get("summary", ""),
                            key_topics=data.get("key_topics", []),
                            entities=data.get("entities", []),
                            dates_mentioned=data.get("dates_mentioned", []),
                            language=data.get("language", ""),
                            word_count=data.get("word_count", 0),
                        )
                        meta.structured_json = entry["json_data"]
                        meta_sections.append(format_doc_for_context(meta))
                        injected += 1
                    except Exception as e:
                        logger.warning(f"⚠️ Formatage métadonnées ignoré: {e}")
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
        conn = self._get_conn()
        
        # V4.5 Phase 0 : top_k réduit de 30 à 15 (moins de bruit, plus rapide)
        # V6.1 : on récupère aussi chunk_date pour le freshness bonus
        vec_results = conn.execute("""
            SELECT content, source, distance, chunk_date
            FROM chunks
            WHERE embedding MATCH ?
            ORDER BY distance
            LIMIT 15
        """, [qvec]).fetchall()
        
        fts_results = []
        if fts_query:
            try:
                fts_results = conn.execute("""
                    SELECT content, source, 1.0 as distance, '' as chunk_date
                    FROM chunks_fts
                    WHERE content MATCH ?
                    LIMIT 15
                """, [fts_query]).fetchall()
            except sqlite3.OperationalError:
                pass
        
        conn.close()
        return vec_results, fts_results

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
            final_score = 0.6 * (1 - vec_dist) + 0.4 * bm25_norm + source_bonus
            scored.append((content, source, min(final_score, 1.0)))
            
        # Trier par score décroissant
        return sorted(scored, key=lambda x: -x[2])[:top_k]

    def _format_context(self, results: List[Tuple]) -> str:
        '''Formate les résultats avec marqueurs CONTEXTE clairs pour forcer le grounding.'''
        context_parts = []
        for i, (content, source, score) in enumerate(results, 1):
            context_parts.append(
                f"[SOURCE {i}] {source}\n"
                f"{sanitize_chunk_content(content)}\n"
            )
        return "=== DÉBUT DU CONTEXTE ===\n" + "\n".join(context_parts) + "\n=== FIN DU CONTEXTE ==="

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
            
        conn = self._get_conn()
        source_name = chunks[0].get("source", "")
        
        # V10 : Supprimer les anciens chunks via la table de mapping rowid
        if dedup_source and source_name:
            old_rows = conn.execute(
                "SELECT rowid FROM chunk_rowids WHERE source = ?", (source_name,)
            ).fetchall()
            old_count = len(old_rows)
            if old_count > 0:
                for (rowid,) in old_rows:
                    conn.execute("DELETE FROM chunks WHERE rowid = ?", (rowid,))
                conn.execute("DELETE FROM chunk_rowids WHERE source = ?", (source_name,))
                conn.execute("DELETE FROM chunks_fts WHERE source = ?", (source_name,))
                logger.info(f"🔄 V10 Déduplication : {old_count} anciens chunks de '{source_name}' remplacés")
        
        for chunk in chunks:
            # V6.1 : date par défaut = aujourd'hui
            chunk_date = chunk.get("date", "") or datetime.now().strftime("%Y-%m-%d")
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
            # Insertion FTS
            conn.execute(
                "INSERT INTO chunks_fts(content, source) VALUES (?, ?)",
                [chunk["content"], chunk["source"]]
            )
        conn.commit()
        conn.close()
        logger.info(f"{len(chunks)} chunks ajoutés à l'index (source: {source_name}).")

    def add_chunks_with_parents(self, chunks: List[dict], doc_summary: str = ""):
        """V6 : Ajoute des chunks avec hiérarchie Parent-Child.
        
        Chaque chunk peut avoir un parent_id. Lors du retrieval, si un enfant
        match, on remonte au parent pour fournir un contexte complet.

        V10 : Stocke les rowid vec0 dans chunk_rowids pour permettre les suppressions.
        """
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
            # Insertion FTS
            conn.execute(
                "INSERT INTO chunks_fts(content, source) VALUES (?, ?)",
                [chunk["content"], chunk["source"]]
            )
        
        conn.commit()
        conn.close()
        logger.info(f"{len(chunks)} chunks (avec hiérarchie) ajoutés à l'index.")

    def _fetch_parent_context(self, source: str, chunk_text: str) -> str:
        """V6 : Remonte au parent d'un chunk pour enrichir le contexte.
        
        Si le chunk actuel est trop court ou trop spécifique, on fetch
        la section parente complète pour donner plus de contexte au LLM.
        """
        if len(chunk_text) > 2000:
            return chunk_text  # Déjà assez long
        
        conn = self._get_conn()
        try:
            # Chercher un parent : une section plus longue de la même source
            parent = conn.execute(
                """SELECT content FROM chunk_hierarchy 
                   WHERE source = ? AND level IN ('document', 'section')
                   AND LENGTH(content) > 1000
                   ORDER BY LENGTH(content) DESC LIMIT 1""",
                (source,)
            ).fetchone()
            conn.close()
            
            if parent and parent[0] != chunk_text:
                return parent[0]
        except Exception as e:
            logger.debug(f"⚠️ _fetch_parent_context: {e}")
            try:
                conn.close()
            except Exception:
                pass

        return chunk_text
    
    def clear_reranker(self, force: bool = False):
        """Décharge le reranker cross-encoder pour libérer la RAM.
        Connecté au RAMMonitor en cas de mémoire critique.
        """
        self.reranker.unload()
        logger.info("🧹 Reranker cross-encoder déchargé (RAMMonitor).")
