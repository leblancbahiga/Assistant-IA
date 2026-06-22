"""ProactiveEngine — Moteur de proactivité.

Détecte les opportunités d'action non sollicitées à partir de signaux :
  - Temporels (heure, jour, calendrier)
  - Contextuels (état du système, mémoire)
  - Comportementaux (patterns d'utilisation)
  - Externes (notifications, événements)
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class SignalPriority(enum.Enum):
    """Priorité des signaux proactifs."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class SignalCategory(enum.Enum):
    """Catégories de signaux."""
    TEMPORAL = "temporal"
    CONTEXTUAL = "contextual"
    BEHAVIORAL = "behavioral"
    EXTERNAL = "external"
    MEMORY = "memory"


@dataclass
class Signal:
    """Signal détecté par le moteur."""
    id: str
    category: SignalCategory
    priority: SignalPriority
    description: str
    source: str                       # e.g., "clock", "knowledge_graph", "calendar"
    timestamp: float = 0.0
    data: dict = field(default_factory=dict)
    confidence: float = 1.0
    dismissed: bool = False
    executed: bool = False

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class Action:
    """Action proactive proposée."""
    id: str
    signal_id: str
    description: str
    action_type: str      # "suggest", "execute", "remind", "inform"
    prompt: str           # Prompt pour le LLM
    priority: SignalPriority
    ttl_seconds: int = 3600  # Expiration
    created_at: float = 0.0
    approved: bool = False
    rejected: bool = False

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()

    @property
    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl_seconds


@dataclass
class ActionPlan:
    """Plan d'actions proactives décidées."""
    actions: list[Action] = field(default_factory=list)
    evaluation: str = ""
    llm_used: bool = False

    def add(self, action: Action) -> None:
        self.actions.append(action)

    def pending_actions(self) -> list[Action]:
        return [a for a in self.actions if not a.approved and not a.rejected and not a.is_expired]


class ProactiveEngine:
    """Moteur de proactivité.

    Usage :
        engine = ProactiveEngine()
        engine.register_collector("clock", clock_collector)
        engine.register_collector("memory", memory_collector)
        plan = await engine.evaluate()
        for action in plan.pending_actions():
            print(action.description)
    """

    def __init__(self):
        self._collectors: dict[str, Callable[[], list[Signal]]] = {}
        self._signals: list[Signal] = []
        self._action_history: list[Action] = []
        self._on_signal: Optional[Callable[[Signal], None]] = None
        self._on_action: Optional[Callable[[Action], None]] = None

    def register_collector(self, name: str, collector_fn: Callable[[], list[Signal]]) -> None:
        """Enregistre un collecteur de signaux.

        Args:
            name: Identifiant du collecteur
            collector_fn: Fonction retournant une liste de signaux
        """
        self._collectors[name] = collector_fn
        logger.info(f"Collecteur '{name}' enregistré")

    def remove_collector(self, name: str) -> None:
        self._collectors.pop(name, None)

    async def collect_signals(self) -> list[Signal]:
        """Collecte les signaux de tous les collecteurs enregistrés.

        Returns:
            Signaux collectés (filtrés : non expirés, haute confiance)
        """
        all_signals: list[Signal] = []
        for name, collector in self._collectors.items():
            try:
                signals = collector()
                for s in signals:
                    s.source = name
                    if self._on_signal:
                        self._on_signal(s)
                all_signals.extend(signals)
            except Exception as e:
                logger.error(f"Erreur collecteur '{name}': {e}")

        # Filtrer
        active = [
            s for s in all_signals
            if not s.dismissed and s.confidence >= 0.3
        ]

        self._signals = active
        return active

    async def evaluate(self, llm_client=None) -> ActionPlan:
        """Évalue les signaux et décide des actions proactives.

        Args:
            llm_client: Client LLM optionnel (si None, règles simples)

        Returns:
            ActionPlan avec les actions proposées
        """
        signals = await self.collect_signals()
        plan = ActionPlan()

        if not signals:
            return plan

        if llm_client:
            # Évaluation LLM
            try:
                prompt = self._build_evaluation_prompt(signals)
                response = await llm_client.chat(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=500,
                    temperature=0.3,
                )
                text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                plan.evaluation = text
                plan.llm_used = True

                # Actions générées par le LLM
                for sig in signals[:3]:  # Top 3 signaux
                    if sig.priority.value >= SignalPriority.MEDIUM.value:
                        action = Action(
                            id=f"action_{time.time_ns()}_{sig.id}",
                            signal_id=sig.id,
                            description=sig.description,
                            action_type="suggest",
                            prompt=text,
                            priority=sig.priority,
                        )
                        plan.add(action)
                        if self._on_action:
                            self._on_action(action)
            except Exception as e:
                logger.error(f"Erreur évaluation LLM: {e}")

        else:
            # Règles simples
            for sig in signals:
                if sig.priority == SignalPriority.CRITICAL:
                    action = Action(
                        id=f"action_{time.time_ns()}_{sig.id}",
                        signal_id=sig.id,
                        description=sig.description,
                        action_type="inform",
                        prompt=f"Action automatique: {sig.description}",
                        priority=sig.priority,
                    )
                    plan.add(action)

        return plan

    def _build_evaluation_prompt(self, signals: list[Signal]) -> str:
        """Génère le prompt d'évaluation pour le LLM."""
        lines = [
            "Tu es NURU. Voici les signaux contextuels détectés.",
            "Évalue si une action proactive est pertinente.",
            "Réponds par 'ACTION: description' ou 'IGNORE' pour chaque signal.\n",
        ]
        for s in signals:
            lines.append(
                f"[{s.priority.name}] {s.category.value}: {s.description} "
                f"(confiance: {s.confidence:.1f})"
            )
        return "\n".join(lines)

    def dismiss(self, signal_id: str) -> None:
        """Ignore un signal."""
        for s in self._signals:
            if s.id == signal_id:
                s.dismissed = True
                break

    def approve_action(self, action_id: str) -> None:
        """Approuve une action proposée."""
        for plan_signal in self._signals:
            for action in self._action_history:
                if action.id == action_id:
                    action.approved = True
                    break

    def reject_action(self, action_id: str) -> None:
        """Rejette une action proposée."""
        for action in self._action_history:
            if action.id == action_id:
                action.rejected = True
                break

    def set_signal_callback(self, callback: Callable[[Signal], None]) -> None:
        self._on_signal = callback

    def set_action_callback(self, callback: Callable[[Action], None]) -> None:
        self._on_action = callback

    def to_dict(self) -> dict:
        return {
            "n_collectors": len(self._collectors),
            "n_active_signals": len(self._signals),
            "n_action_history": len(self._action_history),
            "collectors": list(self._collectors.keys()),
        }
