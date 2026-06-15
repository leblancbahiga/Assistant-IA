"""Test B-Routing-QuiEst — Audit 2026-06-14.

Bug : 'Qui est Leblanc Bahiga ?' est routé comme GENERAL_KNOWLEDGE.
Cause : semantic_router.py:158 — has_gk ET not has_rag_kw → GENERAL_KNOWLEDGE.
Ni 'Leblanc' ni 'Bahiga' ni 'qui est [nom propre]' ne sont dans RAG_KEYWORDS.

Le résultat : rag_context=XXXX chars trouvé dans le CV, mais intent=GENERAL
donc le LLM répond 'je ne dispose pas d'info sur cette personne' au lieu
d'utiliser le CV Leblanc.

Le fix doit :
1. Inclure des noms-propres typiques (Leblanc, Bahiga, etc.) dans RAG_KEYWORDS
2. OU : inverser la logique — si la requête commence par 'qui est [Nom capitalized]'
   alors RAG (car identité personnelle)
3. OU : si RAG a trouvé top_score > 0.20 → forcer DOCUMENT_KEYWORD même si has_gk

Cas à tester :
- 'Qui est Leblanc Bahiga ?' → doit être RAG/DOCUMENT_KEYWORD
- 'Qui est le président de la France ?' → reste GENERAL (culture générale)
- 'Combien font 2+2 ?' → reste GENERAL (math)
- 'Cherche dans mon CV' → RAG (déjà testé)
"""
import pytest


def test_qui_est_leblanc_doit_router_vers_rag():
    """'Qui est Leblanc Bahiga ?' doit aller vers RAG (le CV est dans l'index)."""
    from src.semantic_router import SemanticRouter
    import asyncio

    async def go():
        router = SemanticRouter(rag_engine=None, is_online_check=None, cloud_llm=None)
        result = await router.route("Qui est Leblanc Bahiga ?", rag_context="", rag_result=None)
        return result.decision, result.confidence

    decision, conf = asyncio.run(go())
    assert decision in ("DOCUMENT_KEYWORD", "LOCAL_RAG"), (
        f"'Qui est Leblanc Bahiga ?' routé vers {decision} (conf={conf}). "
        f"Devrait être DOCUMENT_KEYWORD ou LOCAL_RAG. "
        f"Voir semantic_router.py:158 — GENERAL_KNOWLEDGE matche 'qui est' "
        f"mais ignore que 'Leblanc Bahiga' est 99% d'identité personnelle."
    )


def test_qui_president_france_pas_rag():
    """'Qui est le président de la France ?' doit PAS être RAG (c'est culture générale)."""
    from src.semantic_router import SemanticRouter
    import asyncio

    async def go():
        router = SemanticRouter(rag_engine=None, is_online_check=None, cloud_llm=None)
        result = await router.route(
            "Qui est le président de la France ?",
            rag_context="", rag_result=None
        )
        return result.decision

    decision = asyncio.run(go())
    assert decision != "DOCUMENT_KEYWORD", (
        f"'Qui est le président de la France ?' routé vers {decision}. "
        f"Ne doit pas être DOCUMENT_KEYWORD (c'est une question de culture G, "
        f"pas sur un document utilisateur)."
    )
    assert decision != "LOCAL_RAG", (
        f"'Qui est le président de la France ?' → LOCAL_RAG ? Inattendu."
    )


def test_un_mecanisme_qui_est_nom_propre_existe():
    """Le router doit avoir un mécanisme pour reconnaitre 'Qui est [Nom]'.

    Le fix actuel (V10.3k) :
    1. trouve 'qui est' dans query_lower
    2. récupère le mot suivant
    3. vérifie si ce mot est capitalized dans user_query (originale)
    4. si oui → is_identity_query=True → DOCUMENT_KEYWORD

    À noter :
    - 'qui est' minuscule trouvé même si l'utilisateur a écrit 'Qui est'
    - Le mot capitalized est vu via la query ORIGINALE (pas lowercased)
    """
    import re

    def is_identity(original_query: str, lowered_query: str) -> bool:
        m_gk = re.search(r"qui est\s+(\S+)", lowered_query)
        if not m_gk:
            return False
        next_word_lower = m_gk.group(1).rstrip("?!.,;:")
        pattern_next = re.escape(next_word_lower[:min(4, len(next_word_lower))])
        m_orig = re.search(pattern_next, original_query, re.IGNORECASE)
        if m_orig and m_orig.start() >= 4:
            return m_orig.group(0)[0].isupper()
        return False

    cases = [
        # (original, lowercased, attendu)
        ("Qui est Leblanc ?", "qui est leblanc ?", True),
        ("Qui est Bahiga ?", "qui est bahiga ?", True),
        ("Qui est Leblanc Bahiga ?", "qui est leblanc bahiga ?", True),
        ("Qui est le président ?", "qui est le président ?", False),
        ("Qui est Marie Curie ?", "qui est marie curie ?", True),
        ("Qui est la France ?", "qui est la france ?", False),
    ]
    for orig, low, expected in cases:
        actual = is_identity(orig, low)
        assert actual == expected, (
            f"Identity detection a échoué pour {orig!r}: "
            f"attendu {expected}, got {actual}"
        )
