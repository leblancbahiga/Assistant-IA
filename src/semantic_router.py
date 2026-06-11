"""
Routeur Sémantique Hybride pour NURU V4.
Remplace le simple IntentClassifier par un système à 5 niveaux :
1. Trivial Check (regex, 0 Mo RAM)
2. Web Trigger (mots-clés d'actualité — pas de RAG inutile)
3. Recherche RAG + Score de confiance
4. Cloud Fallback
5. Clarification
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

# Mots-clés pour le mode "trivial" (conversation simple, pas besoin de RAG)
TRIVIAL_PATTERNS = {
    # Salutations / remerciements / farewell
    r"^(bonjour|salut|hello|hi|coucou|hey|yo|merci|thanks|bonsoir|bye|aurevoir|au revoir|à demain|bonne nuit|bonne journée|bon week-end|bonne fin de semaine)\b": "SIMPLE",
    r"^(oui|non|ok|d'accord|daccord|super|parfait|cool|génial|nickel)\b": "SIMPLE",
    # Feedback / sentiment simple
    r"^(c['' ]?(est|était|etait) (bien|super|génial|nul|pas mal|sympa|intéressant)\b)": "SIMPLE",
    r"^((je (suis|va|vais) (bien|content|heureux|fatigué|occupé))\b)": "SIMPLE",
    # Identité (questions sur NURU lui-même)
    r"^(qui (es-?tu|êtes-?vous|suis-?je))\b": "SIMPLE",
    r"^((tu es|vous êtes) qui)\b": "SIMPLE",
    r"^(quelle est ton? (nom|identité|but|mission|rôle|fonction|objectif|créateur|auteur))\b": "SIMPLE",
    # Méta (demande de répétition, clarification)
    r"^((tu peux )?(répéter|répète|expliquer|clarifier|résumer|reformuler))\b": "SIMPLE",
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
    plan_branch: str = ""  # Trace de décision pour debugging

class SemanticRouter:
    """
    Routeur sémantique 4 niveaux conçu pour M1 8 Go.
    
    Niveau 1 - Trivial Check : patterns regex (0 Mo RAM, < 1 ms)
    Niveau 2 - RAG Confidence : embedding + search + reranker score
    Niveau 3 - Cloud Fallback : si RAG insuffisant mais internet disponible
    Niveau 4 - Clarification : si rien n'est trouvé
    """
    
    def __init__(self, rag_engine=None, is_online_check=None):
        self.rag_engine = rag_engine
        self.is_online = is_online_check or (lambda: True)
        # V4.5 Phase 0 : Cache TTL enfin actif (256 entrées, TTL 5 min)
        self._cache = TTLDecisionCache(maxsize=256, ttl_seconds=300)
        
    def set_rag_engine(self, rag_engine):
        """Injecte le moteur RAG après construction (injection de dépendances)."""
        self.rag_engine = rag_engine
    
    async def route(self, user_query: str, context: Optional[Dict] = None) -> RouterResult:
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
        # NIVEAU 2 : WEB TRIGGER (Actualité — pas de RAG inutile)
        # NURU V5 : priorité RAG — si mots-clés docs, on ignore les web triggers
        # Correction 7 : Regex \b pour éviter faux positifs (ex: "fao" dans "il faudrait")
        # ====================================
        rag_pattern = re.compile(r'\b(' + '|'.join(map(re.escape, RAG_KEYWORDS)) + r')\b', re.IGNORECASE)
        web_pattern = re.compile(r'\b(' + '|'.join(map(re.escape, WEB_TRIGGERS)) + r')\b', re.IGNORECASE)
        has_rag_keyword = bool(rag_pattern.search(query_lower))
        has_web_trigger = bool(web_pattern.search(query_lower))
        if has_web_trigger and not has_rag_keyword:
            result.decision = "CLOUD_GROQ"
            result.confidence = 0.8
            result.reasoning = f"Web trigger détecté"
            result.processing_time_ms = (time.time() - t_start) * 1000
            logger.info(f"🧠 Router N2 (Web Trigger) → CLOUD_GROQ: {query_lower[:50]}")
            self._cache.set(cache_key, result)
            return result
        
        # ====================================
        # NIVEAU 3 : RAG CONFIDENCE (Embedding + Search)
        # ====================================
        if self.rag_engine is not None:
            # Lancer la recherche RAG (non-bloquante)
            try:
                rag_context, rag_result = await self.rag_engine.retrieve(user_query)
                result.rag_top_score = rag_result.top_score
                
                # Debug logging pour comprendre le comportement
                logger.debug(
                    f"🧠 Router N3 (RAG): requête={query_lower[:40]} | "
                    f"top_score={rag_result.top_score:.2f} | "
                    f"chunks={rag_result.chunks_injected} | "
                    f"rejet={rag_result.rejection_reason or 'NON'} | "
                    f"mots-clés RAG={has_rag_keyword}"
                )
                
                # Décision basée sur le RAG
                if rag_context:
                    # Contexte RAG trouvé et validé
                    result.decision = "LOCAL_RAG"
                    result.confidence = rag_result.top_score
                    result.reasoning = f"RAG trouvé (top1={rag_result.top_score:.2f})"
                    result.processing_time_ms = (time.time() - t_start) * 1000
                    logger.info(f"🧠 Router N3 → LOCAL_RAG (top1={rag_result.top_score:.2f})")
                    self._cache.set(cache_key, result)
                    return result
                
                elif rag_result.rejection_reason and has_rag_keyword:
                    # Requête avec mots-clés RAG mais pas trouvé : on essaie quand même
                    # Peut-être que le document n'est pas indexé → passer au cloud
                    logger.warning(
                        f"🧠 Router N3: mots-clés RAG mais pas de docs trouvés "
                        f"(score={rag_result.top_score:.2f}). Tentative cloud..."
                    )
                    # On laisse continuer vers N4
                
            except Exception as e:
                logger.error(f"🧠 Router N3: Erreur RAG: {e}")
        
        # ====================================
        # NIVEAU 4 : CLOUD FALLBACK
        # ====================================
        if self.is_online():
            # Si la requête semble complexe (longueur, mots techniques, etc.)
            is_complex = len(user_query.split()) >= 8 or has_rag_keyword
            
            if is_complex or result.rag_top_score > 0.0:
                result.decision = "CLOUD_GROQ"
                result.confidence = 0.7
                result.reasoning = f"Requête {'complexe' if is_complex else 'RAG insuffisant'}"
                result.processing_time_ms = (time.time() - t_start) * 1000
                logger.info(
                    f"🧠 Router N3 → CLOUD_GROQ (complexe={is_complex}, "
                    f"RAG_score={result.rag_top_score:.2f})"
                )
                self._cache.set(cache_key, result)
                return result
            
            # Requête simple non-trivial : au cloud par défaut
            result.decision = "CLOUD_GROQ"
            result.confidence = 0.5
            result.reasoning = "Requête simple par défaut → Cloud"
            result.processing_time_ms = (time.time() - t_start) * 1000
            logger.debug(f"🧠 Router N3 → CLOUD_GROQ (simple)")
            self._cache.set(cache_key, result)
            return result
        
        # ====================================
        # NIVEAU 5 : CLARIFICATION (Hors ligne)
        # ====================================
        result.decision = "CLARIFICATION"
        result.confidence = 0.0
        result.reasoning = "Pas de documents locaux et pas d'accès Internet"
        result.processing_time_ms = (time.time() - t_start) * 1000
        logger.info(f"🧠 Router N4 → CLARIFICATION")
        self._cache.set(cache_key, result)
        return result
