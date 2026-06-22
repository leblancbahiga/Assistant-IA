"""DynamicPromptBuilder — Construction dynamique du prompt système.

Phase 3 : intègre PersonaEngine + Knowledge Graph + contextuel + émotionnel.
Génère le prompt système à chaque cycle, adapté au contexte actuel.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from src.personality.engine import PersonaEngine
from src.knowledge.graph import KnowledgeGraph

logger = logging.getLogger(__name__)


@dataclass
class PromptContext:
    """Contexte pour la construction du prompt."""
    current_time: str = ""
    active_tasks: list[str] = field(default_factory=list)
    recent_memories: list[str] = field(default_factory=list)
    emotional_state: str = "neutre"
    sleep_phase: str = "awake"
    user_goal: Optional[str] = None
    conversation_history: list[dict] = field(default_factory=list)


@dataclass
class DynamicPromptBuilder:
    """Constructeur de prompt système dynamique.

    Usage :
        builder = DynamicPromptBuilder(persona_engine, knowledge_graph)
        prompt = builder.build(context)
    """

    persona: PersonaEngine
    knowledge: Optional[KnowledgeGraph] = None

    # Templates section par section
    identity_template: str = (
        "Tu es NURU, un système d'exploitation cognitif personnel.\n"
        "Tu fonctionnes sur Mac Apple Silicon et tu es connecté à "
        "un écosystème de mémoire, d'outils et de connaissances.\n\n"
        "{persona_instructions}"
    )

    context_template: str = (
        "\n=== CONTEXTE ACTUEL ===\n"
        "Date et heure : {current_time}\n"
        "{emotional_context}"
        "{task_context}"
        "{sleep_context}"
    )

    memory_template: str = (
        "\n=== MÉMOIRES RÉCENTES ===\n"
        "{memories}"
    )

    knowledge_template: str = (
        "\n=== CONNAISSANCES RELIÉES ===\n"
        "{knowledge}"
    )

    def build(self, ctx: Optional[PromptContext] = None) -> str:
        """Construit le prompt système complet."""
        if ctx is None:
            ctx = PromptContext()

        parts = []

        # 1. Identité + Persona
        persona_instructions = ""
        if self.persona:
            persona_instructions = self.persona.build_prompt_instructions()

        parts.append(self.identity_template.format(
            persona_instructions=persona_instructions,
        ))

        # 2. Contexte
        emotional = ""
        if ctx.emotional_state != "neutre":
            emotional = f"État émotionnel détecté : {ctx.emotional_state}\n"

        tasks = ""
        if ctx.active_tasks:
            tasks = f"Tâches en cours : {', '.join(ctx.active_tasks)}\n"

        sleep = ""
        if ctx.sleep_phase != "awake":
            sleep = f"Phase de sommeil : {ctx.sleep_phase}\n"

        parts.append(self.context_template.format(
            current_time=ctx.current_time or "(non spécifié)",
            emotional_context=emotional,
            task_context=tasks,
            sleep_context=sleep,
        ))

        # 3. Mémoires
        if ctx.recent_memories:
            memories_text = "\n".join(f"- {m}" for m in ctx.recent_memories[-5:])
            parts.append(f"\n=== MÉMOIRES RÉCENTES ===\n{memories_text}")

        # 4. Connaissances reliées
        if self.knowledge and ctx.user_goal:
            try:
                related = self.knowledge.find_related(ctx.user_goal, max_results=5)
                if related:
                    knowledge_text = "\n".join(
                        f"- {n.label} ({n.entity_type})" for n in related
                    )
                    parts.append(self.knowledge_template.format(knowledge=knowledge_text))
            except Exception:
                pass

        return "\n\n".join(parts)
