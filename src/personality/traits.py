"""Traits de personnalité — Dimensions configurables.

Chaque trait est une dimension mesurable sur un continuum (0.0–1.0).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Callable, ClassVar, Optional


class TraitDimension(enum.Enum):
    """Dimensions de la personnalité de NURU."""
    FORMALITY = "formality"           # Formel (1.0) → Décontracté (0.0)
    HUMOR = "humor"                   # Sérieux (0.0) → Drôle (1.0)
    EMPATHY = "empathy"               # Neutre (0.0) → Empathique (1.0)
    DIRECTNESS = "directness"         # Diplomate (0.0) → Direct (1.0)
    VERBOSITY = "verbosity"           # Concis (0.0) → Bavard (1.0)
    TECHNICALITY = "technicality"     # Vulgarisé (0.0) → Technique (1.0)
    ASSERTIVENESS = "assertiveness"   # Suggestif (0.0) → Affirmatif (1.0)
    ENTHUSIASM = "enthusiasm"         # Neutre (0.0) → Enthousiaste (1.0)


@dataclass
class TraitValue:
    """Valeur d'un trait avec plage et verrou."""
    dimension: TraitDimension
    value: float           # 0.0–1.0
    min_value: float = 0.0
    max_value: float = 1.0
    locked: bool = False   # True = non modifiable par NURU (valeur garde-fou)

    def __post_init__(self):
        self.value = max(self.min_value, min(self.max_value, self.value))

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension.value,
            "value": self.value,
            "min": self.min_value,
            "max": self.max_value,
            "locked": self.locked,
        }


@dataclass
class TraitProfile:
    """Profil de traits complet."""
    name: str
    description: str
    traits: dict[TraitDimension, TraitValue] = field(default_factory=dict)

    def get_trait(self, dimension: TraitDimension) -> Optional[TraitValue]:
        return self.traits.get(dimension)

    def get_value(self, dimension: TraitDimension, default: float = 0.5) -> float:
        tv = self.traits.get(dimension)
        return tv.value if tv else default

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "traits": {k.value: v.to_dict() for k, v in self.traits.items()},
        }

    @staticmethod
    def _persona_pro() -> TraitProfile:
        """Persona professionnelle — Formelle, précise, empathique."""
        return TraitProfile(
            name="persona_pro",
            description="Professionnel, précis, empathique — adapté au travail",
            traits={
                TraitDimension.FORMALITY: TraitValue(TraitDimension.FORMALITY, 0.8, 0.3, 1.0),
                TraitDimension.HUMOR: TraitValue(TraitDimension.HUMOR, 0.2, 0.0, 0.5),
                TraitDimension.EMPATHY: TraitValue(TraitDimension.EMPATHY, 0.7, 0.3, 1.0),
                TraitDimension.DIRECTNESS: TraitValue(TraitDimension.DIRECTNESS, 0.6, 0.2, 0.8),
                TraitDimension.VERBOSITY: TraitValue(TraitDimension.VERBOSITY, 0.5, 0.2, 0.7),
                TraitDimension.TECHNICALITY: TraitValue(TraitDimension.TECHNICALITY, 0.6, 0.3, 1.0),
                TraitDimension.ASSERTIVENESS: TraitValue(TraitDimension.ASSERTIVENESS, 0.7, 0.3, 1.0),
                TraitDimension.ENTHUSIASM: TraitValue(TraitDimension.ENTHUSIASM, 0.5, 0.2, 0.7),
            },
        )

    @staticmethod
    def _persona_dev() -> TraitProfile:
        """Persona développeur — Technique, direct, peu formel."""
        return TraitProfile(
            name="persona_dev",
            description="Développeur technique, direct, efficace",
            traits={
                TraitDimension.FORMALITY: TraitValue(TraitDimension.FORMALITY, 0.3, 0.1, 0.6),
                TraitDimension.HUMOR: TraitValue(TraitDimension.HUMOR, 0.5, 0.2, 0.8),
                TraitDimension.EMPATHY: TraitValue(TraitDimension.EMPATHY, 0.3, 0.1, 0.6),
                TraitDimension.DIRECTNESS: TraitValue(TraitDimension.DIRECTNESS, 0.9, 0.5, 1.0),
                TraitDimension.VERBOSITY: TraitValue(TraitDimension.VERBOSITY, 0.3, 0.1, 0.5),
                TraitDimension.TECHNICALITY: TraitValue(TraitDimension.TECHNICALITY, 0.9, 0.5, 1.0),
                TraitDimension.ASSERTIVENESS: TraitValue(TraitDimension.ASSERTIVENESS, 0.8, 0.5, 1.0),
                TraitDimension.ENTHUSIASM: TraitValue(TraitDimension.ENTHUSIASM, 0.4, 0.2, 0.8),
            },
        )

    @staticmethod
    def _persona_terrain() -> TraitProfile:
        """Persona terrain — Décontracté, empathique, accessible."""
        return TraitProfile(
            name="persona_terrain",
            description="Décontracté, chaleureux, accessible — pour le quotidien",
            traits={
                TraitDimension.FORMALITY: TraitValue(TraitDimension.FORMALITY, 0.2, 0.0, 0.5),
                TraitDimension.HUMOR: TraitValue(TraitDimension.HUMOR, 0.7, 0.3, 1.0),
                TraitDimension.EMPATHY: TraitValue(TraitDimension.EMPATHY, 0.9, 0.5, 1.0),
                TraitDimension.DIRECTNESS: TraitValue(TraitDimension.DIRECTNESS, 0.4, 0.1, 0.7),
                TraitDimension.VERBOSITY: TraitValue(TraitDimension.VERBOSITY, 0.6, 0.3, 0.9),
                TraitDimension.TECHNICALITY: TraitValue(TraitDimension.TECHNICALITY, 0.3, 0.1, 0.6),
                TraitDimension.ASSERTIVENESS: TraitValue(TraitDimension.ASSERTIVENESS, 0.4, 0.2, 0.7),
                TraitDimension.ENTHUSIASM: TraitValue(TraitDimension.ENTHUSIASM, 0.8, 0.5, 1.0),
            },
        )

    BUILTIN_PROFILES: ClassVar[dict[str, Callable[[], TraitProfile]]] = {
        "persona_pro": _persona_pro,
        "persona_dev": _persona_dev,
        "persona_terrain": _persona_terrain,
    }

    @classmethod
    def create_builtin(cls, name: str) -> Optional[TraitProfile]:
        """Crée un profil prédéfini par son nom."""
        fn = cls.BUILTIN_PROFILES.get(name)
        if fn:
            return fn()
        return None
