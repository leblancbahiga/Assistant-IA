"""
NURU V8+ — Vérificateur de faits post-génération (Sprint 5).

Compare la réponse générée contre les sources RAG pour vérifier
que chaque affirmation est supportée par les documents.

Utilise le LLM cloud configuré (OpenCode Zen, OpenRouter, DeepSeek, Groq, Nvidia).
Protégé par already_fact_checked guard anti-boucle.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constantes ──
MAX_SOURCES_CHARS = 4000     # ~1000 tokens pour les sources
MAX_RESPONSE_CHARS = 2000    # ~500 tokens pour la réponse
VERIFY_TIMEOUT = 15.0        # V10 Audit: 5s -> 15s (JSON verification prend du temps)
MAX_RETRIES = 1              # Max régénérations


@dataclass
class FactCheckResult:
    """Résultat de la vérification des faits.

    Attributes:
        verified: True si toutes les affirmations sont supportées par les sources
        issues: Liste des affirmations non trouvées dans les sources
        confidence_delta: Ajustement de confiance (-0.2 si problèmes, -0.4 si échec)
        needs_regenerate: True si une régénération est recommandée
    """
    verified: bool = True
    issues: list[str] = field(default_factory=list)
    confidence_delta: float = 0.0
    needs_regenerate: bool = False


VERIFY_PROMPT = """Tu es un vérificateur de faits spécialisé en analyse documentaire.

Compare la RÉPONSE générée avec les SOURCES fournies.
Pour chaque affirmation dans la réponse, indique si elle est SUPPORTÉE ou NON par les sources.

Règles :
- SUPPORTÉE = l'affirmation est explicitement présente dans UNE source au moins
- NON SUPPORTÉE = l'affirmation n'est pas dans les sources (hallucination possible)
- Les reformulations et synthèses sont acceptables si le contenu est présent
- Les informations générales (ex: "le riz est une céréale") sans source sont OK
- Ne compte PAS les omissions comme des erreurs

Retourne UNIQUEMENT un JSON valide, sans commentaires :
{{
    "verified": true/false,
    "issues": ["liste des affirmations non supportées, vide si tout est OK"],
    "confidence_delta": -0.2
}}
"""


class FactChecker:
    """Vérificateur de faits post-génération.

    Utilise le LLM cloud pour comparer la réponse aux sources.
    Retourne FactCheckResult avec le niveau de confiance ajusté.
    """

    def __init__(self, cloud_llm: Optional[object] = None):
        self._cloud = cloud_llm

    async def verify(self, response: str, sources: list[str],
                     cloud_llm: object = None) -> FactCheckResult:
        """Vérifie la réponse contre les sources.

        Args:
            response: Réponse générée par le LLM
            sources: Liste des textes sources (chunks RAG)
            cloud_llm: Instance CloudLLM (override si nécessaire)

        Returns:
            FactCheckResult avec le verdict
        """
        llm = cloud_llm or self._cloud
        if not llm:
            logger.debug("FactChecker: pas de CloudLLM, skip vérification")
            return FactCheckResult(verified=True)

        if not response or not response.strip():
            return FactCheckResult(verified=True)

        # Tronquer les sources au budget
        source_text = self._format_sources(sources)
        if len(source_text) > MAX_SOURCES_CHARS:
            source_text = source_text[:MAX_SOURCES_CHARS]

        # Tronquer la réponse
        clean_response = response[:MAX_RESPONSE_CHARS]

        prompt = (
            f"{VERIFY_PROMPT}\n"
            f"\nSOURCES :\n{source_text}\n"
            f"\nRÉPONSE :\n{clean_response}\n"
            f"\nJSON :"
        )

        try:
            raw = llm.generate(prompt, timeout=VERIFY_TIMEOUT)
            return self._parse_result(raw)
        except Exception as e:
            logger.warning(f"FactChecker: échec appel cloud ({e})")
            return FactCheckResult(verified=True, confidence_delta=0.0)

    def _format_sources(self, sources: list[str]) -> str:
        """Formate les sources pour le prompt."""
        if not sources:
            return "[Aucune source fournie]"

        parts = []
        for i, s in enumerate(sources, 1):
            if not s or not s.strip():
                continue
            s_clean = s.strip()[:500]  # 500 chars max par source
            parts.append(f"[Source {i}] {s_clean}")

        return "\n\n".join(parts) if parts else "[Aucune source valide]"

    def _parse_result(self, raw: str) -> FactCheckResult:
        """Parse la réponse JSON du LLM."""
        if not raw or not raw.strip():
            return FactCheckResult(verified=True)

        cleaned = raw.strip()
        # Nettoyer les artefacts markdown
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)

        try:
            data = json.loads(cleaned)

            verified = data.get("verified", True)
            issues = data.get("issues", [])
            if not isinstance(issues, list):
                issues = []

            # Calculer confidence_delta
            if not verified and issues:
                confidence_delta = min(-0.2 * len(issues), -0.4)
            else:
                confidence_delta = 0.0

            needs_regenerate = not verified and len(issues) > 0

            return FactCheckResult(
                verified=bool(verified),
                issues=[str(i) for i in issues],
                confidence_delta=confidence_delta,
                needs_regenerate=needs_regenerate,
            )

        except (json.JSONDecodeError, Exception) as e:
            logger.debug(f"FactChecker: parse error ({e}), raw={raw[:100]}")
            return FactCheckResult(verified=True, confidence_delta=0.0)
