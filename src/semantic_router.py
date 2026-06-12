"""
Routeur Sémantique Hybride pour NURU V10.
Système à 6 niveaux — TOUJOURS essaie RAG d'abord (plus de mots-clés codés en dur) :
1. Trivial Check (regex, 0 Mo RAM)
2. Web Trigger (mots-clés d'actualité — pas de RAG inutile)
3. RAG d'abord (toujours — notre index)
4. Spotlight (tous les fichiers de l'ordinateur via mdfind)
5. Cloud Fallback
6. Clarification
Décisions : SIMPLE | WEB | LOCAL_RAG | CLOUD_GROQ | CLARIFICATION
"""
import logging
import re
import time
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass, field

# V4.5 Phase 0 : Cache routeur enfin actif avec TTL
from src.infra.cache import TTLDecisionCache

logger = logging.getLogger(__name__)

# ── Prompt de classification LLM (V10.1) ─────────────────────────────────
CLASSIFY_PROMPT = """Classe cette requête en UN seul mot parmi ces catégories :
- SIMPLE : calcul, logique, définition, culture générale, conversation, opinion, conseil
- RAG : demande spécifique sur un document personnel, CV, rapport, projet, fichier
- WEB : information temps réel, actualité, prix, météo, personne publique en poste

Requête : "{query}"
Réponse (un seul mot) :"""

# Mots-clés pour le mode "trivial" (conversation simple, pas besoin de RAG)
TRIVIAL_PATTERNS = {
    # Salutations / remerciements / farewell
    r"^(bonjour|salut|hello|hi|coucou|hey|yo|merci|thanks|bonsoir|bye|aurevoir|au revoir|à demain|bonne nuit|bonne journée|bonne fin de semaine)\\b": "SIMPLE",
    r"^(oui|non|ok|d'accord|daccord|super|parfait|cool|génial|nickel)\\b": "SIMPLE",
    # Feedback / sentiment simple
    r"^(c['' ]?(est|était|etait) (bien|super|génial|nul|pas mal|sympa|intéressant)\\b)": "SIMPLE",
    r"^(je (suis|va|vais) (bien|content|heureux|fatigué|occupé)\\b)": "SIMPLE",
    # Identité (questions sur NURU lui-même)
    r"^(qui (es-?tu|êtes-?vous|suis-?je))\\b": "SIMPLE",
    r"^(tu es|vous êtes) qui\\b": "SIMPLE",
    r"^(quelle est ton? (nom|identité|but|mission|rôle|fonction|objectif|créateur|auteur))\\b": "SIMPLE",
    # Méta (demande de répétition, clarification)
    r"^(tu peux )?(répéter|répète|expliquer|clarifier|résumer|reformuler)\\b": "SIMPLE",
    # V10.1 : Maths / calculs / logique / connaissance générale
    r"(calcul|multipli|additionne|soustrai|divise|racine carrée|pourcentage)": "SIMPLE",
    r"(\\d+[\\.,]?\\d*\\s*[×x\\*\\/]\\s*\\d+[\\.,]?\\d*)": "SIMPLE",  # 12x12, 12.5×3
    r"(quel est le résultat|quel résultat|combien.font|que donne)": "SIMPLE",
    r"(énigme|puzzle|devinette|logique|taux|tasse sans fond)": "SIMPLE",
    r"(défini|définition|qu'est-ce que|qui est|c'est quoi|signifie)": "SIMPLE",
    r"(histoire de|explique|décris|compar|différence entre)": "SIMPLE",
    r"(comment fonctionne|pourquoi|comment)": "SIMPLE",
}

# Mots-clés pour les requêtes qui nécessitent absolument du RAG (documents personnels)
RAG_KEYWORDS = {
    "cv", "curriculum", "vitae", "lettre", "motivation", "candidature", "postuler",
    "poste", "emploi", "travail", "job", "recrutement", "recrute",
    "yarid", "iamgold", "iita", "fao", "usaid", "beaccom", "rikolto",
    "mon cv", "mon document", "mes notes", "mes fichiers", "mes pdf",
    "diplôme", "diplome", "certificat", "attestation", "formation",
    "rapport", "présentation", "projet", "étude", "étude de base",
    "filière", "filiere", "riz", "walikale", "agriculture",
    "cherche dans", "trouve le fichier", "ouvre le document",
    "document de", "fichier de", "note de", "dossier",
    "parle-moi de", "raconte-moi", "qu'est-ce que", "qui est",
    "donne-moi", "montre-moi", "resume", "résume",
}

