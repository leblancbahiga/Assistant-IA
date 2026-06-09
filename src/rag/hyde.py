"""
NURU V8+ — HyDE (Hypothetical Document Embeddings) (Sprint 4.7).

Génère un document hypothétique via CloudLLM, l'embed, puis cherche
les chunks vectoriels les plus proches. Améliore le recall de +15-25%
sur les requêtes ambiguës ou à faible score.

Déclenché UNIQUEMENT si confidence_label = FAIBLE ou ABSENT.
Utilise la REQUÊTE RÉÉCRITE (après QueryRewriter), pas l'originale.
"""

import asyncio
import json
import logging
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Nombre max de résultats HyDE
MAX_HYDE_RESULTS = 5

# Prompt HyDE : demande au LLM de générer un document hypothétique
# qui répondrait parfaitement à la question
HYDE_SYSTEM_PROMPT = (
    "Tu génères un document fictif qui répond PARFAITEMENT à la question posée.\n"
    "Rédige un paragraphe de 4-6 phrases, factuel et détaillé,\n"
    "comme si tu étais un rapport technique ou un document officiel.\n"
    "Utilise un langage neutre et professionnel.\n"
    "Ne mentionne PAS que c'est un document fictif — écris comme si c'était réel."
)


async def hyde_search(
    query: str,
    cloud_llm: object,
    embedder_fn: Callable,
    vector_search_fn: Callable,
    max_results: int = MAX_HYDE_RESULTS,
    top_k: int = 5,
) -> list:
    """Point d'entrée principal HyDE.

    Args:
        query: Requête (idéalement déjà réécrite par QueryRewriter)
        cloud_llm: Instance CloudLLM pour générer le doc hypothétique
        embedder_fn: Fonction sync d'embedding (embedder.embed(doc, is_query=False))
        vector_search_fn: Fonction sync de recherche vectorielle (prend un vecteur sérialisé)
        max_results: Nombre max de résultats
        top_k: Nombre de chunks à récupérer

    Returns:
        list[SearchResult]: Résultats HyDE (via src.rag.multi_search.SearchResult)
    """
    from src.rag.multi_search import SearchResult

    t0 = time.time()

    # 1. Générer le document hypothétique
    hypothetical_doc = await _generate_hypothetical(query, cloud_llm)
    if not hypothetical_doc:
        logger.debug("HyDE: génération document hypothétique vide")
        return []

    logger.info(f"📄 HyDE: doc hypothétique généré ({len(hypothetical_doc)} chars)")

    # 2. Embed le document hypothétique
    try:
        embedding = await asyncio.to_thread(
            lambda: embedder_fn(hypothetical_doc, is_query=False)
        )
        if not embedding or not embedding[0]:
            logger.debug("HyDE: embedding vide")
            return []
        qvec = embedding[0]
    except Exception as e:
        logger.warning(f"HyDE: échec embedding: {e}")
        return []

    # 3. Recherche vectorielle
    try:
        vec_results = await asyncio.to_thread(
            lambda: vector_search_fn(qvec, top_k=top_k)
        )
        if not vec_results:
            logger.debug("HyDE: aucun résultat vectoriel")
            return []
    except Exception as e:
        logger.warning(f"HyDE: échec recherche: {e}")
        return []

    # 4. Construire les SearchResult
    results = []
    for i, (content, source, score) in enumerate(vec_results):
        results.append(SearchResult(
            content=content,
            source=source,
            score=float(score),
            strategy='hyde',
            rank=i,
        ))

    elapsed = (time.time() - t0) * 1000
    logger.info(
        f"📄 HyDE: {len(results)} résultat(s) en {elapsed:.0f}ms "
        f"(doc={len(hypothetical_doc)} chars)"
    )

    return results[:max_results]


async def _generate_hypothetical(query: str, cloud_llm: object) -> str:
    """Génère un document hypothétique via CloudLLM.

    Args:
        query: La requête (idéalement réécrite)
        cloud_llm: Instance CloudLLM avec méthode generate()

    Returns:
        str: Le document hypothétique, ou "" en cas d'échec
    """
    prompt = (
        f"{HYDE_SYSTEM_PROMPT}\n"
        f"\nQuestion : {query}\n"
        f"\nDocument :"
    )

    try:
        response = cloud_llm.generate(prompt, timeout=5.0)
        if not response or not response.strip():
            return ""

        cleaned = response.strip()
        # Limiter à 500 tokens (~2000 chars) pour éviter un doc trop long
        if len(cleaned) > 2000:
            cleaned = cleaned[:2000]

        # Nettoyer les artefacts LLM courants
        import re
        cleaned = re.sub(
            r'^(?:Document\s*:?\s*|Voici\s*:?\s*|Bien sûr[^:]*:?\s*)',
            '', cleaned, flags=re.IGNORECASE
        ).strip()

        return cleaned

    except Exception as e:
        logger.warning(f"HyDE génération échouée: {e}")
        return ""


def hyde_vector_search(
    qvec: list[float],
    rag_engine: object,
    top_k: int = 5,
) -> list[tuple]:
    """Recherche vectorielle avec le vecteur HyDE.

    Wrapper autour de RAGEngine._search_db pour compatibilité.

    Returns:
        list[(content, source, score)]: Résultats triés par score décroissant
    """
    import sqlite_vec
    import struct

    try:
        # Sérialiser le vecteur pour sqlite-vec
        serialized = sqlite_vec.serialize_float32(qvec)

        # Utiliser la méthode de recherche de RAGEngine
        conn = rag_engine._get_conn()
        rows = conn.execute(
            "SELECT content, source, distance FROM chunks "
            "WHERE embedding MATCH ? "
            "ORDER BY distance LIMIT ?",
            [serialized, top_k]
        ).fetchall()
        conn.close()

        return [(r[0], r[1], 1 - r[2]) for r in rows if r[0] and r[2] < 1.0]

    except Exception as e:
        logger.warning(f"HyDE vector search error: {e}")
        return []
