"""PersonaEngine — Moteur de personnalité.

Point d'entrée unique pour appliquer une personnalité à NURU.
Intègre les ValueGuardrails et génère les instructions de prompt.
Utilisé par le DynamicPromptBuilder (Phase 3).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .traits import TraitProfile, TraitDimension
from .guardrails import ValueGuardrails, GuardrailRule

logger = logging.getLogger(__name__)

PERSONA_DIR = Path.home() / ".nuru" / "personas"


@dataclass
class Persona:
    """Persona complète avec profil et garde-fous."""
    name: str
    profile: TraitProfile
    description: str = ""
    is_active: bool = False

    @classmethod
    def builtin(cls, name: str) -> Optional[Persona]:
        """Charge une persona prédéfinie."""
        profile = TraitProfile.create_builtin(name)
        if profile:
            return cls(name=name, profile=profile, description=profile.description)
        return None


@dataclass
class PersonaEngine:
    """Moteur de personnalité — point d'entrée unique.

    Gère le cycle de vie des personas et l'injection dans le prompt système.
    """

    active_persona: Optional[Persona] = None
    guardrails: ValueGuardrails = field(default_factory=ValueGuardrails)
    personas: dict[str, Persona] = field(default_factory=dict)

    def __post_init__(self):
        self._load_builtins()
        # Default : persona_pro
        if not self.active_persona:
            self.activate("persona_pro")

    def _load_builtins(self) -> None:
        for name in TraitProfile.BUILTIN_PROFILES:
            persona = Persona.builtin(name)
            if persona:
                self.personas[name] = persona

    def activate(self, name: str) -> bool:
        """Active une persona par son nom."""
        if name in self.personas:
            if self.active_persona:
                self.active_persona.is_active = False
            self.active_persona = self.personas[name]
            self.active_persona.is_active = True
            logger.info(f"🎭 Persona activée: {name}")
            return True
        logger.warning(f"Persona inconnue: {name}")
        return False

    def register_persona(self, persona: Persona) -> None:
        """Enregistre une persona personnalisée."""
        self.personas[persona.name] = persona
        PERSONA_DIR.mkdir(parents=True, exist_ok=True)
        path = PERSONA_DIR / f"{persona.name}.json"
        with open(path, "w") as f:
            json.dump({
                "name": persona.name,
                "profile": persona.profile.to_dict(),
                "description": persona.description,
            }, f, indent=2)

    def get_builtin_names(self) -> list[str]:
        return list(TraitProfile.BUILTIN_PROFILES.keys())

    def get_active_trait(self, dimension: TraitDimension) -> float:
        """Valeur courante d'un trait (avec garde-fous)."""
        if not self.active_persona:
            return 0.5
        tv = self.active_persona.profile.traits.get(dimension)
        if tv:
            return tv.value
        return 0.5

    def build_prompt_instructions(self) -> str:
        """Génère les instructions de personnalité pour le prompt système.

        Appelé par DynamicPromptBuilder (Phase 3).
        """
        if not self.active_persona:
            return ""

        parts = [f"🎭 Persona active : {self.active_persona.name}"]
        profile = self.active_persona.profile

        # Mapping traits → instructions comportementales
        trait_map = {
            TraitDimension.FORMALITY: (
                "Formalité",
                "Utilise un langage formel, vouvoie, structure tes réponses.",
                "Utilise un langage décontracté, tutoie, sois naturel.",
            ),
            TraitDimension.HUMOR: (
                "Humour",
                "Garde un ton sérieux et professionnel.",
                "Tu peux utiliser de l'humour léger si approprié.",
            ),
            TraitDimension.EMPATHY: (
                "Empathie",
                "Reste factuel et neutre émotionnellement.",
                "Montre de l'empathie et de la chaleur dans tes réponses.",
            ),
            TraitDimension.DIRECTNESS: (
                "Directivité",
                "Sois diplomate, suggère plutôt qu'affirme.",
                "Sois direct, va droit au but.",
            ),
            TraitDimension.VERBOSITY: (
                "Verbosite",
                "Sois concis, réponds en peu de mots.",
                "Tu peux développer, donne des explications détaillées.",
            ),
            TraitDimension.TECHNICALITY: (
                "Technicité",
                "Vulgarise, évite le jargon technique.",
                "Utilise le vocabulaire technique précis.",
            ),
        }

        for dim, (label, low_desc, high_desc) in trait_map.items():
            val = self.get_active_trait(dim)
            instruction = low_desc if val < 0.4 else (high_desc if val > 0.6 else "Équilibre.")
            parts.append(f"- {label} ({val:.1f}) : {instruction}")

        # Ajouter les garde-fous HARD
        parts.append("")
        for rule in self.guardrails.rules:
            parts.append(rule.to_prompt_instruction())

        return "\n".join(parts)

    def to_dict(self) -> dict:
        return {
            "active_persona": self.active_persona.name if self.active_persona else None,
            "available": list(self.personas.keys()),
            "guardrails": self.guardrails.to_dict(),
        }
