"""
NURU V8+ — Query Rewriter avec LLM Cloud (Groq/OpenRouter/DeepSeek).

Réécrit une requête utilisateur pour améliorer le recall RAG :
1. Extraction des entités clés (noms, lieux, dates)
2. Reformulation en requête de recherche optimisée
3. Fallback sur le rewriter V6 (synonymes) si CloudLLM indisponible

Tâche 4.2 — Sprint 4 : Multi-stratégie + Query Intelligence.
"""

import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Termes de recherche génériques à toujours ajouter selon le contexte
DOMAIN_TERMS = {
    "agronomie": ["agriculture", "rendement", "culture", "production vegetale", "sol",
                  "irrigation", "semence", "fertilisation", "recolte"],
    "elevage": ["betail", "veterinaire", "pature", "alimentation animale"],
    "informatique": ["developpement", "logiciel", "programmation", "python", "data",
                     "base de donnees", "algorithme"],
    "cv": ["competence", "experience professionnelle", "formation", "diplome",
           "parcours", "poste occupe"],
}

# Mots reflecteurs de domaine
DOMAIN_KEYWORDS = {
    "riz|mais|manioc|sorgho|haricot|cassava|semence|rendement|recolte|sol|fertilisation|beaccom|rikolto|yarid|palabek|lubero|kananga|innogence": "agronomie",
    "cv|competence|diplome|experience|parcours|formation|poste": "cv",
    "python|javascript|code|logiciel|programmation|base de donnees|algorithme|api": "informatique",
}


# V10 BUG #1: Protection contre les réécritures Cloud qui dévient le sens
# Le Cloud LLM peut interpréter BEACCOM comme "système de paiement électronique"
# alors que c'est une ONG agricole en RDC. Cette fonction détecte ces déviations.
def _cloud_rewrite_is_safe(original_query: str, cloud_rewrite: str) -> bool:
    """Vérifie que la réécriture Cloud ne change pas le sens de la requête.

    Règles:
    1. La réécriture doit contenir au moins 50% des mots significatifs de l'originale
    2. Les nouveaux termes ne doivent pas contredire le contexte documentaire
    """
    import re
    # Extraire les mots significatifs (non stop-words) des deux requêtes
    stop_words = {
        'de', 'la', 'le', 'les', 'un', 'une', 'des', 'du', 'au', 'aux', 'en', 'et', 'ou',
        'est', 'sont', 'dans', 'sur', 'par', 'pour', 'avec', 'sans', 'que', 'qui', 'ne', 'pas',
        'the', 'a', 'an', 'in', 'on', 'at', 'of', 'to', 'is', 'are', 'and', 'or', 'for',
    }

    orig_words = set(
        w.lower() for w in re.findall(r'\w+', original_query)
        if w.lower() not in stop_words and len(w) > 1
    )
    cloud_words = set(
        w.lower() for w in re.findall(r'\w+', cloud_rewrite)
        if w.lower() not in stop_words and len(w) > 1
    )

    if not orig_words:
        return True  # Requête vide ou stop-words uniquement → safe

    # Au moins 50% des mots originaux doivent être dans la réécriture
    overlap = orig_words & cloud_words
    retention_ratio = len(overlap) / len(orig_words)

    if retention_ratio < 0.5:
        logger.debug(
            f"Cloud rewrite unsafe: seulement {retention_ratio:.0%} des mots "
            f"originaux conservés ({overlap} vs {orig_words})"
        )
        return False

    return True


