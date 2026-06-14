"""
Routeur Sémantique Hybride V10.1 pour NURU.
Architecture 2-passes de l'audit :
1. Trivial (regex, 0ms) — salutations, identité
2. Patterns documentaires (instantané) — mots-clés CV/rapport/projet
3. Patterns connaissance générale (instantané) — maths, logique, sciences
4. Patterns web (instantané) — actualité, prix, météo
5. LLM Classification (~100ms) — cas ambigus
6. Spotlight (fichiers locaux)
7. Cloud Fallback
8. Clarification
"""
import logging
import re
import time
from typing import Optional
from dataclasses import dataclass

from src.infra.cache import TTLDecisionCache

logger = logging.getLogger(__name__)

# ── Prompt classification LLM (Passe 2) ───────────────────────────────────
# AUDIT-2026-06-14 V10.3 — S-001 P0 : sanitisation de la query avant interpolation
# pour éliminer le risque de prompt-injection via le passage LLM de classification.
from src.core.prompt_guard import sanitize_for_prompt_injection

_INJECTION_BOUNDARIES = ("Classe cette requête", "Réponse")  # seuls extraits du template, JAMAIS user-influencés

CLASSIFY_PROMPT = """Classe cette requête en UN seul mot :
- GENERAL : calcul, logique, définition, culture générale, conversation
- RAG : document personnel, CV, rapport, projet, fichier
- WEB : actualité, prix, météo, personne en poste

Requête : <<QUERY>>
Réponse (un seul mot) :"""


def build_classify_prompt(query: str) -> str:
    """Construit le prompt de classification LLM avec sanitation V10.3.

    - Tronque la query à 500 caractères (limite rationale : aucun classifieur n'a besoin de plus)
    - Neutralise les motifs d'injection connus (SYSTEM/INST/Ignore/etc.)
    - Remplace interroge par des délimiteurs stricts <<QUERY>> autour de la valeur sanitizée
    - Garantit qu'aucun contenu user ne peut faire sortir le modèle du cadre "un seul mot"
    """
    return CLASSIFY_PROMPT.replace("<<QUERY>>", sanitize_for_prompt_injection(query, max_chars=500))

# ── Patterns connaissance générale (Passe 1 — audit §7.1) ─────────────────
GENERAL_KNOWLEDGE_PATTERNS = [
    # Calculs arithmétiques / logiques
    r"(combien (font|fait|valent|vaut))",
    r"(quel(le)? est le résultat de)",
    r"\d+\s*[\+\-\*/]\s*\d+",
    # Jeux et logique abstraite
    r"\b(morpion|tic[- ]tac[- ]toe|échecs|dames|sudoku|puzzle)\b",
    # Demandes explicatives génériques (sans référent personnel/documentaire)
    r"(explique(-moi)?|qu['' ]est[- ]ce que|comment fonctionne|pourquoi (le|la|les|l['' ]))",
    r"\b(photosynthèse|évolution|relativité|gravité|atome|adn|big bang)\b",
    # Histoire / culture générale (sans "mon/ma/mes")
    r"(qui était|quand a eu lieu|où se trouve|qu['' ]est-il arrivé)",
]

# ── Patterns web (Passe 1 — audit §7.1) ──────────────────────────────────
WEB_SEARCH_PATTERNS = [
    r"\b(actuel(le)?ment|aujourd['' ]?hui|en ce moment|cette année|de nos jours)\b",
    r"(qui est|qui dirige|qui occupe le poste de).{0,30}(président|premier ministre|pdg|ceo|directeur)",
    r"(président|premier ministre).{0,30}(actuel|en exercice|de la|des|du)",
    r"(prix (actuel|du jour)|cours (actuel|du jour)|météo|température (actuelle)?)",
    r"(dernières? (nouvelles|actualités)|actualité|news)",
]

# ── Patterns documents (instantané) ────────────────────────────────────────
RAG_KEYWORDS = {
    "cv", "curriculum", "vitae", "lettre", "motivation", "candidature",
    "yarid", "iamgold", "iita", "fao", "usaid", "beaccom", "rikolto",
    "mon cv", "mon document", "mes notes", "mes fichiers",
    "diplôme", "diplome", "certificat", "attestation",
    "rapport", "présentation", "projet", "étude de base",
    "filière", "filiere", "walikale",
    "cherche dans", "trouve le fichier", "ouvre le document",
}

