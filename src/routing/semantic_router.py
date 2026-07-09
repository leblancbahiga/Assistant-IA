"""
NURU V15 — Semantic Router ultra-léger (P1 #43).

Classification d'intention 100 % locale par mots-clés pondérés + patterns.
Remplace l'étape N3 (classification LLM ~100ms) du Router V12 par
un classifieur instantané (0.5-2ms sur M1), zéro appel cloud.

Intents supportés :
  - RAG     : questions sur documents personnels, CV, projets, utilisateur
  - GENERAL : culture générale, calculs, explications, définitions
  - WEB     : actualité, prix, météo, personnes en poste
  - SIMPLE  : salutations, remerciements, identité, feedback

Usage :
    router = SemanticRouter()
    route = router.route("Quel est le projet Yarid ?")
    # → SemanticRoute(intent="RAG", confidence=0.95, ...)
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Types
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class SemanticRoute:
    """Résultat de classification sémantique ultra-légère.

    Attributes:
        intent:       Intention détectée (RAG|GENERAL|WEB|SIMPLE)
        confidence:   Score de confiance [0, 1]
        breakdown:    Scores détaillés par intent (diagnostic)
        processing_ms: Temps de classification en ms
        reasoning:    Raison courte de la décision
    """
    intent: str = "GENERAL"
    confidence: float = 0.0
    breakdown: dict[str, float] = field(default_factory=dict)
    processing_ms: float = 0.0
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "confidence": round(self.confidence, 3),
            "breakdown": {k: round(v, 3) for k, v in self.breakdown.items()},
            "processing_ms": round(self.processing_ms, 1),
            "reasoning": self.reasoning,
        }


# ═══════════════════════════════════════════════════════════════════════
# Patterns triviaux (0 ms)
# ═══════════════════════════════════════════════════════════════════════

# Chaque pattern regex → intent correspondant.
# Utilise re.match (début de chaîne) pour les salutations et feedbacks.
TRIVIAL_PATTERNS: dict[str, str] = {
    r"^(bonjour|salut|hello|hi|coucou|hey|yo)\b": "SIMPLE",
    r"^(merci|thanks|merci beaucoup|merci bien)\b": "SIMPLE",
    r"^(bonsoir|bonne nuit|bonne journée|bonne soirée|à demain|bye|aurevoir|au revoir|ciao)\b": "SIMPLE",
    r"^(oui|non|ok|d'accord|daccord|super|parfait|cool|génial|nickel|top)\b": "SIMPLE",
    r"^(c['' ]?(est|était|etait) (bien|super|génial|nul|pas mal|sympa|intéressant))\b": "SIMPLE",
    r"^(je (suis|va|vais) (bien|content|heureux|fatigué|occupé))\b": "SIMPLE",
    r"^(qui (es-?tu|êtes-?vous|est[- ]?tu|est[- ]?ce|est ce))\b": "SIMPLE",
    r"^(tu es|vous êtes) qui\b": "SIMPLE",
    r"^(quelle est (ton?|ta) (nom|identité|but|mission|rôle|fonction|objectif|créateur|auteur))\b": "SIMPLE",
    r"^(tu peux )?(répéter|répète|expliquer|clarifier|résumer|reformuler)\b": "SIMPLE",
}


# ═══════════════════════════════════════════════════════════════════════
# Mots-clés pondérés par intention
# ═══════════════════════════════════════════════════════════════════════

# Poids : 3 = discriminant fort, 2 = modéré, 1 = faible
# Les mots-clés longs et spécifiques ont un poids plus élevé car
# ils sont moins ambigus.

INTENT_KEYWORDS: dict[str, dict[str, int]] = {
    "RAG": {
        # Documents professionnels
        "cv": 3, "curriculum": 3, "vitae": 3,
        "lettre": 3, "motivation": 3, "candidature": 3,
        "diplôme": 3, "diplome": 3, "certificat": 3, "attestation": 3,
        "rapport": 2, "présentation": 2, "presentation": 2,
        "projet": 2, "fichier": 2, "document": 2,
        # Projets spécifiques
        "yarid": 3, "iamgold": 3,
        "walikale": 3, "beaccom": 3, "rikolto": 3,
        "iita": 3, "fao": 3, "usaid": 3,
        "filière": 2, "filiere": 2,
        # Recherche documentaire
        "cherche dans": 2, "trouve le fichier": 2,
        "ouvre le document": 2, "trouve le document": 2,
        "cherche": 1, "trouve": 1,
        # Identité utilisateur (Leblanc)
        "leblanc": 3, "bahiga": 3, "mudarhi": 3,
        "mon profil": 3, "ma bio": 3,
        "qui suis-je": 3, "qui suis je": 3,
        "parle-moi de moi": 3, "parle moi de moi": 3,
        "mes infos": 3, "informations personnelles": 3,
        # Études de base / enquêtes
        "étude de base": 3, "etude de base": 3,
        "enquête": 2, "enquete": 2, "sondage": 2,
        # Réunions / comptes-rendus
        "compte-rendu": 2, "compte rendu": 2, "cr réunion": 2,
        "procès-verbal": 2, "proces verbal": 2, "pv": 1,
    },
    "GENERAL": {
        # Questions explicatives
        "pourquoi": 2, "comment": 2, "explique": 2,
        "qu'est-ce": 2, "qu'est ce": 2,
        "fonctionne": 2, "définition": 2, "definition": 2,
        "signifie": 2, "veut dire": 2,
        # Sciences / concepts
        "photosynthèse": 2, "photosynthese": 2,
        "évolution": 2, "evolution": 2,
        "relativité": 2, "relativite": 2,
        "gravité": 2, "gravite": 2,
        "atome": 2, "adn": 2,
        "big bang": 2,
        # Histoire
        "qui était": 2, "qui etait": 2,
        "quand a eu lieu": 2,
        "histoire": 1,
        # Calculs
        "combien": 2, "calcul": 2, "calcule": 2,
        "résultat": 1, "resultat": 1,
        "addition": 2, "soustraction": 2, "multiplication": 2, "division": 2,
        # Jeux / logique
        "morpion": 2, "échecs": 2, "echecs": 2,
        "dames": 1, "sudoku": 2, "puzzle": 2,
        # Culture générale
        "où se trouve": 2, "ou se trouve": 2,
        "taille": 1, "population": 1, "capitale": 2,
        "langue": 1, "religion": 1,
        # Concepts abstraits
        "sens de la vie": 2, "différence entre": 2, "difference entre": 2,
        "avantage": 1, "inconvénient": 1, "inconvenient": 1,
    },
    "WEB": {
        # Temporalité
        "actuel": 2, "actuelle": 2, "actuellement": 2,
        "aujourd'hui": 2, "aujourd hui": 2,
        "en ce moment": 2, "cette année": 2, "cette annee": 2,
        "de nos jours": 2, "récent": 2, "recent": 2,
        "dernier": 1, "dernière": 1, "derniere": 1,
        "nouveau": 1, "nouvelle": 1,
        # Personnalités actuelles
        "président": 2, "president": 2,
        "premier ministre": 2, "pdg": 2, "ceo": 2,
        "directeur": 1, "directrice": 1,
        "actuel président": 3, "actuel president": 3,
        # Métriques temps réel
        "prix": 2, "cours": 2,
        "météo": 3, "meteo": 3,
        "température": 2, "temperature": 2,
        "météorologique": 3, "meteorologique": 3,
        # Actualités
        "actualité": 2, "actualite": 2, "actualités": 2, "actualites": 2,
        "news": 2, "nouvelle": 1,
        # Économie
        "bourse": 2, "taux": 2, "inflation": 2,
        "dollar": 1, "euro": 1,
    },
    "SIMPLE": {
        # Salutations (déjà capturées par TRIVIAL mais utile pour le scoring)
        "bonjour": 1, "salut": 1, "hello": 1,
        "merci": 1, "thanks": 1,
        "bonsoir": 1, "bye": 1,
        # Feedback
        "oui": 1, "non": 1, "ok": 1,
        "super": 1, "parfait": 1, "génial": 1, "genial": 1,
        "bien": 1, "mal": 1,
        # Demande de répétition
        "répète": 1, "repete": 1, "répéter": 1, "repetes": 1,
    },
}


# ═══════════════════════════════════════════════════════════════════════
#  SemanticRouter — Classifieur ultra-léger
# ═══════════════════════════════════════════════════════════════════════


class SemanticRouter:
    """Routeur sémantique ultra-léger (P1 #43).

    Architecture :
      0. Cache récent (LRU, TTL 5 min)
      1. Patterns triviaux (re.match, 0 ms)
      2. Patterns RAG (mots-clés documentaires, 0 ms)
      3. Patterns connaissance générale + web (re.search, 0 ms)
      4. Scoring par mots-clés pondérés (cas ambigus, < 1 ms)

    Le tout sans appel LLM, sans embedding, sans cloud.
    Temps typique : 0.3-1.5 ms sur M1.
    """

    def __init__(self, cache_size: int = 128, cache_ttl: float = 300) -> None:
        """Initialise le routeur avec ses dictionnaires et son cache LRU.

        Args:
            cache_size: Taille max du cache LRU (128 entrées = ~8 KB)
            cache_ttl:  Durée de vie du cache en secondes (5 min par défaut)
        """
        from collections import OrderedDict
        from threading import Lock

        # Ressources partagées
        self._lock = Lock()
        self._cache: OrderedDict = OrderedDict()
        self._cache_size = cache_size
        self._cache_ttl = cache_ttl

        # Patterns pré-compilés
        self._trivial: list[tuple[re.Pattern, str]] = [
            (re.compile(p), intent) for p, intent in TRIVIAL_PATTERNS.items()
        ]
        self._gk_patterns: list[re.Pattern] = [
            re.compile(p) for p in (
                r"(combien (font|fait|valent|vaut))",
                r"(quel(le)? est le résultat de)",
                r"\d+\s*[\+\-\*/]\s*\d+",
                r"\b(morpion|tic[- ]tac[- ]toe|échecs|dames|sudoku|puzzle)\b",
                r"(explique(-moi)?|qu['']est[- ]ce que|comment fonctionne|"
                r"pourquoi (le|la|les|l['']))",
                r"\b(photosynthèse|évolution|relativité|gravité|atome|adn|big bang)\b",
                r"(qui était|quand a eu lieu|où se trouve|qu['']est-il arrivé)",
                r"(différence entre|difference entre|quelle est la différence)",
            )
        ]
        self._web_patterns: list[re.Pattern] = [
            re.compile(p) for p in (
                r"\b(actuel(le)?ment|aujourd['' ]?hui|en ce moment|"
                r"cette année|de nos jours)\b",
                r"(qui est|qui dirige|qui occupe le poste de).{0,30}"
                r"(président|premier ministre|pdg|ceo|directeur)",
                r"(président|premier ministre).{0,30}(actuel|en exercice|de la|des|du)",
                r"(prix (actuel|du jour)|cours (actuel|du jour)|"
                r"météo|température (actuelle)?)",
                r"(dernières? (nouvelles|actualités)|actualité|news)",
            )
        ]

        # Mots-clés RAG pour détection rapide (set pour O(1))
        # On exclut les verbes génériques (trouve, cherche) du set
        # pour éviter les faux positifs (ex: "Où se trouve X")
        _excluded_single = {"trouve", "cherche", "fichier", "document"}
        self._rag_keyword_set: set[str] = {
            k for k in INTENT_KEYWORDS["RAG"]
            if " " not in k and k not in _excluded_single
        }
        # Mots-clés RAG multi-mots (phrases)
        self._rag_phrases: list[str] = [
            k for k in INTENT_KEYWORDS["RAG"] if " " in k
        ]

        logger.debug(
            "SemanticRouter initialisé : %d patterns, %d keywords, %d phrases",
            len(self._trivial) + len(self._gk_patterns) + len(self._web_patterns),
            len(INTENT_KEYWORDS["RAG"]) + len(INTENT_KEYWORDS["GENERAL"])
            + len(INTENT_KEYWORDS["WEB"]) + len(INTENT_KEYWORDS["SIMPLE"]),
            len(self._rag_phrases),
        )

    # ── Cache ────────────────────────────────────────────────────────

    def _cache_get(self, key: str) -> SemanticRoute | None:
        """Retourne une entrée du cache si valide (TTL non expiré)."""
        now = time.monotonic()
        with self._lock:
            if key in self._cache:
                entry_time, route = self._cache[key]
                if now - entry_time < self._cache_ttl:
                    # Réinsérer en fin (LRU)
                    del self._cache[key]
                    self._cache[key] = (entry_time, route)
                    return route
                else:
                    del self._cache[key]
        return None

    def _cache_set(self, key: str, route: SemanticRoute) -> None:
        """Stocke un résultat dans le cache LRU."""
        with self._lock:
            if len(self._cache) >= self._cache_size:
                self._cache.popitem(last=False)  # Éviction LRU
            self._cache[key] = (time.monotonic(), route)

    # ── Classification ───────────────────────────────────────────────

    def route(self, query: str) -> SemanticRoute:
        """Classe une requête utilisateur en intention.

        Args:
            query: Texte libre de la requête utilisateur

        Returns:
            SemanticRoute avec intent, confidence, breakdown
        """
        # ══ Début timing ══
        t0 = time.monotonic()
        q = query.lower().strip()

        # ── Cache check ──
        if len(q) > 3:
            cached = self._cache_get(q)
            if cached is not None:
                cached.breakdown["_cache"] = 1.0
                cached.processing_ms = (time.monotonic() - t0) * 1000
                return cached

        if not q:
            route = SemanticRoute(
                intent="SIMPLE", confidence=1.0,
                reasoning="Requête vide",
            )
            route.processing_ms = (time.monotonic() - t0) * 1000
            return route

        # ══ PASSE 1 : Patterns triviaux (0 ms) ══
        for pattern, intent in self._trivial:
            if pattern.match(q):
                route = SemanticRoute(
                    intent=intent, confidence=0.95,
                    reasoning=f"Pattern trivial: {intent}",
                )
                route.processing_ms = (time.monotonic() - t0) * 1000
                self._cache_set(q, route)
                return route

        # ══ PASSE 2 : Mots-clés RAG rapides ══
        # 2a : Mots simples (O(1) par mot via set)
        words = set(q.split())
        rag_exact = words & self._rag_keyword_set
        # 2b : Phrases RAG
        rag_phrase = any(ph in q for ph in self._rag_phrases)

        has_rag_kw = bool(rag_exact) or rag_phrase

        # 2c : Détection identité "Qui est [Nom Propre]"
        is_identity = False
        if not has_rag_kw:
            m = re.search(r"qui est\s+(\S+)", q)
            if m:
                next_word = m.group(1).rstrip("?!,.;:")
                if next_word and next_word[0].isupper() if query.strip() else False:
                    # Vérifier dans la requête originale pour la casse
                    orig_idx = query.lower().find(next_word)
                    if orig_idx >= 0 and orig_idx + len(next_word) <= len(query):
                        orig_word = query[orig_idx:orig_idx + len(next_word)]
                        if orig_word and orig_word[0].isupper():
                            is_identity = True

        # ══ PASSE 3 : Patterns connaissance générale + web ══
        has_gk = any(p.search(q) for p in self._gk_patterns)
        has_web = any(p.search(q) for p in self._web_patterns)

        # ══ Décision immédiate par pattern fort ══
        if has_rag_kw or is_identity:
            kw_str = ", ".join(sorted(rag_exact)) if rag_exact else (
                "identité" if is_identity else ""
            )
            route = SemanticRoute(
                intent="RAG", confidence=0.92,
                reasoning=f"Mots-clés RAG: {kw_str}",
            )
            route.processing_ms = (time.monotonic() - t0) * 1000
            self._cache_set(q, route)
            return route

        if has_gk and not has_web:
            route = SemanticRoute(
                intent="GENERAL", confidence=0.85,
                reasoning="Pattern connaissance générale",
            )
            route.processing_ms = (time.monotonic() - t0) * 1000
            self._cache_set(q, route)
            return route

        if has_web:
            route = SemanticRoute(
                intent="WEB", confidence=0.80,
                reasoning="Pattern actualité/web",
            )
            route.processing_ms = (time.monotonic() - t0) * 1000
            self._cache_set(q, route)
            return route

        if has_gk and has_web:
            # Les deux patterns : choisir WEB si plus spécifique
            web_score = self._score_intent(q, "WEB")
            gk_score = self._score_intent(q, "GENERAL")
            if web_score > gk_score:
                route = SemanticRoute(
                    intent="WEB", confidence=0.65,
                    breakdown={"WEB": web_score, "GENERAL": gk_score},
                    reasoning="Pattern mixte GK+WEB → WEB (score)",
                )
            else:
                route = SemanticRoute(
                    intent="GENERAL", confidence=0.65,
                    breakdown={"WEB": web_score, "GENERAL": gk_score},
                    reasoning="Pattern mixte GK+WEB → GENERAL (score)",
                )
            route.processing_ms = (time.monotonic() - t0) * 1000
            self._cache_set(q, route)
            return route

        # ══ PASSE 4 : Scoring par mots-clés pondérés ══
        scores: dict[str, float] = {}
        for intent in INTENT_KEYWORDS:
            scores[intent] = self._score_intent(q, intent)

        best = max(scores, key=lambda k: scores[k])
        best_score = scores[best]
        total_score = sum(scores.values())

        if best_score > 0:
            # Normalisation : confiance basée sur le ratio du meilleur score
            if total_score > 0:
                ratio = best_score / total_score
                confidence = min(0.5 + ratio * 0.4, 0.92)
            else:
                confidence = 0.4

            route = SemanticRoute(
                intent=best,
                confidence=confidence,
                breakdown=scores,
                reasoning=f"Scoring keywords: {best}={best_score}",
            )
        else:
            # Aucun mot-clé trouvé → GENERAL par défaut
            route = SemanticRoute(
                intent="GENERAL",
                confidence=0.30,
                breakdown=scores,
                reasoning="Aucun mot-clé → GENERAL (fallback)",
            )

        route.processing_ms = (time.monotonic() - t0) * 1000
        self._cache_set(q, route)
        return route

    def _score_intent(self, query_lower: str, intent: str) -> float:
        """Calcule le score d'une requête pour une intention donnée.

        Somme pondérée des mots-clés trouvés, normalisée par
        le nombre total de mots pour éviter le biais de longueur.

        Args:
            query_lower: Requête en minuscules
            intent:      Intention à scorer (RAG|GENERAL|WEB|SIMPLE)

        Returns:
            Score float ≥ 0
        """
        keywords = INTENT_KEYWORDS.get(intent, {})
        if not keywords:
            return 0.0

        # Parcourir les mots-clés (mots simples et phrases)
        score = 0.0
        for keyword, weight in keywords.items():
            if " " in keyword:
                # Phrase multi-mots : rechercher la sous-chaîne
                if keyword in query_lower:
                    score += weight * 1.5  # Bonus pour phrase exacte
            else:
                # Mot simple : split + set pour éviter les faux positifs
                # (ex: "chat" dans "château")
                if keyword in query_lower.split():
                    score += weight

        # Normalisation par longueur de requête
        word_count = len(query_lower.split())
        if word_count > 0:
            score = score / (word_count ** 0.5)  # Croissance sous-linéaire

        return score

    # ── API pratique pour intégration ─────────────────────────────────

    def classify(self, query: str) -> str:
        """Retourne uniquement l'intention (API légère pour usage rapide).

        Args:
            query: Requête utilisateur

        Returns:
            Chaîne d'intention : RAG|GENERAL|WEB|SIMPLE
        """
        return self.route(query).intent

    def describe(self, query: str) -> dict[str, Any]:
        """Retourne un diagnostic complet (debug/affichage).

        Args:
            query: Requête utilisateur

        Returns:
            Dict avec intent, confidence, breakdown, timing
        """
        route = self.route(query)
        return route.to_dict()
