"""
NURU V9 — SelfEvaluator : évalue la qualité des réponses sans référence humaine.

Dimensions (RAGAS-like) pour V9 MVP :
- faithfulness : la réponse est-elle supportée par les sources ?
- answer_relevance : la réponse répond-elle à la question ?
- context_precision : le contexte récupéré est-il pertinent ?
- context_recall : le contexte couvre-t-il les sources pertinentes ?
- hallucination_score : y a-t-il des affirmations non supportées ?

Les vérifications sont basées sur des règles et similarité textuelle
(pas de LLM-call pour ne pas saturer la RAM).
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class EvalResult:
    """Résultat d'évaluation d'une réponse selon les dimensions RAGAS-like.

    Tous les scores sont dans [0.0, 1.0] où 1.0 = parfait.
    overall est la moyenne pondérée des dimensions.
    """
    faithfulness: float = 0.0
    answer_relevance: float = 0.0
    context_precision: float = 0.0
    context_recall: float = 0.0
    hallucination_score: float = 0.0
    overall: float = 0.0


class SelfEvaluator:
    """Évaluateur automatique de qualité des réponses.

    Évalue une réponse sur 5 dimensions sans nécessiter de référence humaine.
    Pour V9 MVP, utilise des règles heuristiques et la similarité
    textuelle au lieu de LLM-calls.

    Poids des dimensions pour le score overall :
    - faithfulness: 0.30
    - answer_relevance: 0.25
    - context_precision: 0.20
    - context_recall: 0.15
    - hallucination_score: 0.10
    """

    # Poids pour le calcul du score overall
    OVERALL_WEIGHTS: dict[str, float] = {
        "faithfulness": 0.30,
        "answer_relevance": 0.25,
        "context_precision": 0.20,
        "context_recall": 0.15,
        "hallucination_score": 0.10,
    }

    def __init__(self, memory_manager=None):
        """Initialise l'évaluateur.

        Args:
            memory_manager: Instance optionnelle de MemoryManager pour
                            consulter ErrorMemory (non utilisée en V9 MVP)
        """
        self.memory_manager = memory_manager

    # ── Évaluation complète ───────────────────────────────────────

    def evaluate(
        self,
        query: str,
        response: str,
        sources: Optional[list[str]] = None,
        context: Optional[str] = None,
    ) -> EvalResult:
        """Évalue une réponse sur toutes les dimensions.

        Args:
            query: La requête utilisateur originale
            response: La réponse générée
            sources: Liste des textes sources utilisés (optionnel)
            context: Le contexte RAG récupéré (optionnel)

        Returns:
            EvalResult avec tous les scores calculés
        """
        sources = sources or []
        context = context or ""

        faithfulness = self._check_faithfulness(response, sources)
        answer_relevance = self._check_relevance(query, response)
        context_precision = self._check_precision(context, query)
        context_recall = self._check_recall(context, sources)
        hallucination_score = self._check_hallucination(response, sources)

        # Score overall : moyenne pondérée
        overall = (
            faithfulness * self.OVERALL_WEIGHTS["faithfulness"]
            + answer_relevance * self.OVERALL_WEIGHTS["answer_relevance"]
            + context_precision * self.OVERALL_WEIGHTS["context_precision"]
            + context_recall * self.OVERALL_WEIGHTS["context_recall"]
            + hallucination_score * self.OVERALL_WEIGHTS["hallucination_score"]
        )

        return EvalResult(
            faithfulness=round(faithfulness, 4),
            answer_relevance=round(answer_relevance, 4),
            context_precision=round(context_precision, 4),
            context_recall=round(context_recall, 4),
            hallucination_score=round(hallucination_score, 4),
            overall=round(overall, 4),
        )

    # ── Dimensions individuelles ──────────────────────────────────

    def _check_faithfulness(self, response: str, sources: list[str]) -> float:
        """Vérifie que les affirmations de la réponse sont supportées par les sources.

        Pour MVP : extrait les phrases de la réponse, vérifie pour chacune
        si au moins un mot-clé significatif (hors mots vides) apparaît
        dans les sources.

        Args:
            response: La réponse générée
            sources: Les textes sources

        Returns:
            Score [0.0, 1.0] : proportion de phrases de la réponse
            qui sont supportées par au moins une source
        """
        if not response.strip():
            return 0.0

        if not sources:
            # Pas de sources disponibles → on ne peut pas vérifier
            return 0.5

        # Extraire les phrases de la réponse
        sentences = self._split_sentences(response)
        if not sentences:
            return 0.5

        # Mots vides français et anglais à ignorer
        stop_words = {
            "le", "la", "les", "un", "une", "des", "du", "de", "et", "est",
            "a", "à", "dans", "pour", "sur", "avec", "pas", "que", "qui",
            "par", "ou", "où", "si", "ce", "se", "son", "sa", "ses",
            "the", "a", "an", "is", "are", "was", "were", "in", "on",
            "at", "to", "for", "of", "with", "by", "and", "or", "not",
            "il", "elle", "nous", "vous", "ils", "elles", "cela",
            "plus", "moins", "très", "aussi", "mais", "donc", "car",
            "ni", "hors", "dès", "chez", "entre", "sous", "autre",
            "fait", "bien", "peut", "être", "avoir", "faire",
        }

        supported_count = 0
        for sentence in sentences:
            # Extraire les mots significatifs de la phrase
            words = set(re.findall(r'[a-zéèêëàâùûîôç]+', sentence.lower()))
            keywords = words - stop_words

            if not keywords:
                # Phrase sans mot significatif → considérée supportée
                supported_count += 1
                continue

            # Vérifier si au moins un mot-clé apparaît dans les sources
            source_text = " ".join(sources).lower()
            if any(kw in source_text for kw in keywords):
                supported_count += 1

        return supported_count / len(sentences)

    def _check_relevance(self, query: str, response: str) -> float:
        """Vérifie la pertinence de la réponse par rapport à la question.

        Pour MVP : calcule le ratio de mots-clés de la requête
        qui apparaissent dans la réponse. Un mot-clé est un mot
        significatif (≥ 4 caractères, hors mots vides).

        Args:
            query: La requête utilisateur
            response: La réponse générée

        Returns:
            Score [0.0, 1.0]
        """
        if not query.strip() or not response.strip():
            return 0.0

        # Extraire les mots-clés significatifs de la requête
        query_lower = query.lower()
        response_lower = response.lower()

        # Mots vides supplémentaires pour les requêtes
        stop_words = {
            "avec", "dans", "pour", "sur", "avec", "comment", "quelle",
            "quels", "quelles", "quel", "quand", "pourquoi", "combien",
            "est-ce", "the", "what", "how", "why", "when", "where",
            "which", "this", "that", "these", "those",
        }

        words = re.findall(r'[a-zéèêëàâùûîôç]+', query_lower)
        keywords = {
            w for w in words
            if len(w) >= 4 and w not in stop_words
        }

        if not keywords:
            # Pas de mots-clés → réponse considérée pertinente
            return 0.8

        # Compter combien de mots-clés apparaissent dans la réponse
        found = sum(1 for kw in keywords if kw in response_lower)
        return found / len(keywords)

    def _check_precision(self, context: str, query: str) -> float:
        """Vérifie que le contexte récupéré est pertinent pour la requête.

        Pour MVP : ratio de phrases du contexte qui contiennent
        au moins un mot-clé de la requête.

        Args:
            context: Le contexte RAG récupéré
            query: La requête utilisateur

        Returns:
            Score [0.0, 1.0]
        """
        if not context.strip():
            return 0.0

        if not query.strip():
            return 0.5

        # Extraire les mots significatifs de la requête
        query_lower = query.lower()
        context_lower = context.lower()

        # Phrases du contexte (en minuscules pour la comparaison)
        context_sentences = self._split_sentences(context)
        if not context_sentences:
            return 0.0

        # Mots-clés de la requête (4+ caractères)
        stop_words = {
            "avec", "dans", "pour", "sur", "the", "this", "that",
            "what", "how", "why", "when", "where", "est-ce",
        }
        query_keywords = [
            w for w in re.findall(r'[a-zéèêëàâùûîôç]+', query_lower)
            if len(w) >= 4 and w not in stop_words
        ]

        if not query_keywords:
            return 0.5

        # Ratio de phrases pertinentes (comparaison insensible à la casse)
        relevant = sum(
            1 for sent in context_sentences
            if any(kw in sent.lower() for kw in query_keywords)
        )
        return relevant / len(context_sentences)

    def _check_recall(self, context: str, sources: list[str]) -> float:
        """Vérifie que le contexte couvre bien les sources pertinentes.

        Pour MVP : ratio de sources dont au moins un mot-clé
        apparaît dans le contexte.

        Args:
            context: Le contexte RAG récupéré
            sources: Les textes sources disponibles

        Returns:
            Score [0.0, 1.0]
        """
        if not sources:
            # Pas de sources → pas de recall à évaluer
            return 0.5

        if not context.strip():
            return 0.0

        context_lower = context.lower()

        stop_words = {
            "avec", "dans", "pour", "sur", "the", "this", "that",
            "and", "but", "not", "was", "were", "has", "had",
        }

        covered = 0
        for source in sources:
            if not source.strip():
                continue
            source_lower = source.lower()
            # Extraire mots-clés de la source
            source_keywords = [
                w for w in re.findall(r'[a-zéèêëàâùûîôç]+', source_lower)
                if len(w) >= 5 and w not in stop_words
            ]
            if not source_keywords:
                # Source courte, on vérifie directement
                if source_lower in context_lower:
                    covered += 1
                continue

            # Source couverte si au moins un mot-clé apparaît dans le contexte
            if any(kw in context_lower for kw in source_keywords):
                covered += 1

        return covered / len(sources)

    def _check_hallucination(self, response: str, sources: list[str]) -> float:
        """Détecte les affirmations non supportées dans la réponse.

        Pour MVP : complément de faithfulness. Calcule la proportion
        de phrases supportées par les sources, puis retourne
        (1 - faithfulness) comme score d'hallucination.
        Un score élevé = peu d'hallucinations.

        Args:
            response: La réponse générée
            sources: Les textes sources

        Returns:
            Score [0.0, 1.0] où 1.0 = pas d'hallucination
        """
        if not response.strip():
            return 0.0

        if not sources:
            # Pas de sources → ne peut pas détecter d'hallucination
            return 0.6

        faithfulness = self._check_faithfulness(response, sources)
        # Hallucination score = 1 - hallucination_rate
        hallucination_rate = 1.0 - faithfulness
        return 1.0 - hallucination_rate

    # ── Utilitaires ───────────────────────────────────────────────

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Découpe un texte en phrases.

        Args:
            text: Le texte à découper

        Returns:
            Liste des phrases non vides
        """
        # Séparateurs : point, point d'interrogation, point d'exclamation,
        # retour à la ligne, ou point-virgule suivi d'une majuscule
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]
        return sentences