# Mots-clés d'actualité/temporels qui déclenchent le Web direct (pas de RAG)
# NURU V5 : retiré les années (2024-2028), "dernier", "nouvelle" — polluaient le routage RAG
WEB_TRIGGERS = {
    "actuel", "actuellement",
    "aujourd'hui", "aujourd hui",
    "en ce moment",
    "qui est le", "qui est la",
    "quel est le prix", "quel est le",
    "météo", "température",
    "président de", "président des",
    "premier ministre",
    "actualité", "actualites",
}

@dataclass
class RouterResult:
    decision: str = "SIMPLE"  # SIMPLE | WEB | LOCAL_RAG | CLOUD_GROQ | CLARIFICATION
    confidence: float = 1.0
    reasoning: str = ""
    processing_time_ms: float = 0.0
    rag_top_score: float = 0.0
    spotlight_context: str = ""  # Contexte Spotlight lu pour le prompt
    plan_branch: str = ""  # Trace de décision pour debugging

class SemanticRouter:
    """
    Routeur sémantique 4 niveaux conçu pour M1 8 Go.
    
    Niveau 1 - Trivial Check : patterns regex (0 Mo RAM, < 1 ms)
    Niveau 2 - LLM Classification : compréhension sémantique via Groq (~100 ms)
    Niveau 3 - RAG : recherche dans l'index local
    Niveau 4 - Cloud Fallback : si rien trouvé
    Niveau 5 - Clarification : si hors ligne
    """
    
    def __init__(self, rag_engine=None, is_online_check=None, cloud_llm=None):
        self.rag_engine = rag_engine
        self.cloud_llm = cloud_llm  # V10.1 : pour classification LLM
        self.is_online = is_online_check or (lambda: True)
        # V4.5 Phase 0 : Cache TTL enfin actif (256 entrées, TTL 5 min)
        self._cache = TTLDecisionCache(maxsize=256, ttl_seconds=300)
        # V10 : Spotlight search (tous les fichiers de l'ordinateur)
        self._spotlight = None
        self._spotlight_context = ""  # Contexte Spotlight pour le prompt
        try:
            from src.rag.spotlight import SpotlightSearch
            self._spotlight = SpotlightSearch()
            logger.info("🧠 Router: Spotlight initialisé (macOS mdfind)")
        except Exception as e:
            logger.debug(f"🧠 Router: Spotlight non disponible: {e}")
        
    def set_rag_engine(self, rag_engine):
        """Injecte le moteur RAG après construction (injection de dépendances)."""
        self.rag_engine = rag_engine
    
    async def route(self, user_query: str, context: Optional[Dict] = None,
                     rag_context: Optional[str] = None,
                     rag_result=None) -> RouterResult:
        """
        Route une requête utilisateur vers le bon modèle de réponse.
        
        Args:
            user_query: La requête de l'utilisateur (nettoyée, en minuscule)
            context: Contexte optionnel (historique, état de la session)
        
        Returns:
            RouterResult avec la décision et sa raison
        """
        t_start = time.time()
        result = RouterResult()
        query_lower = user_query.strip().lower()

        # ====================================
        # NIVEAU 0 : CACHE (V4.5 Phase 0 — enfin actif)
        # ====================================
        cache_key = self._cache.make_key(query_lower)
        cached = self._cache.get(cache_key)
        if cached is not None:
            cached.processing_time_ms = (time.time() - t_start) * 1000
            logger.debug(f"🧠 Router Cache HIT → {cached.decision} pour {query_lower[:50]}")
            return cached

        # ====================================
        # NIVEAU 1 : TRIVIAL CHECK (0 Mo RAM)
        # ====================================
        for pattern, decision in TRIVIAL_PATTERNS.items():
            if re.match(pattern, query_lower):
                result.decision = decision
                result.reasoning = f"Match pattern trivial: {pattern[:30]}..."
                result.processing_time_ms = (time.time() - t_start) * 1000
                logger.debug(f"🧠 Router N1 (Trivial) → {decision}: {query_lower[:50]}")
                self._cache.set(cache_key, result)
                return result
        
        # ====================================
        # NIVEAU 2 : RAG KEYWORDS (instantané)
        # ====================================
        doc_indicators = ['beaccom', 'yarid', 'rikolto', 'rapport', 'cv', 'document', 
                         'fichier', 'projet', 'étude', 'proposition', 'contrat', 'facture']
        has_doc_term = any(term in query_lower for term in doc_indicators)
        
        if has_doc_term:
            result.decision = "LOCAL_RAG"
            result.confidence = 0.9
            result.reasoning = "Document keyword match"
            result.processing_time_ms = (time.time() - t_start) * 1000
            self._cache.set(cache_key, result)
            return result
        
        # ====================================
        # NIVEAU 3 : LLM CLASSIFICATION (~100ms via Groq)
        # V10.1 : Le LLM comprend le sens de la requête
        # ====================================
        if self.cloud_llm and self.is_online():
            try:
                intent = await self._classify_with_llm(user_query)
                logger.info(f"🧠 Router N3 (LLM) → {intent}: {query_lower[:50]}")
                
                if intent == "RAG":
                    # LLM dit RAG → essayer le RAG local
                    if rag_result is not None:
                        rag_context_local, rag_result_local = rag_context, rag_result
                    elif self.rag_engine is not None:
                        try:
                            rag_context_local, rag_result_local = await self.rag_engine.retrieve(user_query)
                        except Exception:
                            rag_context_local, rag_result_local = "", None
                    else:
                        rag_context_local, rag_result_local = "", None
                    
                    if rag_result_local and rag_result_local.top_score > 0.3:
                        result.decision = "LOCAL_RAG"
                        result.confidence = rag_result_local.top_score
                        result.rag_top_score = rag_result_local.top_score
                        result.reasoning = f"LLM→RAG, score={rag_result_local.top_score:.2f}"
                    else:
                        # LLM dit RAG mais score faible → cloud quand même
                        result.decision = "CLOUD_GROQ"
                        result.confidence = 0.5
                        result.reasoning = f"LLM→RAG mais score faible ({getattr(rag_result_local, 'top_score', 0):.2f})"
                
                elif intent == "WEB":
                    result.decision = "CLOUD_GROQ"
                    result.confidence = 0.8
                    result.reasoning = "LLM→WEB (actualité)"
                
                else:  # SIMPLE
                    result.decision = "CLOUD_GROQ"
                    result.confidence = 0.7
                    result.reasoning = f"LLM→{intent} (réponse générale)"
                
                result.processing_time_ms = (time.time() - t_start) * 1000
                self._cache.set(cache_key, result)
                return result
                
            except Exception as e:
                logger.warning(f"🧠 Router N3: LLM classify failed: {e}")
        
        # ====================================
        # NIVEAU 4 : SPOTLIGHT (fichiers locaux)
        # ====================================
        if self._spotlight:
            try:
                spotlight_results = self._spotlight.search(user_query, max_results=5, read_content=True)
                if spotlight_results:
                    context_parts = []
                    for r in spotlight_results:
                        if r.content:
                            context_parts.append(f"[SOURCE: {r.filename}]\n{r.content}\n")
                        else:
                            context_parts.append(f"[SOURCE: {r.filename}] (contenu non lisible)\n")
                    result.decision = "LOCAL_RAG"
                    result.confidence = 0.7
                    result.reasoning = f"Spotlight ({len(spotlight_results)} fichiers)"
                    result.processing_time_ms = (time.time() - t_start) * 1000
                    result.spotlight_context = "\n".join(context_parts)
                    self._cache.set(cache_key, result)
                    return result
            except Exception as e:
                logger.warning(f"🧠 Router N4: Spotlight erreur: {e}")
        
        # ====================================
        # NIVEAU 5 : CLOUD FALLBACK
        # ====================================
        if self.is_online():
            result.decision = "CLOUD_GROQ"
            result.confidence = 0.5
            result.reasoning = "Fallback cloud"
            result.processing_time_ms = (time.time() - t_start) * 1000
            logger.info(f"🧠 Router N5 → CLOUD_GROQ")
            self._cache.set(cache_key, result)
            return result
        
        # ====================================
        # NIVEAU 6 : CLARIFICATION (Hors ligne)
        # ====================================
        result.decision = "CLARIFICATION"
        result.confidence = 0.0
        result.reasoning = "Pas de documents locaux et pas d'accès Internet"
        result.processing_time_ms = (time.time() - t_start) * 1000
        logger.info(f"🧠 Router N6 → CLARIFICATION")
        self._cache.set(cache_key, result)
        return result

    async def _classify_with_llm(self, query: str) -> str:
        """Classe l'intent via un appel LLM rapide (Groq, ~100ms)."""
        prompt = CLASSIFY_PROMPT.format(query=query)
        response = ""
        async for token in self.cloud_llm.generate_stream(
            prompt, intent="SIMPLE",
            system_prompt="Tu es un classificateur. Réponds uniquement par un seul mot.",
            temperature=0.0
        ):
            response += token
        
        response = response.strip().lower()
        for valid in ["simple", "rag", "web"]:
            if valid in response:
                return valid.upper()
        return "SIMPLE"  # défaut

    async def route_with_context(self, ctx, rag_context=None, rag_result=None):
        """Route en utilisant un QueryContext (compatibilité orchestrator)."""
        query = getattr(ctx, 'query', '') or getattr(ctx, 'text', '')
        return await self.route(query, rag_context=rag_context, rag_result=rag_result)
