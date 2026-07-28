"""Routeur unifié V12 — Fusion SemanticRouter + Router."""
import enum
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

from src.infra.cache import TTLDecisionCache
from src.core.prompt_guard import sanitize_for_prompt_injection
from src.core.policies import PolicyEngine
from src.core.query_context import QueryContext

logger = logging.getLogger(__name__)

# ── Prompt classification LLM (Passe 2) ───────────────────────────────────
# AUDIT-2026-06-14 V10.3 — S-001 P0 : sanitisation de la query avant interpolation
# pour éliminer le risque de prompt-injection via le passage LLM de classification.

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
    # V12.1 — Questions personnelles sur l'utilisateur
    "leblanc", "bahiga", "mudarhi",
    "mon profil", "ma bio", "qui suis-je", "qui suis je",
    "parle-moi de moi", "parle moi de moi",
    "mes infos", "informations personnelles",
}

# ── Patterns triviaux (0 ms) ──────────────────────────────────────────────
TRIVIAL_PATTERNS = {
    r"^(bonjour|salut|hello|hi|coucou|hey|yo|merci|thanks|bonsoir|bye|aurevoir|au revoir|à demain|bonne nuit|bonne journée|bonne fin de semaine)\b": "SIMPLE",
    r"^(oui|non|ok|d'accord|daccord|super|parfait|cool|génial|nickel)\b": "SIMPLE",
    r"^(c['' ]?(est|était|etait) (bien|super|génial|nul|pas mal|sympa|intéressant)\b)": "SIMPLE",
    r"^(je (suis|va|vais) (bien|content|heureux|fatigué|occupé)\b)": "SIMPLE",
    r"^(qui (es-?tu|êtes-?vous))\b": "SIMPLE",  # NOTA: "qui suis-je" → RAG via mots-clés
    r"^(tu es|vous êtes) qui\b": "SIMPLE",
    r"^(quelle est ton? (nom|identité|but|mission|rôle|fonction|objectif|créateur|auteur))\b": "SIMPLE",
    r"^(tu peux )?(répéter|répète|expliquer|clarifier|résumer|reformuler)\b": "SIMPLE",
    # "qui suis-je" est traité plus bas par les mots-clés RAG (documents personnels)
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
    hybrid_strategy: Optional[str] = None  # V6: ajouté par Router


class HybridStrategy(enum.Enum):
    """Stratégies hybrides local+cloud inspirées d'OpenJarvis.

    LOCAL_ONLY          : tout en local (défaut V5)
    LOCAL_CLOUD_VERIFY  : Phi-4-mini répond, Groq vérifie et corrige
    CLOUD_PLAN_LOCAL    : Groq planifie les étapes, Phi-4-mini exécute
    LOCAL_RAG_CLOUD     : RAG locale récupère, Groq synthétise (Archon)
    """
    LOCAL_ONLY = "local_only"
    LOCAL_CLOUD_VERIFY = "verify"
    CLOUD_PLAN_LOCAL = "plan"
    LOCAL_RAG_CLOUD = "rag"

    @classmethod
    def from_config(cls, mode: str):
        """Parse une string config en HybridStrategy."""
        mapping = {
            "local_only": cls.LOCAL_ONLY,
            "verify": cls.LOCAL_CLOUD_VERIFY,
            "plan": cls.CLOUD_PLAN_LOCAL,
            "rag": cls.LOCAL_RAG_CLOUD,
        }
        return mapping.get(mode, cls.LOCAL_ONLY)


class Router:
    """Routeur unifié V12 — Patterns + LLM + Spotlight + PolicyEngine.

    Fusion de SemanticRouter (src/semantic_router.py) et Router (src/core/router.py).

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

    def __init__(self, rag_engine=None, is_online_check=None,
                 cloud_llm=None, policy_engine=None, hybrid_mode="local_only"):
        self.rag_engine = rag_engine
        self.cloud_llm = cloud_llm
        async def _always_online() -> bool:
            return True
        self.is_online = is_online_check or _always_online
        self._cache = TTLDecisionCache(maxsize=256, ttl_seconds=300)
        self._spotlight = None
        try:
            from src.rag.spotlight import SpotlightSearch
            self._spotlight = SpotlightSearch()
        except Exception:
            pass
        self.policy_engine = policy_engine or PolicyEngine()
        self.hybrid_strategy = HybridStrategy.from_config(hybrid_mode)

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
        # AUDIT V10.3k — B-Routing-QuiEst : "Qui est [Nom Propre] ?" matchait GENERAL_KNOWLEDGE
        # via le pattern "qui est", même quand la requête cible l'identité de l'utilisateur
        # (Leblanc, etc.). On détecte spécifiquement "qui est" (en query_lower pour matcher
        # la casse, suivi d'un Mot capitalized DANS LA user_query ORIGINALE — pas lowercased —
        # pour identifier un nom propre. Si oui → RAG probable (identité personnelle).
        m_gk = re.search(r"qui est\s+(\S+)", query_lower)
        is_identity_query = False
        if m_gk:
            next_word_lower = m_gk.group(1).rstrip("?!.,;:")  # sans ponctuation
            # V17: si le nom est une personnalite publique connue, pas du RAG
            KNOWN_PUBLIC_FIGURES = (
                "tshisekedi", "kabila", "lumumba", "muzito", "kamerhe",
                "macron", "poutine", "biden", "trump", "merkel",
                "président", "presidente", "premier ministre", "roi", "reine",
            )
            if next_word_lower in KNOWN_PUBLIC_FIGURES or any(
                f"{next_word_lower} {fig}".strip()
                for fig in ("président", "premier ministre", "ministre", "sénateur")
            ):
                is_identity_query = False
            else:
                # Trouver ce mot dans la user_query ORIGINALE pour récupérer sa casse
                pattern_next = re.escape(next_word_lower[:min(4, len(next_word_lower))])
                m_orig = re.search(pattern_next, user_query, re.IGNORECASE)
                if m_orig and m_orig.start() >= 4:  # bien après "qui est"
                    next_word_original = m_orig.group(0)
                    if next_word_original[0].isupper():
                        is_identity_query = True
        # Si on a matché un nom propre, override GENERAL → RAG
        if has_gk and is_identity_query and not has_rag_kw:
            has_gk_unless_identity = False
        else:
            has_gk_unless_identity = has_gk

        # 2a : Connaissance générale évidente SANS référent documentaire
        if has_gk_unless_identity and not has_rag_kw:
            result.decision = "GENERAL_KNOWLEDGE"
            result.confidence = 0.9
            result.reasoning = "Pattern connaissance générale"
            result.processing_time_ms = (time.time() - t_start) * 1000
            self._cache.set(cache_key, result)
            return result

        # 2b : Document keyword → RAG direct
        if has_rag_kw or is_identity_query:
            result.decision = "DOCUMENT_KEYWORD"
            result.confidence = 0.9
            result.reasoning = (
                "Document keyword OR identity query (Qui est [Nom])"
            )
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
        if self.cloud_llm and await self.is_online():
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
        if await self.is_online():
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
        prompt = build_classify_prompt(query)
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

    async def route_with_context(self, ctx: QueryContext, rag_context: Optional[str] = None,
                                  rag_result=None) -> RouterResult:
        """Route en utilisant un QueryContext pour les décisions RAM-dépendantes.

        Ajoute les informations de stratégie hybride dans le résultat.
        V10 : Spotlight contourne l'escalade RAM (pas de LLM, léger).
        V10 Audit: Accepte un rag_context/rag_result pré-calculé pour éviter
        le double appel retrieve().
        """
        result = await self.route(ctx.query, rag_context=rag_context, rag_result=rag_result)

        # V10 : Spotlight ne déclenche JAMAIS l'escalade Cloud
        # (Spotlight = mdfind, pas de LLM, pas de RAM nécessaire)
        is_spotlight = result.spotlight_context != ""

        # V10 Expert fix: Spotlight bypass — si Spotlight a trouvé du contenu,
        # forcer LOCAL_ONLY quel que soit l'état RAM
        if is_spotlight and len(result.spotlight_context) > 500:
            logger.info(
                f"🔍 Spotlight bypass: {len(result.spotlight_context)} chars trouvés "
                f"→ forçage LOCAL_ONLY (pas d'escalade Cloud)"
            )
            # Ne pas changer la décision (déjà LOCAL_RAG depuis N4)
            return result

        # Escalade cloud si RAM trop basse (sauf si c'est du Spotlight)
        # V16 FIX: Pour les requêtes RAG documentaires, ON FORCE le local.
        # Le fallback Cloud ne doit se déclencher QUE si le serveur local est 
        # physiquement arrêté (ConnectionError), pas si la RAM est basse.
        # Sur M1 8Go, le swap est lent mais FONCTIONNE - ne pas basculer sur cloud.
        # V17: LOCAL_RAG ne bascule JAMAIS vers Cloud — le LoRA RAG adapter
        # n'est chargé que sur le local. Envoyer une requête RAG vers Cloud
        # = perdre le bénéfice du fine-tuning LoRA.
        if result.decision == "LOCAL_RAG" and not is_spotlight:
            if self.policy_engine.should_use_cloud(ctx):
                logger.info(
                    f"🔒 V17: LOCAL_RAG maintenu (swap OK) — "
                    f"le LoRA RAG adapter est local ({ctx.ram_free_mb} MB RAM)"
                )
                # V17: PLUS JAMAIS d'escalade Cloud pour LOCAL_RAG.
                # Le swap M1 est lent mais fonctionne, et le LoRA ne charge pas sur Cloud.
                # Si le local crash, ce sera catché par LLMGenerator → fallback Cloud.
                pass
            # Spotlight bypass inchangé
        elif is_spotlight:
            logger.info(f"🔍 Router: Spotlight actif → pas d'escalade RAM")

        # Stratégie hybride : enrichir le résultat
        result.hybrid_strategy = self.hybrid_strategy.value
        result.reasoning += f" | hybrid:{self.hybrid_strategy.value}"

        return result

    def set_hybrid_strategy(self, mode: str):
        """Change la stratégie hybride à la volée."""
        self.hybrid_strategy = HybridStrategy.from_config(mode)
        logger.info(f"🔄 Router: stratégie hybride → {self.hybrid_strategy.value}")