# ── Patterns triviaux (0 ms) ──────────────────────────────────────────────
TRIVIAL_PATTERNS = {
    r"^(bonjour|salut|hello|hi|coucou|hey|yo|merci|thanks|bonsoir|bye|aurevoir|au revoir|à demain|bonne nuit|bonne journée|bonne fin de semaine)\b": "SIMPLE",
    r"^(oui|non|ok|d'accord|daccord|super|parfait|cool|génial|nickel)\b": "SIMPLE",
    r"^(c['' ]?(est|était|etait) (bien|super|génial|nul|pas mal|sympa|intéressant)\b)": "SIMPLE",
    r"^(je (suis|va|vais) (bien|content|heureux|fatigué|occupé)\b)": "SIMPLE",
    r"^(qui (es-?tu|êtes-?vous|suis-?je))\b": "SIMPLE",
    r"^(tu es|vous êtes) qui\b": "SIMPLE",
    r"^(quelle est ton? (nom|identité|but|mission|rôle|fonction|objectif|créateur|auteur))\b": "SIMPLE",
    r"^(tu peux )?(répéter|répète|expliquer|clarifier|résumer|reformuler)\b": "SIMPLE",
}

# ── Seuils RAG (audit §7.1) ───────────────────────────────────────────────
# V10.2: centralisé dans config.rag_router_min_score (0.15)
from src.config import config as _nuru_config
RAG_SCORE_THRESHOLD = _nuru_config.rag_router_min_score


@dataclass
class RouterResult:
    decision: str = "SIMPLE"
    confidence: float = 1.0
    reasoning: str = ""
    processing_time_ms: float = 0.0
    rag_top_score: float = 0.0
    spotlight_context: str = ""


