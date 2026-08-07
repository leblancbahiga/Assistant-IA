"""
NURU V8+ — Orchestrateur de recherche multi-stratégie (Sprint 4).

Lance plusieurs stratégies de recherche en parallèle et fusionne
les résultats via RRF normalisé (basé sur les RANGS, pas les scores bruts).

Stratégies :
1. Vectoriel (sqlite-vec) — recherche sémantique
2. FTS5 (BM25) — recherche lexicale
3. Métadonnées structurées (doc_structured)
4. Grep (to_thread, ligne par ligne) — si RAM suffisante ET score FAIBLE
5. HyDE — si score FAIBLE/ABSENT (nécessite CloudLLM)
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Final, Optional

from src.config import config
from src.rag.types import SearchResult

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────

# V10.3k — audit Option C : seuil RAM configurable via Config.
# Défaut historique 2000 inadapté à M1 8 Go (1.1 Go dispo réelle).
MIN_RAM_FOR_HEAVY_SEARCH_MB = getattr(
    config, "heavy_search_min_ram_mb", 1000
)
RRF_K = 60                              # Constante RRF standard
MAX_RRF_STRATEGIES = 5                  # Max théorique : vectoriel + FTS + metadata + grep + HyDE
EARLY_STOP_SCORE = 0.75                 # Score FTS/Vectoriel > 0.75 → skip grep/HyDE
DEDUP_COSINE_THRESHOLD = 0.50           # V17.2: 0.90→0.50 (Jaccard) — collabse les lettres quasi-identiques
MAX_GREP_RESULTS = 3                    # Résultats grep max
MAX_HYDE_RESULTS = 5                    # Résultats HyDE max
RAM_CHECK_INTERVAL_S = 10.0             # Vérification RAM au plus toutes les 10s

# Cache de la dernière vérification RAM
_last_ram_check: float = 0
_last_ram_result: tuple[bool, int] = (True, 9999)


# ──────────────────────────────────────────
# Types de données
# ──────────────────────────────────────────

@dataclass
class MultiSearchDiagnostic:
    """Diagnostic temps réel de la recherche multi-stratégie."""
    query: str
    strategies_tried: list[str] = field(default_factory=list)
    strategies_timing: dict[str, float] = field(default_factory=dict)
    results_per_strategy: dict[str, int] = field(default_factory=dict)
    early_stopped: bool = False
    early_stop_reason: str = ""
    grep_called: bool = False
    hyde_called: bool = False
    ram_ok: bool = False
    ram_free_mb: int = 0
    total_results_before_dedup: int = 0
    total_results_after_dedup: int = 0
    rrf_top_k_actual: int = 0
    total_time_ms: float = 0.0
    # V15 #18 : Ambiguity detection
    _ambiguity_gap: float = 0.0
    _ambiguous: bool = False


# ──────────────────────────────────────────
# Vérification RAM
# ──────────────────────────────────────────

def check_ram_available() -> tuple[bool, int]:
    """Vérifie si la RAM disponible est suffisante pour les recherches lourdes.

    Cache le résultat 10s pour éviter des appels psutil trop fréquents.
    Retourne (ok, free_mb).
    """
    global _last_ram_check, _last_ram_result
    now = time.time()
    if now - _last_ram_check < RAM_CHECK_INTERVAL_S:
        return _last_ram_result

    try:
        import psutil
        free_mb = int(psutil.virtual_memory().available / (1024 * 1024))
        ok = free_mb >= MIN_RAM_FOR_HEAVY_SEARCH_MB
        if not ok:
            logger.info(
                f"RAM insuffisante pour recherche lourde : {free_mb} MB "
                f"(seuil: {MIN_RAM_FOR_HEAVY_SEARCH_MB} MB)"
            )
        _last_ram_check = now
        _last_ram_result = (ok, free_mb)
        return ok, free_mb
    except Exception:
        return True, 9999


# ──────────────────────────────────────────
# Fusion RRF (basée sur les RANGS, pas les scores bruts)
# V15 Phase 0B : normalisation débiaisée + poids par stratégie
# ──────────────────────────────────────────

# Poids relatifs des stratégies RRF — V17: ratio 0.55/0.25/0.15 vectoriel/fts/meta
STRATEGY_WEIGHTS: dict[str, float] = {
    "vectoriel": 1.0,
    "fts": 0.45,
    "metadata": 0.27,
    "hyde": 0.6,
    "grep": 0.5,
}


def reciprocal_rank_fusion(
    strategy_results: list[list[SearchResult]],
    strategy_labels: Optional[list[str]] = None,
    k: int = RRF_K,
) -> list[SearchResult]:
    """Fusion RRF débiaisée — chaque stratégie contribue selon son poids.

    Le score normalisé tient compte du nombre réel et de la qualité
    des stratégies exécutées, pas d'un maximum théorique arbitraire.

    Args:
        strategy_results: Résultats classés par stratégie
        strategy_labels: Noms des stratégies (pour pondération)
        k: Constante RRF standard
    """
    if strategy_labels is None:
        strategy_labels = [""] * len(strategy_results)

    scores: dict[tuple[str, str], float] = defaultdict(float)
    content_map: dict[tuple[str, str], str] = {}
    raw_scores: dict[tuple[str, str], float] = defaultdict(float)  # V16+: preserve max raw score

    total_max_possible = 0.0
    active_weights_sum = 0.0

    for results, label in zip(strategy_results, strategy_labels):
        weight = STRATEGY_WEIGHTS.get(label, 0.5)
        active_weights_sum += weight
        for rank in range(1, len(results) + 1):
            total_max_possible += weight * (1.0 / (k + rank))

        for rank, r in enumerate(results, start=1):
            key = (r.content[:400], r.source)
            scores[key] += weight * (1.0 / (k + rank))
            if key not in raw_scores or r.raw_score > raw_scores[key]:
                raw_scores[key] = r.raw_score
            if key not in content_map or len(r.content) > len(content_map[key]):
                content_map[key] = r.content

    if not scores or total_max_possible <= 0:
        return []

    # V17.2: normalisation min-max par le MEILLEUR score RRF reel du lot,
    # PAS par un plafond theorique (qui saturait tout a ~1.0 → plus de
    # discrimination). Le meilleur chunk = 1.0, les autres s'etalent.
    best_rrf = max(scores.values())
    if best_rrf <= 0:
        return []
    fused = [
        SearchResult(
            content=content_map[key],
            source=key[1],
            score=rrf_score / best_rrf,
            raw_score=raw_scores.get(key, 0.0),
            strategy='rrf',
            rank=0,
        )
        for key, rrf_score in scores.items()
    ]

    fused.sort(key=lambda x: x.score, reverse=True)
    return fused


# ──────────────────────────────────────────
# Déduplication sémantique
# ──────────────────────────────────────────

def semantic_dedup(
    results: list[SearchResult],
    threshold: float = DEDUP_COSINE_THRESHOLD,
) -> list[SearchResult]:
    """Déduplication sémantique : si cos > threshold entre 2 résultats, drop le second.

    Utilise un overlap de mots comme proxy de similarité (pas de modèle d'embedding
    coûteux — évite un appel MLX pour ça).
    """
    if len(results) < 2:
        return results

    deduped: list[SearchResult] = []
    for r in results:
        is_dup = False
        words_r = set(r.content.lower().split())
        if not words_r:
            deduped.append(r)
            continue

        for existing in deduped:
            words_e = set(existing.content.lower().split())
            if not words_e:
                continue
            # Jaccard-like overlap
            intersection = words_r & words_e
            union = words_r | words_e
            if len(union) > 0:
                jaccard = len(intersection) / len(union)
                if jaccard >= threshold:
                    is_dup = True
                    break

        if not is_dup:
            deduped.append(r)

    return deduped


# ──────────────────────────────────────────
# Orchestrateur multi-stratégie
# ──────────────────────────────────────────

class MultiSearchOrchestrator:
    """Orchestre les stratégies de recherche en parallèle avec RRF fusion.

    Usage:
        orchestrator = MultiSearchOrchestrator(
            vector_search=rag_engine._search_db,
            cloud_llm=cloud_llm_instance,
        )
        results, diag = await orchestrator.search(query, rewritten_query, top_k=5)
    """

    def __init__(
        self,
        vector_search_fn: Optional[Callable] = None,
        cloud_llm: Optional[object] = None,
        get_doc_meta_fn: Optional[Callable] = None,
        grep_fn: Optional[Callable] = None,
        embedder_fn: Optional[Callable] = None,
        vector_search_vec_fn: Optional[Callable] = None,
        model_size_below_7b: bool = True,
        ambiguity_threshold: float = 0.30,
    ):
        self._vector_search = vector_search_fn
        self._cloud = cloud_llm
        self._get_doc_meta = get_doc_meta_fn
        self._grep = grep_fn
        self._embedder = embedder_fn
        self._vector_search_vec = vector_search_vec_fn

        # V15 #18 : Détection modèle <7B + seuil d'ambiguïté
        self._small_model = model_size_below_7b
        self._ambiguity_threshold = ambiguity_threshold

    async def search(
        self,
        query: str,
        rewritten_query: str = "",
        top_k: int = 5,
    ) -> tuple[list[SearchResult], MultiSearchDiagnostic]:
        """Point d'entrée principal — exécute les stratégies appropriées.

        Args:
            query: Requête utilisateur originale
            rewritten_query: Requête réécrite (par QueryRewriter)
            top_k: Nombre de résultats souhaité

        Returns:
            (results_fusionnés, diagnostic)
        """
        t_start = time.time()
        diag = MultiSearchDiagnostic(query=query[:200])
        ram_ok, ram_free = check_ram_available()
        diag.ram_ok = ram_ok
        diag.ram_free_mb = ram_free

        effective_query = rewritten_query or query
        # V12.1 : is_weak supprimé — le early_stopping (score >= EARLY_STOP_SCORE)
        # est le seul garde-fou. HyDE+grep sont lancés dès que le score rapide
        # est insuffisant, sans dépendre d'un confidence_label externe.
        early_stop = False
        heavy_labels: list[str] = []
        heavy_gathered: list = []

        # ── Round 1 : Stratégies RAPIDES (vectoriel + FTS + métadonnées) ──
        # Ces stratégies prennent < 50ms. On les attend pour décider
        # si grep + HyDE sont nécessaires (early stopping).
        fast_strategies: list[asyncio.Task] = []
        fast_labels: list[str] = []

        if self._vector_search:
            fast_strategies.append(asyncio.create_task(
                self._run_vector_search(effective_query)
            ))
            fast_labels.append("vectoriel")

        if self._vector_search:
            fast_strategies.append(asyncio.create_task(
                self._run_fts_search(effective_query)
            ))
            fast_labels.append("fts")

        if self._get_doc_meta:
            fast_strategies.append(asyncio.create_task(
                self._run_metadata_search(effective_query)
            ))
            fast_labels.append("metadata")

        # Attendre les stratégies rapides
        all_results: list[list[SearchResult]] = []
        fast_gathered = await asyncio.gather(*fast_strategies, return_exceptions=True)

        for label, result in zip(fast_labels, fast_gathered):
            if isinstance(result, Exception):
                logger.warning(f"⚠️ Échec stratégie {label}: {result}")
                diag.strategies_tried.append(label)
                diag.results_per_strategy[label] = 0
                all_results.append([])
                continue

            all_results.append(result)
            diag.strategies_tried.append(label)
            diag.results_per_strategy[label] = len(result)

        # Early stopping V15 #18 : détection d'ambiguïté + modèle <7B
        max_fast_score = 0.0
        min_fast_score = 1.0  # V15 #18 : pour calculer l'écart top-1/top-5
        fast_scores: list[float] = []
        for idx, label in enumerate(fast_labels):
            if label in ("vectoriel", "fts") and idx < len(all_results):
                if all_results[idx]:
                    scores = [r.score for r in all_results[idx]]
                    s = max(scores)
                    max_fast_score = max(max_fast_score, s)
                    fast_scores.extend(scores)

        # V15 #18 : Ambiguity detection — si écart top-1/top-5 > seuil
        ambiguous = False
        if len(fast_scores) >= 2:
            fast_scores.sort(reverse=True)
            gap = fast_scores[0] - fast_scores[-1]
            ambiguous = gap >= self._ambiguity_threshold
            diag._ambiguity_gap = round(gap, 3)
            diag._ambiguous = ambiguous

        if max_fast_score >= EARLY_STOP_SCORE and not ambiguous:
            early_stop = True
            diag.early_stopped = True
            diag.early_stop_reason = (
                f"Score max={max_fast_score:.2f} >= {EARLY_STOP_SCORE}"
            )
            logger.info(f"⏭️ Early stopping: score={max_fast_score:.2f} >= {EARLY_STOP_SCORE}")
        else:
            # ── Round 2 : Stratégies LOURDES (grep + HyDE) ──
            # Lancées SEULEMENT si le score rapide est insuffisant
            if ram_ok and self._grep:
                grep_task = asyncio.create_task(self._run_grep(query))
                diag.grep_called = True

            if ram_ok and self._cloud:
                hyde_task = asyncio.create_task(self._run_hyde(query))
                diag.hyde_called = True

            # Attendre grep et HyDE en parallèle
            heavy_tasks = []
            heavy_labels = []
            if ram_ok and self._grep:
                heavy_tasks.append(grep_task)
                heavy_labels.append("grep")
            if ram_ok and self._cloud:
                heavy_tasks.append(hyde_task)
                heavy_labels.append("hyde")

            if heavy_tasks:
                heavy_gathered = await asyncio.gather(*heavy_tasks, return_exceptions=True)
                for label, result in zip(heavy_labels, heavy_gathered):
                    if isinstance(result, Exception):
                        logger.warning(f"⚠️ Échec stratégie {label}: {result}")
                        diag.strategies_tried.append(label)
                        diag.results_per_strategy[label] = 0
                        all_results.append([])
                        continue
                    all_results.append(result)
                    diag.strategies_tried.append(label)
                    diag.results_per_strategy[label] = len(result)

        # Compter les résultats
        diag.total_results_before_dedup = sum(len(r) for r in all_results)

        # ── Construction des labels de stratégies pour RRF pondéré ──
        all_labels = fast_labels[:] + heavy_labels  # même ordre que all_results

        # ── Fusion RRF (par RANGS) ──
        if not all_results:
            diag.total_time_ms = (time.time() - t_start) * 1000
            return [], diag

        fused = reciprocal_rank_fusion(all_results, strategy_labels=all_labels)

        # ── Déduplication sémantique ──
        deduped = semantic_dedup(fused)
        diag.total_results_after_dedup = len(deduped)

        # ── Top-K final ──
        final = deduped[:top_k]
        diag.rrf_top_k_actual = len(final)
        diag.total_time_ms = (time.time() - t_start) * 1000

        return final, diag

    # ──────────────────────────────────────
    # Sous-stratégies
    # ──────────────────────────────────────

    async def _run_vector_search(self, query: str) -> list[SearchResult]:
        """Recherche vectorielle via sqlite-vec à partir d'un texte."""
        if not self._vector_search:
            return []

        t0 = time.time()
        try:
            vec_results = await asyncio.to_thread(
                self._vector_search, query, search_type="vector"
            )
            results = []
            for i, (content, source, score) in enumerate(vec_results):
                results.append(SearchResult(
                    content=content,
                    source=source,
                    score=float(score),
                    raw_score=float(score),
                    strategy='vectoriel',
                    rank=i,
                ))
            return results
        except Exception as e:
            logger.warning(f"Recherche vectorielle échouée: {e}")
            return []

    async def _run_vector_search_with_vec(self, qvec, top_k: int = 5) -> list:
        """Recherche vectorielle à partir d'un vecteur (pour HyDE).

        Utilise vector_search_vec_fn ou vector_search_fn avec la signature (qvec, top_k).
        Retourne [(content, source, score)].
        """
        fn = self._vector_search_vec or self._vector_search
        if not fn:
            return []

        try:
            results = await asyncio.to_thread(
                lambda: fn(qvec, top_k=top_k)
            )
            return [(c, s, float(sc)) for c, s, sc in results]
        except Exception as e:
            logger.warning(f"Recherche vectorielle (vecteur) échouée: {e}")
            return []

    async def _run_fts_search(self, query: str) -> list[SearchResult]:
        """Recherche FTS5 (BM25)."""
        if not self._vector_search:
            return []

        t0 = time.time()
        try:
            fts_results = await asyncio.to_thread(
                self._vector_search, query, search_type="fts"
            )
            results = []
            for i, (content, source, score) in enumerate(fts_results):
                results.append(SearchResult(
                    content=content,
                    source=source,
                    score=float(score),
                    raw_score=float(score),
                    strategy='fts',
                    rank=i,
                ))
            return results
        except Exception as e:
            logger.warning(f"Recherche FTS échouée: {e}")
            return []

    async def _run_metadata_search(self, query: str) -> list[SearchResult]:
        """Recherche dans les métadonnées structurées."""
        if not self._get_doc_meta:
            return []

        try:
            results = await asyncio.to_thread(
                lambda: self._get_doc_meta(query)
            )
            search_results = []
            for i, item in enumerate(results):
                json_data = item.get("json_data", "{}")
                search_results.append(SearchResult(
                    content=f"[{item.get('doc_type', 'doc')}] {json_data[:500]}",
                    source=item.get("source", ""),
                    score=max(0.0, 0.5 - i * 0.1),  # Score décroissant
                    raw_score=max(0.0, 0.5 - i * 0.1),
                    strategy='metadata',
                    rank=i,
                ))
            return search_results
        except Exception as e:
            logger.debug(f"Recherche métadonnées: {e}")
            return []

    async def _run_grep(self, query: str) -> list[SearchResult]:
        """Recherche par grep dans les fichiers (si RAM suffisante)."""
        if not self._grep:
            return []

        try:
            grep_results = await asyncio.to_thread(
                lambda: self._grep(query, max_results=MAX_GREP_RESULTS)
            )
            results = []
            for i, r in enumerate(grep_results):
                results.append(SearchResult(
                    content=r.get("content", "")[:2000],
                    source=r.get("filename", r.get("path", "")),
                    score=float(r.get("score", 0.5)),
                    raw_score=float(r.get("score", 0.5)),
                    strategy='grep',
                    rank=i,
                ))
            return results
        except Exception as e:
            logger.warning(f"Grep échoué: {e}")
            return []

    async def _run_hyde(self, query: str) -> list[SearchResult]:
        """HyDE — voir src/rag/hyde.py pour l'implémentation complète."""
        if not self._cloud or not self._embedder:
            return []

        # V15 Phase 0B : activation conditionnelle — HyDE coûte 5s + tokens cloud,
        # inutile pour les requêtes simples (1 mot, entité nommée, fait direct)
        if not self._should_use_hyde(query):
            logger.debug(f"⏭️ HyDE désactivé pour requête simple: {query!r}")
            return []

        try:
            from src.rag.hyde import hyde_search
            hyde_results = await hyde_search(
                query=query,
                cloud_llm=self._cloud,
                embedder_fn=self._embedder,
                vector_search_fn=self._vector_search_vec,  # synchrone (RAGEngine._search_db)
                max_results=MAX_HYDE_RESULTS,
            )
            return hyde_results
        except ImportError:
            logger.debug("HyDE pas encore disponible (sera implémenté en 4.7)")
            return []
        except Exception as e:
            logger.warning(f"HyDE échoué: {e}")
            return []

    # ──────────────────────────────────────
    # V15 #18 : Activation conditionnelle HyDE

    _SIMPLE_QUERY_WORDS: Final = frozenset({
        "bonjour", "salut", "hello", "hi", "merci", "bye", "oui", "non",
    })

    @staticmethod
    def _is_small_model_query(query: str) -> bool:
        """Skip HyDE quand la requête ne justifie pas son coût.

        Modèle <7B : HyDE ajoute latence sans gain significatif.
        Requêtes simples (≤1 mot, salutations, entités) : pas d'ambiguïté.
        """
        q = query.strip()
        if not q or len(q) < 10:
            return True
        words = q.split()
        if len(words) <= 1:
            return True
        if q.lower() in MultiSearchOrchestrator._SIMPLE_QUERY_WORDS:
            return True
        # Entité nommée seule (pas de verbe)
        if len(words) <= 3 and not any(
            c in q for c in ("?", "comment", "pourquoi", "qu'est-ce", "est-ce",
                             "explique", "décrit", "compare", "différence")
        ):
            import re
            if not re.search(r'\b(est|sont|fait|a\b|ont|peut|veut|dit|donne|trouve)\b', q, re.I):
                return True
        return False

    def _should_use_hyde(self, query: str) -> bool:
        """Active HyDE seulement pour les requêtes complexes ET modèle ≥7B."""
        q = query.strip()
        if not q:
            return False

        # Modèle <7B → HyDE désactivé (coût > bénéfice sur M1 8 Go)
        if self._small_model:
            logger.debug("⏭️ HyDE désactivé : modèle <7B")
            return False

        # Requête simple → pas besoin de HyDE
        if self._is_small_model_query(query):
            return False

        return True
