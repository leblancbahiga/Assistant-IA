"""
NURU Kernel — Router Réduit (Phase 3.8).

Classifieur 5-bucket pur et simple.
Le Kernel ne répond jamais — le router ne fait que classifier.

Intents :
    GENERAL   — conversation libre, salutation, identité
    RAG       — question factuelle sur les documents indexés
    WEB       — actualité, recherche en ligne
    HYBRID    — besoin de RAG + web (question sur documents + actualité)
    TOOL      — action outil (code, calcul, runtime)

Principes :
    - Zéro appel LLM dans la décision de routage
    - Zéro stratégie hybride (c'est au pipeline de décider)
    - Zéro spotlight (c'est au step Retrieve)
    - Zéro policy engine (c'est au kernel state)
    - Cache TTL 5 minutes pour les requêtes identiques
    - Délègue à RouterV16 pour le scoring sémantique quand disponible
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class KernelRoute:
    """Résultat minimal du routeur.

    Champs :
        intent : GENERAL | RAG | WEB | HYBRID | TOOL
        confidence : score [0, 1]
        reasoning : debug court
        processing_time_ms : temps de classification
        from_cache : True si résultat en cache
    """
    intent: str = "GENERAL"
    confidence: float = 1.0
    reasoning: str = ""
    processing_time_ms: float = 0.0
    from_cache: bool = False


# ── Patterns triviaux (instantanés, 0 LLM) ─────────────────────

TRIVIAL_GENERAL = re.compile(
    r"^(bonjour|salut|coucou|hello|hey|merci|au revoir|bye"
    r"|qui es-tu|qui êtes-vous|tu t'appelles"
    r"|comment (vas?tu|allez?vous|ça va)"
    r"|ça va|oui|non|d'accord|ok|super|génial"
    r"|merci beaucoup|bonne journée|bonne soirée"
    r")\s*[.!?]*$",
    re.IGNORECASE,
)

TRIVIAL_TOOL = re.compile(
    r"^(calcule?\s|combien fait |exécute |lance |ouvre |"
    r"code |écris un programme| programme |"
    r"capture d'écran|screenshot|"
    r"terminal|commande |shell )",
    re.IGNORECASE,
)

TRIVIAL_WEB = re.compile(
    r"(actualité|météo|cours (de )?(bourse|action)|"
    r"taux de change|prix du |résultat (du )?(match|sport)|"
    r"dernières nouvelles|breaking news|"
    r"recherche google|cherche |trouve |"
    r"qu'est-ce qui se passe)",
    re.IGNORECASE,
)

TRIVIAL_RAG = re.compile(
    r"(rapport|document|fichier|cv|projet|"
    r"qu'a dit |que contient |extrait |"
    r"dans le document|dans le fichier|"
    r"parle-moi de |résume |synthèse)",
    re.IGNORECASE,
)


# ── Routeur Kernel ─────────────────────────────────────────────

class KernelRouter:
    """Routeur minimal 5-bucket.

    Architecture :
        1. Cache (TTL 300s)
        2. Patterns triviaux (0ms) — GENERAL, TOOL, WEB, RAG
        3. RouterV16 (si disponible) — scoring sémantique
        4. Keyword fallback — patterns basiques
        5. Cache + retour

    Usage :
        router = KernelRouter()
        route = router.route("Qui est Einstein ?")
        # KernelRoute(intent="RAG", confidence=0.85, ...)
    """

    def __init__(self, cache_size: int = 256, cache_ttl: float = 300.0):
        self._cache: dict[str, tuple[float, KernelRoute]] = {}
        self._cache_max = cache_size
        self._cache_ttl = cache_ttl
        self._v16: Any = None  # RouterV16, lazy

    @property
    def v16(self):
        """RouterV16 lazy (pas d'import au module level)."""
        if self._v16 is None:
            try:
                from src.routing.v16.router_v16 import RouterV16
                self._v16 = RouterV16()
            except Exception as e:
                logger.debug("⚠️ RouterV16 non disponible: %s", e)
                self._v16 = False  # Ne pas réessayer
        return self._v16 if self._v16 is not False else None

    # ── Routage principal ──────────────────────────────────────

    def route(self, query: str) -> KernelRoute:
        """Classifie une requête en intent 5-bucket.

        Args:
            query : Texte utilisateur brut

        Returns:
            KernelRoute avec intent, confidence, reasoning
        """
        t0 = time.perf_counter()
        q = query.strip().lower()

        # 1. Cache hit ?
        cache_key = q[:200]  # Limiter la taille de clé
        cached = self._check_cache(cache_key)
        if cached is not None:
            cached.from_cache = True
            return cached

        route = self._classify(q, query)

        route.processing_time_ms = (time.perf_counter() - t0) * 1000
        self._set_cache(cache_key, route)
        return route

    def _classify(self, q: str, original: str) -> KernelRoute:
        """Chaîne de classification.

        Ordre :
        1. Patterns triviaux (0 ms)
        2. RouterV16 (scoring sémantique, si disponible)
        3. Keyword fallback
        4. Default GENERAL
        """
        # ── N1 : Triviaux (instantané) ──
        # Salutations / conversations
        if TRIVIAL_GENERAL.match(q):
            return KernelRoute(intent="GENERAL", confidence=0.95,
                               reasoning="Trivial pattern → GENERAL")

        # Actions outils
        if TRIVIAL_TOOL.match(q):
            return KernelRoute(intent="TOOL", confidence=0.90,
                               reasoning="Trivial pattern → TOOL")

        # Web explicite
        if TRIVIAL_WEB.search(q):
            return KernelRoute(intent="WEB", confidence=0.85,
                               reasoning="Web keyword → WEB")

        # RAG explicite
        if TRIVIAL_RAG.search(q):
            return KernelRoute(intent="RAG", confidence=0.80,
                               reasoning="Document keyword → RAG")

        # ── N2 : RouterV16 (scoring sémantique) ──
        v16 = self.v16
        if v16 is not None:
            try:
                v16_decision = v16.route(original)
                intent = self._v16_intent(v16_decision.intent)
                # HIGH → garder la confiance, LOW → descendre
                confidence = v16_decision.confidence
                reasoning = f"V16 → {intent} (conf={confidence:.2f})"

                # Vérifier HYBRID (RAG + WEB combinés)
                if intent == "RAG" and self._has_web_signal(q):
                    intent = "HYBRID"
                    reasoning += " → HYBRID (RAG + web)"

                return KernelRoute(
                    intent=intent,
                    confidence=confidence,
                    reasoning=reasoning,
                )
            except Exception as e:
                logger.debug("⚠️ V16 route failed: %s", e)

        # ── N3 : Keyword fallback ──
        # RAG keywords
        rag_keywords = [
            "rapport", "document", "fichier", "cv", "projet",
            "résume", "synthèse", "extrait", "contenu",
            "que dit", "que contient", "parle-moi",
            "index", "recherche", "trouve dans",
        ]
        web_keywords = [
            "actualité", "news", "météo", "prix", "cours",
            "google", "internet", "en ligne", "site",
            "dernière", "récent", "tendance",
        ]
        tool_keywords = [
            "calcul", "code", "programme", "script",
            "terminal", "commande", "exécute", "lance",
        ]

        has_rag = any(kw in q for kw in rag_keywords)
        has_web = any(kw in q for kw in web_keywords)
        has_tool = any(kw in q for kw in tool_keywords)

        if has_rag and has_web:
            return KernelRoute(intent="HYBRID", confidence=0.65,
                               reasoning="Keyword fallback → HYBRID")
        if has_rag:
            return KernelRoute(intent="RAG", confidence=0.70,
                               reasoning="Keyword fallback → RAG")
        if has_web:
            return KernelRoute(intent="WEB", confidence=0.60,
                               reasoning="Keyword fallback → WEB")
        if has_tool:
            return KernelRoute(intent="TOOL", confidence=0.55,
                               reasoning="Keyword fallback → TOOL")

        # ── N4 : Default ──
        return KernelRoute(intent="GENERAL", confidence=0.50,
                           reasoning="Default → GENERAL")

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _v16_intent(v16_intent: str) -> str:
        """Mappe l'intent V16 vers les 5 buckets standard."""
        mapping = {
            "RAG": "RAG",
            "WEB": "WEB",
            "GENERAL": "GENERAL",
            "ACTION": "TOOL",
            "MULTI_ROUTE": "HYBRID",
            "COMPLEX": "HYBRID",
        }
        return mapping.get(v16_intent, "GENERAL")

    @staticmethod
    def _has_web_signal(q: str) -> bool:
        """Vérifie si la requête contient un signal web malgré le routage RAG."""
        web_signals = [
            "actualité", "récent", "dernier", "aujourd'hui",
            "cette semaine", "ce mois", "maintenant",
            "dernières nouvelles", "news",
        ]
        return any(s in q for s in web_signals)

    # ── Cache ──────────────────────────────────────────────────

    def _check_cache(self, key: str) -> Optional[KernelRoute]:
        now = time.monotonic()
        entry = self._cache.get(key)
        if entry is not None and now - entry[0] < self._cache_ttl:
            return entry[1]
        return None

    def _set_cache(self, key: str, route: KernelRoute) -> None:
        # Éviter les fuites mémoire
        if len(self._cache) >= self._cache_max:
            # Supprimer la plus vieille entrée
            oldest = min(self._cache.keys(), key=lambda k: self._cache[k][0])
            del self._cache[oldest]
        self._cache[key] = (time.monotonic(), route)

    def clear_cache(self) -> None:
        """Vide le cache de routage."""
        self._cache.clear()
        logger.debug("🧹 Cache routeur vidé")

    # ── Cycle de vie kernel ────────────────────────────────────

    def start(self) -> None:
        logger.info("🧭 KernelRouter prêt")

    def stop(self) -> None:
        self.clear_cache()
        logger.info("🧭 KernelRouter arrêté")

    def __repr__(self) -> str:
        return f"<KernelRouter cache={len(self._cache)}>"
