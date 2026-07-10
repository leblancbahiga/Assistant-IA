"""NURU V15 Phase 4 — ReflexionEngine 2 passes (P1 #34).

Génération réflexive en 2 passes :
1. **Pass 1 (Generate)** : génère une réponse initiale via le LLM
2. **Pass 2 (Reflect)** : critique et raffine — vérifie les faits,
   détecte les contradictions, améliore la couverture

S'inspire des mécanismes Reflexion (Shinn et al. 2023) adaptés
pour M1 8 Go : pas de LLM-call reflexif dans la boucle critique,
utilisation d'heuristiques + contexte mémoire pour la réflexion.
"""

import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Optional

from src.learning.self_eval import SelfEvaluator, EvalResult

logger = logging.getLogger(__name__)


@dataclass
class ReflectionResult:
    """Résultat d'une génération réflexive 2 passes.

    Attributes:
        initial_response: Réponse brute Pass 1
        final_response: Réponse raffinée Pass 2
        critique: Analyse réflexive (faiblesses détectées)
        improvements_applied: Liste des améliorations effectuées
        eval_initial: Score d'auto-évaluation Pass 1
        eval_final: Score d'auto-évaluation Pass 2
        duration_ms: Temps total (Pass 1 + Pass 2)
        hallucination_warnings: Alertes d'hallucination détectées
    """
    initial_response: str = ""
    final_response: str = ""
    critique: list[str] = field(default_factory=list)
    improvements_applied: list[str] = field(default_factory=list)
    eval_initial: Optional[EvalResult] = None
    eval_final: Optional[EvalResult] = None
    duration_ms: float = 0.0
    hallucination_warnings: list[str] = field(default_factory=list)