class CloudQueryRewriter:
    """Réécriture de requête via LLM Cloud pour améliorer le recall RAG.

    Utilise le CloudLLM configuré pour reformuler la requête
    en une version optimisée pour la recherche sémantique + FTS.
    """

    def __init__(self, cloud_llm: Optional[object] = None):
        self._cloud = cloud_llm
        # Fallback V6 : rewriter à synonymes
        self._v6_rewriter = None
        try:
            from src.query_rewriter import QueryRewriter
            self._v6_rewriter = QueryRewriter(cloud_llm=cloud_llm)
        except Exception:
            pass

    def get_domain(self, query: str) -> Optional[str]:
        """Détecte le domaine de la requête à partir des mots-clés."""
        q_lower = query.lower()
        for pattern, domain in DOMAIN_KEYWORDS.items():
            if re.search(pattern, q_lower):
                return domain
        return None

    def rewrite(self, query: str) -> str:
        """Point d'entrée principal : réécrit la requête.

        Priorité :
        1. LLM Cloud (si disponible)
        2. V6 fallback (synonymes)
        3. Requête originale inchangée
        """
        if not query or not query.strip():
            return query

        # 1. Essayer LLM Cloud
        if self._cloud:
            try:
                cloud_result = self._rewrite_with_cloud(query)
                if cloud_result:
                    # V10 Correction BUG #1: Vérifier que la réécriture Cloud ne dévie pas
                    # du contexte réel (ex: BEACCOM → "système de paiement électronique")
                    if self._v6_rewriter and _cloud_rewrite_is_safe(query, cloud_result):
                        logger.info(
                            f"Cloud Query Rewriting: '{query[:60]}' -> '{cloud_result[:80]}'"
                        )
                        return cloud_result
                    else:
                        # Cloud a déliré → fallback V6
                        logger.warning(
                            f"Cloud rewrite unsafe (hallucination détectée): "
                            f"'{query[:40]}' -> '{cloud_result[:80]}' → fallback V6"
                        )
            except Exception as e:
                logger.debug(f"Cloud rewrite failed: {e}")

        # 2. Fallback V6
        if self._v6_rewriter:
            try:
                v6_result = self._v6_rewriter.rewrite(query)
                if v6_result and v6_result != query:
                    logger.info(
                        f"V6 Query Rewriting: '{query[:60]}' -> '{v6_result[:80]}'"
                    )
                    return v6_result
            except Exception:
                pass

        return query

    def _rewrite_with_cloud(self, query: str) -> str:
        """Réécriture via LLM Cloud — une seule requête structurée.

        Prompt optimisé pour que le LLM produise une version
        de la requête adaptée à la recherche documentaire.
        """
        domain = self.get_domain(query)
        domain_hint = ""
        if domain and domain in DOMAIN_TERMS:
            terms = DOMAIN_TERMS[domain]
            domain_hint = (
                f"\nContexte : la requête semble liée au domaine '{domain}'. "
                f"Termes pertinents : {', '.join(terms[:4])}."
            )

        prompt = (
            "Tu es un réécrivain de requêtes pour un système de recherche documentaire (RAG).\n"
            "Ta mission : transformer la QUESTION en une REQUÊTE DE RECHERCHE optimisée.\n"
            "\n"
            "Règles :\n"
            "1. Réponds UNIQUEMENT avec la requête réécrite (pas d'explication, pas de formatage)\n"
            "2. Ajoute des synonymes et termes connexes si pertinent\n"
            "3. Préserve les noms propres, lieux, dates et chiffres\n"
            "4. Supprime les mots de liaison inutiles\n"
            "5. Garde la même langue que la question\n"
            f"\nQuestion : {query}"
            f"{domain_hint}"
            "\n\nRequête de recherche :"
        )

        try:
            response = self._cloud.generate(prompt, timeout=5.0)
            if not response or not response.strip():
                logger.debug("Cloud rewrite: réponse vide")
                return ""

            cleaned = response.strip()
            # Nettoyer les artefacts possibles
            cleaned = re.sub(
                r'^(?:Requête de recherche\s*:?\s*|Réécriture\s*:?\s*)',
                '', cleaned, flags=re.IGNORECASE
            ).strip()
            # Supprimer les guillemets superflus
            cleaned = cleaned.strip('"\'„"')
            # Limiter la longueur
            if len(cleaned) > 500:
                cleaned = cleaned[:500]

            if cleaned and cleaned != query:
                return cleaned
            return ""

        except Exception as e:
            logger.warning(f"Cloud rewrite error: {e}")
            return ""
