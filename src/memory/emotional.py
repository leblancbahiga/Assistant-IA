"""EmotionalContext — Contexte émotionnel de l'utilisateur.

Analyse le ton des messages pour inférer l'état émotionnel.
Utilisé par DynamicPromptBuilder pour adapter le ton de NURU.
"""

from __future__ import annotations

import enum
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


class EmotionalState(enum.Enum):
    """États émotionnels détectables."""
    NEUTRAL = "neutre"
    HAPPY = "content"
    STRESSED = "stressé"
    FRUSTRATED = "frustré"
    URGENT = "urgent"
    SAD = "triste"
    ANGRY = "fâché"
    CURIOUS = "curieux"
    GRATEFUL = "reconnaissant"


@dataclass
class EmotionalConfig:
    """Configuration de l'analyse émotionnelle."""
    enabled: bool = True
    window_size: int = 5         # Messages à analyser
    min_confidence: float = 0.3  # Seuil minimum
    language: str = "fr"


@dataclass
class EmotionalResult:
    """Résultat de l'analyse émotionnelle."""
    state: EmotionalState = EmotionalState.NEUTRAL
    confidence: float = 1.0
    detected_keywords: list[str] = field(default_factory=list)
    message_count: int = 0


class EmotionalAnalyzer:
    """Analyseur de contexte émotionnel basé sur des règles.

    Usage :
        analyzer = EmotionalAnalyzer()
        result = analyzer.analyze("C'est vraiment génial !")
        if result.state == EmotionalState.HAPPY:
            print("Utilisateur content")
    """

    def __init__(self, config: Optional[EmotionalConfig] = None):
        self.config = config or EmotionalConfig()
        self._recent_messages: list[str] = []

        # Lexique émotionnel français
        self._lexicon = {
            EmotionalState.HAPPY: [
                r"(génial|super|excellent|parfait|merci|bravo|top|👍|🎉|heureux|content)",
            ],
            EmotionalState.STRESSED: [
                r"(stress|pressé|urgence|délai|trop de|débordé|chargé|urgent)",
            ],
            EmotionalState.FRUSTRATED: [
                r"(ça marche pas|bug|erreur|encore|toujours|jamais|rien|pénible|fatiguant)",
                r"(marche.*pas|pas.*marche|encore.*bug)",
            ],
            EmotionalState.URGENT: [
                r"(tout de suite|immédiatement|vite|urgence|maintenant|dépêche|vite|⚠️)",
            ],
            EmotionalState.ANGRY: [
                r"(fâché|énervé|colère|exaspéré|agacé|ça suffit|j'en ai marre)",
            ],
            EmotionalState.CURIOUS: [
                r"(comment|pourquoi|explique|dis-moi|j'aimerais|curieux|intéressant)",
            ],
            EmotionalState.GRATEFUL: [
                r"(merci|merci beaucoup|reconnaissant|sympa|gentil|apprécie|parfait merci)",
            ],
        }

    def analyze(self, message: str) -> EmotionalResult:
        """Analyse le ton émotionnel d'un message."""
        self._recent_messages.append(message)
        if len(self._recent_messages) > self.config.window_size:
            self._recent_messages.pop(0)

        if not self.config.enabled:
            return EmotionalResult(state=EmotionalState.NEUTRAL, confidence=1.0)

        message_lower = message.lower()
        scores: dict[EmotionalState, int] = {}

        for state, patterns in self._lexicon.items():
            count = 0
            keywords = []
            for pattern in patterns:
                matches = re.findall(pattern, message_lower)
                count += len(matches)
                keywords.extend(matches)
            if count > 0:
                scores[state] = count

        if not scores:
            return EmotionalResult(state=EmotionalState.NEUTRAL, confidence=0.5, message_count=1)

        best_state: EmotionalState = max(scores, key=lambda s: scores[s])  # type: ignore
        total_keywords = sum(scores.values())

        return EmotionalResult(
            state=best_state,
            confidence=min(total_keywords / 3.0, 1.0),
            detected_keywords=[str(k) for k in scores.keys()],
            message_count=len(self._recent_messages),
        )

    def get_current_trend(self) -> EmotionalResult:
        """Analyse des derniers messages pour détecter une tendance."""
        if not self._recent_messages:
            return EmotionalResult()

        combined = " ".join(self._recent_messages[-self.config.window_size:])
        return self.analyze(combined)

    def reset(self) -> None:
        """Réinitialise l'analyseur."""
        self._recent_messages.clear()