class ReflexionEngine:
    """Moteur de réflexion 2 passes.

    Usage:
        engine = ReflexionEngine()
        result = await engine.reflect(
            query="Qu'est-ce que la photosynthèse ?",
            context="Les plantes vertes...",
            generate_fn=llm.generate,
        )
        # result.final_response = réponse raffinée
        # result.critique = ["manque détails sur chloroplastes", ...]
    """

    def __init__(
        self,
        self_eval: Optional[SelfEvaluator] = None,
        min_reflection_gain: float = 0.05,
        use_critique: bool = True,
    ):
        self.evaluator = self_eval or SelfEvaluator()
        self.min_reflection_gain = min_reflection_gain
        self.use_critique = use_critique

    async def reflect(
        self,
        query: str,
        context: str,
        generate_fn: Callable[[str], Awaitable[str]],
        memory_context: Optional[str] = None,
    ) -> ReflectionResult:
        """Exécute une génération réflexive 2 passes.

        Args:
            query: Question utilisateur
            context: Contexte RAG ou mémoire
            generate_fn: Fonction async de génération LLM
                         signature: (prompt: str) -> str
            memory_context: Contexte mémoire optionnel pour la réflexion

        Returns:
            ReflectionResult avec réponse raffinée et métadonnées
        """
        t0 = time.time()
        result = ReflectionResult()

        # ── Pass 1 : Génération initiale ──────────────────────────────
        prompt_1 = self._build_initial_prompt(query, context, memory_context)
        result.initial_response = await generate_fn(prompt_1)
        result.eval_initial = self.evaluator.evaluate(
            query=query,
            response=result.initial_response,
            context=context,
        )

        # ── Pass 2 : Critique réflexive ───────────────────────────────
        result.critique = self._critique(
            query=query,
            response=result.initial_response,
            context=context,
        )

        # Détection d'hallucinations
        result.hallucination_warnings = self._detect_hallucinations(
            response=result.initial_response,
            context=context,
        )

        # Appliquer les améliorations
        if result.critique or result.hallucination_warnings:
            prompt_2 = self._build_reflection_prompt(
                query=query,
                context=context,
                initial=result.initial_response,
                critique=result.critique,
                warnings=result.hallucination_warnings,
                memory_context=memory_context,
            )
            result.final_response = await generate_fn(prompt_2)
            result.eval_final = self.evaluator.evaluate(
                query=query,
                response=result.final_response,
                context=context,
            )

            # Vérifier le gain
            if result.eval_final and result.eval_initial:
                gain = result.eval_final.overall - result.eval_initial.overall
                result.improvements_applied = [
                    f"Amélioration {gain:+.2f} ({len(result.critique)} points critiqués)"
                ]
                if gain < self.min_reflection_gain:
                    logger.info(
                        "Reflexion: gain %.3f < min %.3f, on garde l'initiale",
                        gain, self.min_reflection_gain,
                    )
                    result.final_response = result.initial_response
                else:
                    logger.info(
                        "Reflexion: gain %.3f, réponse raffinée utilisée",
                        gain,
                    )
        else:
            # Rien à améliorer
            result.final_response = result.initial_response
            result.eval_final = result.eval_initial

        result.duration_ms = (time.time() - t0) * 1000
        return result

    def _build_initial_prompt(
        self,
        query: str,
        context: str,
        memory_context: Optional[str] = None,
    ) -> str:
        """Construit le prompt de génération initiale."""
        parts = [
            f"Question : {query}",
            f"Contexte : {context}",
        ]
        if memory_context:
            parts.append(f"Mémoire pertinente : {memory_context}")
        parts.append(
            "Réponds à la question en utilisant uniquement le contexte "
            "fourni. Sois précis et concis."
        )
        return "\n\n".join(parts)

    def _build_reflection_prompt(
        self,
        query: str,
        context: str,
        initial: str,
        critique: list[str],
        warnings: list[str],
        memory_context: Optional[str] = None,
    ) -> str:
        """Construit le prompt de réflexion (Pass 2)."""
        parts = [
            f"Question originale : {query}",
            f"Contexte : {context}",
        ]
        if memory_context:
            parts.append(f"Mémoire pertinente : {memory_context}")

        parts.append(f"Réponse initiale :\n{initial}")

        if critique:
            parts.append(
                "Points à améliorer :\n- " + "\n- ".join(critique)
            )

        if warnings:
            parts.append(
                "⚠️ Vérifications nécessaires :\n- "
                + "\n- ".join(warnings)
            )

        parts.append(
            "Produis une version améliorée de la réponse qui corrige "
            "les points ci-dessus. Garde la même structure mais améliore "
            "la précision, la complétude et la clarté."
        )
        return "\n\n".join(parts)

    def _critique(
        self,
        query: str,
        response: str,
        context: str,
    ) -> list[str]:
        """Analyse réflexive heuristique de la réponse.

        Vérifie :
        - Présence de répétitions
        - Couverture des mots-clés de la question
        - Signalement d'absence de contexte (hallucination potentielle)
        - Taille excessive ou insuffisante
        """
        issues: list[str] = []

        # 1. Répétitions flagrantes
        sentences = re.split(r'[.!?]+', response)
        unique = set(s.strip().lower() for s in sentences if len(s.strip()) > 20)
        if len(sentences) > 3 and len(unique) <= 1:
            issues.append("La réponse semble répétitive : peu de variation entre les phrases")

        # 2. Couverture des mots-clés
        query_words = set(
            w.lower() for w in re.findall(r'\w{4,}', query)
            if w.lower() not in {"comment", "pourquoi", "quelle", "quels",
                                   "quelles", "est-ce", "c'est", "dans", "avec"}
        )
        if query_words:
            covered = sum(1 for w in query_words if w in response.lower())
            coverage = covered / len(query_words)
            if coverage < 0.5:
                issues.append(
                    f"Faible couverture thématique : {covered}/{len(query_words)} "
                    f"mots-clés de la question apparaissent dans la réponse"
                )

        # 3. Détection de phrases évasives
        hedging = re.findall(
            r"(je ne suis pas sûr|je ne sais pas|peut-être|"
            r"il est possible que|je n'ai pas d'information|"
            r"selon les sources disponibles|d'après le contexte)",
            response,
            re.IGNORECASE,
        )
        if len(hedging) > 2:
            issues.append(
                f"Hésitations excessives ({len(hedging)} occurrences) : "
                f"la réponse manque d'assurance"
            )

        # 4. Taille disproportionnée
        resp_words = len(response.split())
        ctx_words = len(context.split())
        if ctx_words > 0 and resp_words > ctx_words * 3:
            issues.append(
                f"Réponse trop longue ({resp_words} mots) "
                f"par rapport au contexte ({ctx_words} mots) — "
                f"risque d'hallucination"
            )
        if resp_words < 5:
            issues.append("Réponse trop courte — manque de développement")

        return issues

    def _detect_hallucinations(
        self,
        response: str,
        context: str,
    ) -> list[str]:
        """Détection heuristique d'hallucinations.

        Vérifie les affirmations factuelles non supportées par le contexte.
        Basé sur des règles simples (pas de LLM-call).
        """
        warnings: list[str] = []

        # 1. Chiffres et statistiques non supportés
        numbers = re.findall(r'\d+[%€$]|\d+%|[\d,]+(?:euros|dollars|fois)', response)
        for num in numbers[:3]:
            if num not in context:
                warnings.append(
                    f"Affirmation chiffrée non vérifiée dans le contexte : «{num}»"
                )

        # 2. Noms propres hors contexte
        proper = re.findall(r'\b[A-Z][a-zéèêëàâäùûüôöîïç]{2,}\b', response)
        context_proper = set(
            re.findall(r'\b[A-Z][a-zéèêëàâäùûüôöîïç]{2,}\b', context)
        )
        for name in proper:
            if name not in context_proper and len(name) > 3:
                warnings.append(
                    f"Entité nommée hors contexte : «{name}»"
                )
                break  # Un seul avertissement suffit

        # 3. Phrases qui ressemblent à des "inventions"
        if "en conclusion" in response.lower() and "en conclusion" not in context.lower():
            if response.lower().count("en conclusion") > 1:
                warnings.append(
                    "Structure de conclusion générique non supportée par le contexte"
                )

        return warnings