class SemanticRouter:
    """Routeur V10.1 : 2-passes (regex → LLM) avec gate de score RAG."""

    def __init__(self, rag_engine=None, is_online_check=None, cloud_llm=None):
        self.rag_engine = rag_engine
        self.cloud_llm = cloud_llm
        self.is_online = is_online_check or (lambda: True)
        self._cache = TTLDecisionCache(maxsize=256, ttl_seconds=300)
        self._spotlight = None
        try:
            from src.rag.spotlight import SpotlightSearch
            self._spotlight = SpotlightSearch()
        except Exception:
            pass

    def set_rag_engine(self, rag_engine):
        self.rag_engine = rag_engine

    async def route(self, user_query: str, context=None,
                     rag_context=None, rag_result=None) -> RouterResult:
        t_start = time.time()
        result = RouterResult()
        query_lower = user_query.strip().lower()

        # ══ N0 : CACHE ══
        cache_key = self._cache.make_key(query_lower)
        cached = self._cache.get(cache_key)
        if cached is not None:
            cached.processing_time_ms = (time.time() - t_start) * 1000
            return cached

        # ══ N1 : TRIVIAL (regex, 0 ms) ══
        for pattern, decision in TRIVIAL_PATTERNS.items():
            if re.match(pattern, query_lower):
                result.decision = decision
                result.reasoning = f"Trivial"
                result.processing_time_ms = (time.time() - t_start) * 1000
                self._cache.set(cache_key, result)
                return result

        # ══ N2 : PATTERNS (Passe 1 — audit §7.1) ══
        has_rag_kw = any(kw in query_lower for kw in RAG_KEYWORDS)
        has_gk = any(re.search(p, query_lower) for p in GENERAL_KNOWLEDGE_PATTERNS)
        has_web = any(re.search(p, query_lower) for p in WEB_SEARCH_PATTERNS)

        # 2a : Connaissance générale évidente SANS référent documentaire
        if has_gk and not has_rag_kw:
            result.decision = "GENERAL_KNOWLEDGE"
            result.confidence = 0.9
            result.reasoning = "Pattern connaissance générale"
            result.processing_time_ms = (time.time() - t_start) * 1000
            self._cache.set(cache_key, result)
            return result

        # 2b : Document keyword → RAG direct
        if has_rag_kw:
            result.decision = "DOCUMENT_KEYWORD"
            result.confidence = 0.9
            result.reasoning = "Document keyword"
            result.processing_time_ms = (time.time() - t_start) * 1000
            self._cache.set(cache_key, result)
            return result

        # 2c : Web trigger → cloud
        if has_web:
            result.decision = "CLOUD_GROQ"
            result.confidence = 0.8
            result.reasoning = "Web trigger"
            result.processing_time_ms = (time.time() - t_start) * 1000
            self._cache.set(cache_key, result)
            return result

        # ══ N3 : LLM CLASSIFICATION (Passe 2 — cas ambigus) ══
        if self.cloud_llm and self.is_online():
            try:
                intent = await self._classify_with_llm(user_query)
                logger.info(f"🧠 Router N3 (LLM) → {intent}: {query_lower[:50]}")

                if intent == "RAG":
                    # LLM dit RAG → essayer le RAG local avec gate de score
                    if rag_result is not None:
                        rag_ctx, rag_res = rag_context, rag_result
                    elif self.rag_engine is not None:
                        try:
                            rag_ctx, rag_res = await self.rag_engine.retrieve(user_query)
                        except Exception:
                            rag_ctx, rag_res = "", None
                    else:
                        rag_ctx, rag_res = "", None

                    if rag_res and rag_ctx and rag_res.top_score >= RAG_SCORE_THRESHOLD:
                        result.decision = "LOCAL_RAG"
                        result.confidence = rag_res.top_score
                        result.rag_top_score = rag_res.top_score
                        result.reasoning = f"LLM→RAG, score={rag_res.top_score:.2f}"
                    else:
                        # LLM dit RAG mais score trop faible → général
                        result.decision = "GENERAL_KNOWLEDGE"
                        result.confidence = 0.6
                        result.reasoning = f"LLM→RAG mais score insuffisant ({getattr(rag_res, 'top_score', 0):.2f})"

                elif intent == "WEB":
                    result.decision = "CLOUD_GROQ"
                    result.confidence = 0.8
                    result.reasoning = "LLM→WEB"
                else:  # GENERAL / SIMPLE
                    result.decision = "GENERAL_KNOWLEDGE"
                    result.confidence = 0.7
                    result.reasoning = f"LLM→{intent}"

                result.processing_time_ms = (time.time() - t_start) * 1000
                self._cache.set(cache_key, result)
                return result

            except Exception as e:
                logger.warning(f"Router N3: LLM classify failed: {e}")

        # ══ N4 : SPOTLIGHT ══
        if self._spotlight:
            try:
                spotlight_results = self._spotlight.search(user_query, max_results=5, read_content=True)
                if spotlight_results:
                    context_parts = []
                    for r in spotlight_results:
                        if r.content:
                            context_parts.append(f"[SOURCE: {r.filename}]\n{r.content}\n")
                    result.decision = "LOCAL_RAG"
                    result.confidence = 0.7
                    result.reasoning = f"Spotlight ({len(spotlight_results)} fichiers)"
                    result.processing_time_ms = (time.time() - t_start) * 1000
                    result.spotlight_context = "\n".join(context_parts)
                    self._cache.set(cache_key, result)
                    return result
            except Exception as e:
                logger.warning(f"Router N4: Spotlight erreur: {e}")

        # ══ N5 : CLOUD FALLBACK ══
        if self.is_online():
            result.decision = "CLOUD_GROQ"
            result.confidence = 0.5
            result.reasoning = "Fallback cloud"
            result.processing_time_ms = (time.time() - t_start) * 1000
            self._cache.set(cache_key, result)
            return result

        # ══ N6 : CLARIFICATION ══
        result.decision = "CLARIFICATION"
        result.confidence = 0.0
        result.reasoning = "Hors ligne"
        result.processing_time_ms = (time.time() - t_start) * 1000
        self._cache.set(cache_key, result)
        return result

    async def _classify_with_llm(self, query: str) -> str:
        """Classe l'intent via un appel LLM rapide (Groq)."""
        prompt = CLASSIFY_PROMPT.format(query=query)
        response = ""
        async for token in self.cloud_llm.generate_stream(
            prompt, intent="SIMPLE",
            system_prompt="Tu es un classificateur. Réponds uniquement par un seul mot.",
            temperature=0.0
        ):
            response += token
        response = response.strip().lower()
        for valid in ["general", "rag", "web", "simple"]:
            if valid in response:
                return valid.upper()
        return "GENERAL"

    async def route_with_context(self, ctx, rag_context=None, rag_result=None):
        """Route avec un QueryContext (compatibilité orchestrator)."""
        query = getattr(ctx, 'query', '') or getattr(ctx, 'text', '')
        return await self.route(query, rag_context=rag_context, rag_result=rag_result)
