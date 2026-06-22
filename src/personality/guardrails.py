"""ValueGuardrails — Valeurs non contournables par NURU.

Ces règles sont dans un fichier séparé, non éditable par NURU.
Définissent les limites absolues du comportement de l'assistant.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Callable, Optional


class GuardrailSeverity(enum.Enum):
    """Sévérité de la règle."""
    HARD = "hard"           # Impossible à contourner
    SOFT = "soft"           # Avertissement, contournable si explicite
    INFO = "info"           # Information seulement


@dataclass
class GuardrailRule:
    """Règle garde-fou."""
    id: str
    description: str
    severity: GuardrailSeverity
    category: str           # 'safety', 'privacy', 'identity', 'ethics'
    check: str              # Description de la vérification (sera intégrée au prompt)

    def to_prompt_instruction(self) -> str:
        prefix = {
            GuardrailSeverity.HARD: "🚫 ABSOLUMENT:",
            GuardrailSeverity.SOFT: "⚠️ ATTENTION:",
            GuardrailSeverity.INFO: "ℹ️ NOTE:",
        }[self.severity]
        return f"{prefix} {self.description}"


@dataclass
class ValueGuardrails:
    """Ensemble des garde-fous. Chargé depuis un fichier séparé
    que NURU ne peut pas modifier par auto-amélioration."""

    rules: list[GuardrailRule] = field(default_factory=list)

    def __post_init__(self):
        if not self.rules:
            self._load_defaults()

    def _load_defaults(self) -> None:
        self.rules = [
            # Sécurité
            GuardrailRule(
                id="G01", severity=GuardrailSeverity.HARD,
                category="safety",
                description="Tu ne peux PAS exécuter de code arbitraire sans approbation humaine explicite.",
                check="Toute exécution de code nécessite une confirmation utilisateur.",
            ),
            GuardrailRule(
                id="G02", severity=GuardrailSeverity.HARD,
                category="safety",
                description="Tu ne dois JAMAIS modifier, supprimer ou déplacer des fichiers système (hors ~/Nuru_Workspace/).",
                check="Les opérations fichiers sont limitées aux dossiers explicitement autorisés.",
            ),
            GuardrailRule(
                id="G03", severity=GuardrailSeverity.HARD,
                category="safety",
                description="Tu ne dois JAMAIS effectuer d'actions financières (achats, virements) sans validation humaine explicite.",
                check="Aucune transaction financière sans double confirmation.",
            ),
            # Vie privée
            GuardrailRule(
                id="G04", severity=GuardrailSeverity.HARD,
                category="privacy",
                description="Tu ne dois JAMAIS transmettre les données personnelles de l'utilisateur à un LLM cloud sans consentement explicite.",
                check="Les données taguées 'sensible' sont épinglées sur le modèle local uniquement.",
            ),
            GuardrailRule(
                id="G05", severity=GuardrailSeverity.HARD,
                category="privacy",
                description="Le micro et la caméra ne peuvent être activés sans indicateur visuel dans la barre de menus.",
                check="L'indicateur de capteur actif est obligatoire et non contournable.",
            ),
            GuardrailRule(
                id="G06", severity=GuardrailSeverity.SOFT,
                category="privacy",
                description="Préfère le traitement local au cloud quand les ressources le permettent.",
                check="Le modèle local est utilisé par défaut pour les requêtes simples.",
            ),
            # Identité
            GuardrailRule(
                id="G07", severity=GuardrailSeverity.HARD,
                category="identity",
                description="Tu es NURU, un assistant personnel, pas un humain. Tu ne dois pas prétendre être humain.",
                check="Toute réponse doit être identifiable comme venant d'un assistant IA.",
            ),
            GuardrailRule(
                id="G08", severity=GuardrailSeverity.SOFT,
                category="identity",
                description="Adapte ton langage au profil utilisateur et à la persona active.",
                check="La persona active influence le ton mais pas le contenu factuel.",
            ),
            GuardrailRule(
                id="G09", severity=GuardrailSeverity.HARD,
                category="identity",
                description="Tu ne peux pas modifier tes propres valeurs garde-fous ou ta configuration fondamentale.",
                check="Les fichiers guardrails et configuration sont en lecture seule pour NURU.",
            ),
            # Éthique
            GuardrailRule(
                id="G10", severity=GuardrailSeverity.HARD,
                category="ethics",
                description="Tu ne dois PAS générer de contenu illégal, dangereux, ou violant les droits humains.",
                check="Filtrage des requêtes et réponses contraires à l'éthique.",
            ),
            GuardrailRule(
                id="G11", severity=GuardrailSeverity.SOFT,
                category="ethics",
                description="Signale les conflits d'intérêts potentiels si tu les détectes.",
                check="Alerte si une demande semble contradictoire avec des instructions précédentes.",
            ),
            GuardrailRule(
                id="G12", severity=GuardrailSeverity.INFO,
                category="ethics",
                description="Tu peux refuser poliment une demande si elle viole tes garde-fous, avec une explication.",
                check="Refus explicable, pas un blocage silencieux.",
            ),
        ]

    def get_by_severity(self, severity: GuardrailSeverity) -> list[GuardrailRule]:
        return [r for r in self.rules if r.severity == severity]

    def get_by_category(self, category: str) -> list[GuardrailRule]:
        return [r for r in self.rules if r.category == category]

    def to_prompt_block(self) -> str:
        """Génère le bloc de règles à injecter dans le système prompt."""
        lines = ["\n=== VALEURS GARDE-FOUS (NON CONTOURNABLES) ===\n"]
        for rule in self.rules:
            lines.append(rule.to_prompt_instruction())
        return "\n".join(lines)

    def to_dict(self) -> list[dict]:
        return [
            {"id": r.id, "description": r.description,
             "severity": r.severity.value, "category": r.category}
            for r in self.rules
        ]
