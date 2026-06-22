"""ContextualLearner — Apprentissage contextuel.

Analyse les interactions NURU↔utilisateur pour extraire des patterns
et ajuster le comportement proactif. Mise à jour du Knowledge Graph.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.knowledge.graph import KnowledgeGraph

logger = logging.getLogger(__name__)


@dataclass
class InteractionPattern:
    """Pattern d'interaction appris."""
    pattern_id: str
    trigger: str                    # e.g., "user_asks_time"
    frequency: int = 1
    last_seen: float = 0.0
    typical_response: str = ""
    entities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.pattern_id,
            "trigger": self.trigger,
            "frequency": self.frequency,
            "entities": self.entities,
        }


@dataclass
class ContextualLearner:
    """Apprentissage contextuel à partir des interactions.

    Usage :
        learner = ContextualLearner(knowledge_graph)
        learner.record_interaction("demande_météo", ["météo", "temps"])
        patterns = learner.get_frequent_patterns()
    """

    knowledge: Optional[KnowledgeGraph] = None
    patterns: dict[str, InteractionPattern] = field(default_factory=dict)

    # Fichier de patterns persistants
    pattern_file: Path = Path.home() / ".nuru" / "patterns.json"

    def __post_init__(self):
        self._load_patterns()

    def _load_patterns(self) -> None:
        """Charge les patterns persistés."""
        if self.pattern_file.exists():
            try:
                data = json.loads(self.pattern_file.read_text())
                for item in data:
                    p = InteractionPattern(**item)
                    self.patterns[p.pattern_id] = p
            except Exception as e:
                logger.error(f"Erreur chargement patterns: {e}")

    def _save_patterns(self) -> None:
        """Persiste les patterns."""
        self.pattern_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.pattern_file.write_text(
                json.dumps([p.to_dict() for p in self.patterns.values()], indent=2)
            )
        except Exception as e:
            logger.error(f"Erreur sauvegarde patterns: {e}")

    def record_interaction(self, trigger: str, entities: list[str] | None = None,
                           response: str = "") -> None:
        """Enregistre une interaction.

        Args:
            trigger: Déclencheur de l'interaction
            entities: Entités associées (optionnelles)
            response: Réponse typique (optionnelle)
        """
        pattern_id = f"pattern_{trigger.lower().replace(' ', '_')}"

        if pattern_id in self.patterns:
            p = self.patterns[pattern_id]
            p.frequency += 1
            p.last_seen = time.time()
            if response:
                p.typical_response = response
            if entities:
                for e in entities:
                    if e not in p.entities:
                        p.entities.append(e)
        else:
            self.patterns[pattern_id] = InteractionPattern(
                pattern_id=pattern_id,
                trigger=trigger,
                frequency=1,
                last_seen=time.time(),
                typical_response=response,
                entities=entities or [],
            )

        # Mettre à jour le Knowledge Graph
        if self.knowledge:
            try:
                self.knowledge.add_node(
                    label=trigger,
                    entity_type="pattern",
                    metadata={"frequency": self._get_frequency(trigger)},
                )
                for entity in (entities or []):
                    self.knowledge.add_node(label=entity, entity_type="entity")
                    # Lier pattern → entité
                    pattern_node = self.knowledge.search_nodes(trigger, entity_type="pattern", limit=1)
                    entity_node = self.knowledge.search_nodes(entity, entity_type="entity", limit=1)
                    if pattern_node and entity_node:
                        self.knowledge.add_edge(
                            pattern_node[0].id, entity_node[0].id,
                            relation="references", weight=1.0,
                        )
            except Exception as e:
                logger.error(f"Erreur mise à jour KG: {e}")

        self._save_patterns()

    def get_frequent_patterns(self, min_frequency: int = 3) -> list[InteractionPattern]:
        """Retourne les patterns les plus fréquents."""
        return [
            p for p in self.patterns.values()
            if p.frequency >= min_frequency
        ]

    def get_recent_patterns(self, seconds: int = 86400) -> list[InteractionPattern]:
        """Patterns récents (24h par défaut)."""
        cutoff = time.time() - seconds
        return [
            p for p in self.patterns.values()
            if p.last_seen >= cutoff
        ]

    def _get_frequency(self, trigger: str) -> int:
        """Récupère la fréquence d'un pattern."""
        pattern_id = f"pattern_{trigger.lower().replace(' ', '_')}"
        p = self.patterns.get(pattern_id)
        return p.frequency if p else 0

    def get_stats(self) -> dict:
        return {
            "total_patterns": len(self.patterns),
            "frequent": len(self.get_frequent_patterns()),
            "recent_24h": len(self.get_recent_patterns()),
        }
