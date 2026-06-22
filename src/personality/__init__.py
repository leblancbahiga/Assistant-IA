"""NURU PersonaEngine — Phase 2a + Phase 3.

Couche d'identité au-dessus du prompt dynamique.
Traits configurables, valeurs garde-fous non contournables, presets.
"""

from .traits import TraitProfile, TraitDimension, TraitValue
from .engine import PersonaEngine, Persona
from .guardrails import ValueGuardrails, GuardrailRule

__all__ = [
    "PersonaEngine", "Persona",
    "TraitProfile", "TraitDimension", "TraitValue",
    "ValueGuardrails", "GuardrailRule",
]
