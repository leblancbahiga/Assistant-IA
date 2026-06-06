# NURU V5 : pysqlite3 avec support d'extensions (nécessaire pour sqlite-vec sur macOS)
import pysqlite3 as sqlite3
import sqlite_vec
import asyncio
import os
import json
import time
import logging
import re
from typing import List, Tuple, Optional
from dataclasses import dataclass, field
from pathlib import Path
from src.config import config
from src.embedder import Embedder
from src.query_rewriter import QueryRewriter
from src.reranker import CrossEncoderReranker

logger = logging.getLogger(__name__)


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

class RAGEngine:
    """Moteur RAG Hybride : Recherche sémantique (sqlite-vec) + BM25."""
    
    def __init__(self):
        self.db_path = config.index_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = Embedder()
        self.rewriter = QueryRewriter()
        self.reranker = CrossEncoderReranker()  # V4 : Reranker sémantique
        self.reranker.set_embedder(self.embedder)  # Connecte l'embedder
        self.last_top_score = 0.0
        self._init_db()
        # V4.5 Phase 0 : seuils configurés pour reranker conditionnel
        self._rerank_min_score = 0.40   # En dessous : pas la peine
        self._rerank_max_score = 0.75   # Au dessus : déjà suffisant
        self._rerank_min_ram_mb = 1500  # RAM minimale pour activer le cross-encoder

    def _should_use_reranker(self, top1_score: float) -> bool:
        """V4.5 Phase 0 : Détermine si le reranker cross-encoder est nécessaire.

        Le reranker est coûteux (~500 MB RAM, ~18s). On ne l'active QUE si :
        1. Le score vectoriel est dans la zone grise (0.40 < score < 0.75)
        2. La RAM disponible est suffisante (> 1.5 Go)
        Sinon, BM25 fait le travail.
        """
        in_gray_zone = self._rerank_min_score < top1_score < self._rerank_max_score
        if not in_gray_zone:
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
        except Exception:
            pass  # Si psutil échoue, on autorise le reranker

        return True

    def _get_conn(self):
        """Ouvre une nouvelle connexion avec support sqlite-vec (Thread-safe)."""
        conn = sqlite3.connect(str(self.db_path), timeout=20)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
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
        conn.commit()
        conn.close()

    def is_file_up_to_date(self, filepath: str, mtime: float = 0, file_hash: str = "") -> bool:
        """Vérifie si le fichier a déjà été indexé avec le même hash SHA256 (V4)."""
        if not file_hash:
            return False
            
        conn = self._get_conn()
        row = conn.execute(
            "SELECT hash FROM indexed_files WHERE filepath = ?", (filepath,)
        ).fetchone()
        conn.close()
        
        if row and row[0] == file_hash:
            return True
        return False

    def mark_file_indexed(self, filepath: str, mtime: float, file_hash: str = ""):
        """Enregistre un fichier comme indexé avec son hash SHA256."""
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO indexed_files (filepath, mtime, hash) VALUES (?, ?, ?)",
            (filepath, mtime, file_hash)
        )
        conn.commit()
        conn.close()

    def remove_file_index(self, source_name: str):
        """Supprime tous les chunks associés à une source."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM chunks WHERE source = ?", (source_name,))
            conn.execute("DELETE FROM chunks_fts WHERE source = ?", (source_name,))
            conn.commit()
        except Exception as e:
            logger.warning(f"Impossible de supprimer l'ancien index pour {source_name}: {e}")
        conn.close()

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
        """Recherche hybride avec confidence gate dynamique V4.
        Retourne (contexte_formaté, RAGResult) pour le dashboard."""
        t_start = time.time()
        if k is None:
            k = config.rag_k

        result = RAGResult(top_k_configured=k, query_rewritten="")

        # 1. Optimisation de la requête
        optimized_query = self.rewriter.rewrite(query)
        fts_query = self.rewriter.normalize_for_fts(query)
        result.query_rewritten = optimized_query

        # 2. Embedding
        embeddings = await self.embedder.embed(optimized_query, is_query=True)
        qvec = sqlite_vec.serialize_float32(embeddings[0])

        vec_results, fts_results = await asyncio.to_thread(
            self._search_db, qvec, fts_query
        )

        result.chunks_retrieved = len(vec_results) + len(fts_results)

        if not vec_results and not fts_results:
            result.retrieval_time_ms = (time.time() - t_start) * 1000
            return "", result

        # === DYNAMIC CONFIDENCE GATE V4.2 ===
        top1_dist = vec_results[0][2] if vec_results else 1.0
        top1_score = 1 - top1_dist

        self.last_top_score = top1_score
        result.top_score = top1_score
        result.all_scores = [1 - d for _, _, d in vec_results] if vec_results else []

        # NURU V5 : Seuil depuis config.settings.yaml
        # V6 : seuils alignés sur les nouvelles valeurs de settings.yaml
        MIN_ABSOLUTE_SCORE = config.rag_score_threshold
        FALLBACK_THRESHOLD = config.rag_score_fallback

        is_reliable = top1_score >= MIN_ABSOLUTE_SCORE or (len(fts_results) > 0 and top1_score >= FALLBACK_THRESHOLD)

        if not is_reliable:
            result.rejection_reason = f"top_score={top1_score:.2f} < {MIN_ABSOLUTE_SCORE}"
            result.rejected_chunks = result.chunks_retrieved
            result.retrieval_time_ms = (time.time() - t_start) * 1000
            logger.info(f"RAG Confidence Gate V4.2: top1={top1_score:.2f} (requis: >={MIN_ABSOLUTE_SCORE}, FTS fallback: >={FALLBACK_THRESHOLD}) → Rejeté")
            return "", result

        seen_contents = set()
        source_counts = {}
        combined_results = []
        source_list = []

        # V4.5 Phase 2 : Fusion RRF des résultats vectoriels et FTS
        from src.rag.retrieval import reciprocal_rank_fusion
        fused = reciprocal_rank_fusion(vec_results, fts_results, top_k=k)

        # NURU V6 : Profile Boost — multiplier le score des documents de Leblanc
        try:
            from src.profile_boost import get_boost_score
            fused = [
                (content, source, score * get_boost_score(source))
                for content, source, score in fused
            ]
            # Re-trier par score boosté
            fused.sort(key=lambda x: x[2], reverse=True)
        except Exception:
            pass

        # Déduplication par contenu après RRF
        for content, source, score in fused:
            if content not in seen_contents:
                count = source_counts.get(source, 0)
                if count < 2:
                    combined_results.append((content, source, score))
                    source_counts[source] = count + 1
                    seen_contents.add(content)

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
                reranked = await self.reranker.rerank(query, combined_results, top_k=k) or []
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
            reranked = self.bm25_rerank(query, combined_results, top_k=k)
        
        # Seconde confidence gate APRÈS reranking (uniquement si reranker a été utilisé)
        if should_rerank and reranked and reranked[0][2] < 0.10:
            logger.warning(f"🗑️ Tous les chunks rejetés par reranker (top1={reranked[0][2]:.2f})")
            if top1_score >= 0.35:
                logger.info("↪️ Fallback BM25 pour éviter un rejet injustifié.")
                reranked = self.bm25_rerank(query, combined_results, top_k=3)
        
        result.chunks_injected = len(reranked)
        result.top_k_actual = len(reranked)

        # Build sources list
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
                    except Exception:
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

        return context, result

    def _search_db(self, qvec: bytes, fts_query: str) -> Tuple:
        """Exécute les recherches vectorielle et FTS dans un thread séparé."""
        conn = self._get_conn()
        
        # V4.5 Phase 0 : top_k réduit de 30 à 15 (moins de bruit, plus rapide)
        vec_results = conn.execute("""
            SELECT content, source, distance
            FROM chunks
            WHERE embedding MATCH ?
            ORDER BY distance
            LIMIT 15
        """, [qvec]).fetchall()
        
        fts_results = []
        if fts_query:
            try:
                fts_results = conn.execute("""
                    SELECT content, source, 1.0 as distance
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
        import re
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
        """Formate les résultats avec marqueurs CONTEXTE clairs pour forcer le grounding."""
        context_parts = []
        for i, (content, source, score) in enumerate(results, 1):
            context_parts.append(
                f"[SOURCE {i}] {source}\n"
                f"{content.strip()}\n"
            )
        return "=== DÉBUT DU CONTEXTE ===\n" + "\n".join(context_parts) + "\n=== FIN DU CONTEXTE ==="

    def add_chunks(self, chunks: List[dict]):
        """Ajoute des chunks à l'index vectoriel et FTS."""
        conn = self._get_conn()
        for chunk in chunks:
            # Insertion Vectorielle
            conn.execute(
                "INSERT INTO chunks(embedding, content, source, chunk_date) VALUES (?, ?, ?, ?)",
                [sqlite_vec.serialize_float32(chunk["embedding"]), chunk["content"], chunk["source"], chunk.get("date", "")]
            )
            # Insertion FTS
            conn.execute(
                "INSERT INTO chunks_fts(content, source) VALUES (?, ?)",
                [chunk["content"], chunk["source"]]
            )
        conn.commit()
        conn.close()
        logger.info(f"{len(chunks)} chunks ajoutés à l'index.")

    def add_chunks_with_parents(self, chunks: List[dict], doc_summary: str = ""):
        """V6 : Ajoute des chunks avec hiérarchie Parent-Child.
        
        Chaque chunk peut avoir un parent_id. Lors du retrieval, si un enfant
        match, on remonte au parent pour fournir un contexte complet.
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
            
            # Insertion Vectorielle
            conn.execute(
                "INSERT INTO chunks(embedding, content, source, chunk_date) VALUES (?, ?, ?, ?)",
                [sqlite_vec.serialize_float32(chunk["embedding"]), chunk["content"], chunk["source"], chunk.get("date", "")]
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
        except Exception:
            conn.close()
        
        return chunk_text
    
    def clear_reranker(self, force: bool = False):
        """Décharge le reranker cross-encoder pour libérer la RAM.
        Connecté au RAMMonitor en cas de mémoire critique.
        """
        self.reranker.unload()
        logger.info("🧹 Reranker cross-encoder déchargé (RAMMonitor).")
