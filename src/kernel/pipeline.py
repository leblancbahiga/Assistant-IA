"""
NURU Kernel — Pipeline Engine (Phase 3.9).

Remplace la méthode monolithique process_query() par des steps composables.
Chaque step est un objet mesurable, traçable, remplaçable.

Principe :
    Le Kernel ne répond jamais — il orchestre.
    PipelineEngine enchaîne les steps, mesure, et retourne un résultat.

Usage :
    pipeline = PipelineEngine()
    pipeline.add_step(ReceiveQuestion())
    pipeline.add_step(Route())
    pipeline.add_step(Retrieve())
    pipeline.add_step(BuildContext())
    pipeline.add_step(Generate())
    pipeline.add_step(Validate())
    pipeline.add_step(Respond())

    result = await pipeline.run("ma question", session_id="abc")
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Optional

logger = logging.getLogger(__name__)


# ── État du pipeline ──────────────────────────────────────────

@dataclass
class PipelineContext:
    """État mutable qui traverse tous les steps du pipeline.

    Chaque step lit et/ou écrit dans ce contexte.
    Les champs sont optionnels — un step peut en produire, un autre les consommer.
    """
    # Entrée
    query: str
    session_id: str = "default"
    use_tts: bool = False
    audio_engine: Any = None
    stream_session: Any = None  # StreamSession V15 P2 #26
    is_online: bool = True

    # Routage
    route_decision: str = ""
    route_confidence: float = 0.0
    intent: str = "GENERAL"      # RAG | GENERAL | COMPLEX | SIMPLE | TOOL
    v16_decision: Any = None     # DecisionV16 si disponible

    # RAG
    rag_context: str = ""
    web_context: str = ""
    rag_result: Any = None       # SearchResult du RAG engine
    spotlight_context: str = ""
    has_agent_delegated: bool = False

    # Cache
    cache_hit: bool = False
    cached_response: str = ""

    # Prompt
    system_prompt: str = ""
    full_prompt: str = ""
    user_facts_str: str = ""

    # Génération
    response: str = ""
    streaming: bool = True
    use_tot: bool = False        # Tree of Thoughts
    use_cot: bool = False        # Chain of Thought
    use_sc: bool = False         # Self-Consistency
    model_used: str = ""
    tokens_generated: int = 0
    tokens_prompt: int = 0

    # Timing et métadonnées
    correlation_id: str = ""
    started_at: float = 0.0
    step_timings: dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None
    strict_refused: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query[:80],
            "intent": self.intent,
            "route": self.route_decision,
            "response_len": len(self.response),
            "tokens": self.tokens_generated,
            "model": self.model_used,
            "error": self.error,
            "steps": dict(self.step_timings),
            "correlation_id": self.correlation_id,
            "duration_s": round(time.time() - self.started_at, 2) if self.started_at else 0,
        }

    @staticmethod
    def _route_to_intent(decision: str) -> str:
        """Convertit la décision du routeur en intent standard."""
        mapping = {
            "RAG": "RAG", "WEB": "COMPLEX", "GENERAL": "GENERAL",
            "HYBRID": "RAG", "TOOL": "COMPLEX", "AGENT": "COMPLEX",
        }
        return mapping.get(decision.upper(), "GENERAL")

    @staticmethod
    def _model_for_intent(intent: str) -> str:
        """Retourne la famille de modèle recommandée pour un intent."""
        if intent == "RAG":
            return "phi-4"
        if intent == "COMPLEX":
            return "cloud"
        return "phi-4"


# ── Step abstrait ─────────────────────────────────────────────

@dataclass
class StepResult:
    """Résultat d'un step individuel.

    - success : le step s'est terminé normalement
    - skip_pipeline : True si le pipeline doit s'arrêter (cache hit, strict refused, etc.)
    - response_ready : si skip_pipeline, la réponse à retourner immédiatement
    - error : message d'erreur si échec
    """
    success: bool = True
    skip_pipeline: bool = False
    response_ready: str = ""
    error: Optional[str] = None


class PipelineStep(ABC):
    """Step composable du pipeline NURU.

    Chaque step :
    - a un nom (utilisé pour le timing et le logging)
    - reçoit le PipelineContext
    - le modifie et le retourne
    - peut demander l'arrêt du pipeline (cache hit, guard block)
    """

    def __init__(self) -> None:
        self.name: str = self.__class__.__name__
        self.duration: float = 0.0

    @abstractmethod
    async def run(self, ctx: PipelineContext) -> tuple[PipelineContext, StepResult]:
        ...

    def __repr__(self) -> str:
        return f"<Step {self.name}>"


# ── Moteur du pipeline ────────────────────────────────────────

class PipelineEngine:
    """Moteur de pipeline : enchaîne les steps dans l'ordre.

    Chaque step produit un StepResult :
    - Si skip_pipeline → arrête l'enchaînement et retourne la réponse
    - Si error → arrête, ctx.error est positionné
    - Sinon → continue au step suivant

    Usage :
        engine = PipelineEngine()
        engine.set_steps(steps_list)  # ou add_step() un par un

        # Mode AsyncGenerator (streaming) :
        async for token in engine.run_stream(query):
            ...

        # Mode direct (résultat complet) :
        ctx = await engine.run(query)
    """

    def __init__(self) -> None:
        self._steps: list[PipelineStep] = []
        self._event_bus: Any = None  # Résolu lazy via kernel

    @property
    def event_bus(self) -> Any:
        if self._event_bus is None:
            try:
                from src.kernel import NuruKernel
                self._event_bus = NuruKernel().get("event_bus")
            except Exception:
                pass
        return self._event_bus

    def add_step(self, step: PipelineStep, index: Optional[int] = None) -> None:
        """Ajoute un step à la séquence. Optionnellement à un index précis."""
        if index is not None:
            self._steps.insert(index, step)
        else:
            self._steps.append(step)
        logger.info("➕ Step ajouté: %s (total=%d)", step.name, len(self._steps))

    def set_steps(self, steps: list[PipelineStep]) -> None:
        """Remplace tous les steps (reset complet)."""
        self._steps = list(steps)
        logger.info("🔄 Pipeline: %d steps configurés", len(self._steps))

    async def run(self, query: str, session_id: str = "default",
                  **kwargs) -> PipelineContext:
        """Exécute tout le pipeline, retourne le contexte final.

        Args:
            query: Question utilisateur
            session_id: ID de session
            **kwargs: Surcharges pour PipelineContext (use_tts, audio_engine, etc.)
        """
        ctx = PipelineContext(
            query=query,
            session_id=session_id,
            started_at=time.time(),
            **kwargs,
        )

        # Émettre start
        eb = self.event_bus
        if eb:
            await eb.emit("pipeline.start", {"query": query[:80], "session_id": session_id})

        for step in self._steps:
            t0 = time.time()
            try:
                ctx, result = await step.run(ctx)
            except Exception as e:
                ctx.error = f"{step.name}: {e}"
                logger.exception("❌ Pipeline error dans %s: %s", step.name, e)
                break

            step.duration = time.time() - t0
            ctx.step_timings[step.name] = round(step.duration, 3)

            if not result.success:
                ctx.error = result.error or f"{step.name}: échec"
                logger.warning("⚠️ Pipeline step %s: %s", step.name, ctx.error)
                break

            if result.skip_pipeline:
                ctx.response = result.response_ready
                logger.info("⏭️ Pipeline arrêté par %s (skip)", step.name)
                break

        # Timing total
        total = time.time() - ctx.started_at
        logger.info(
            "🏁 Pipeline terminé: %.2fs | %d steps | intent=%s | err=%s",
            total, len(self._steps), ctx.intent, ctx.error or "none",
        )

        if eb:
            await eb.emit("pipeline.complete", ctx.to_dict())

        return ctx

    async def run_stream(self, query: str, session_id: str = "default",
                         **kwargs) -> AsyncGenerator[str, None]:
        """Exécute le pipeline avec streaming.

        Pour l'instant, délègue à l'orchestrateur existant.
        Les steps de génération produiront le streaming à terme.
        """
        # Phase 1 : exécution normale (non-streaming pour les steps amont)
        ctx = await self.run(query, session_id=session_id, **kwargs)

        # Phase 2 : yield la réponse
        if ctx.response:
            # Yielder par mots (respecte les frontières)
            from src.core.orchestrator import _yield_by_words
            for chunk in _yield_by_words(ctx.response):
                yield chunk
                await asyncio.sleep(0)

    # ── Cycle de vie kernel ───────────────────────────────────

    def start(self) -> None:
        """Appelé par kernel.boot()."""
        logger.info(
            "▶️ PipelineEngine prêt (%d steps: %s)",
            len(self._steps),
            [s.name for s in self._steps],
        )

    def stop(self) -> None:
        """Appelé par kernel.shutdown()."""
        logger.info("⏹️ PipelineEngine arrêté")

    def __repr__(self) -> str:
        return f"<PipelineEngine {len(self._steps)} steps>"
