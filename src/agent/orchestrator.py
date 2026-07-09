"""
NURU V15 — AgentOrchestrator fusionné (P0 #1).

Merge des deux orchestrators :
  - src/tools/agent_orchestrator.py (V12) : 4-phase Plan→Execute→Verify→Synthesize
  - src/agent/orchestrator.py (V9) : multi-step + error recovery + session mgmt

Architecture :
  1. Simple Q&A → run(query) → 4-phase loop (V12 origin)
  2. Multi-step tasks → run_goal(goal, session_id) → Plan→Steps→Recovery (V9 origin)
  3. Les deux modes partagent : singleton thread-safe, lazy RAG/Memory,
     error recovery, benchmark timing V15.

V15 Phase 0B contraintes :
  - max_steps = 3 (limite agent loop)
  - KV cache 8-bit dans LLM local
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from src.agent.types import (
    AGENT_LIMITS,
    AgentState,
    ErrorType,
    RecoveryAction,
    RecoveryDecision,
    StepResult,
    TaskPlan,
    TaskStatus,
    TaskStep,
)

logger = logging.getLogger(__name__)


# ── Dataclasses de traçabilité (V12) ──────────────────────────────────


@dataclass
class AgentTrace:
    """Trace complète d'une exécution agentique (mode simple Q&A).

    Chaque phase enregistre sa durée, son statut et ses artefacts
    pour permettre la traçabilité et le débogage.
    """
    query: str = ""
    status: str = "idle"  # idle | planning | executing | verifying | done | error
    plan_phase: dict[str, Any] = field(default_factory=dict)
    execute_phase: dict[str, Any] = field(default_factory=dict)
    verify_phase: dict[str, Any] = field(default_factory=dict)
    synthesis: str = ""
    rag_context: str = ""
    memory_context: str = ""
    duration_ms: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "status": self.status,
            "plan": self.plan_phase,
            "execute": self.execute_phase,
            "verify": self.verify_phase,
            "synthesis": self.synthesis,
            "rag_context_length": len(self.rag_context),
            "memory_context_length": len(self.memory_context),
            "duration_ms": round(self.duration_ms, 1),
            "error": self.error,
        }


@dataclass
class PlanResult:
    """Résultat de la phase de planification (mode simple Q&A)."""
    decomposed: bool = False
    steps: list[str] = field(default_factory=list)
    rag_available: bool = False
    rag_documents_found: int = 0
    rag_confidence: str = "NONE"
    memory_available: bool = False
    memory_recalled: int = 0


@dataclass
class VerifyResult:
    """Résultat de la phase de vérification (mode simple Q&A)."""
    passed: bool = False
    score: float = 0.0
    reason: str = ""
    has_content: bool = False
    has_sources: bool = False
    has_memory_context: bool = False


# ── Helpers (V9) ──────────────────────────────────────────────────────


def _detect_error_type(
    result: StepResult,
    verifier_result: tuple[bool, float, str] | None = None,
) -> ErrorType:
    """Détermine le type d'erreur à partir du résultat d'étape.

    Ordre de priorité :
      1. Timeout explicite dans l'erreur
      2. Tool failure / erreur d'exécution
      3. Confiance basse (via verifier)
      4. Inconnu
    """
    error_msg = (result.error or "").lower()
    if "timeout" in error_msg:
        return ErrorType.TIMEOUT
    if result.error:
        return ErrorType.TOOL_FAILURE
    if verifier_result is not None:
        _ok, score, reason = verifier_result
        if not _ok and ("confiance" in reason.lower() or "confidence" in reason.lower()):
            return ErrorType.LOW_CONFIDENCE
    return ErrorType.UNKNOWN


def _resolve_step_id(step: TaskStep, steps: list[TaskStep]) -> str:
    """Résout le depends_on symbolique (step_1, step_2…) en ID réel.
    Si depends_on référence 'step_{N}', on retourne l'ID de steps[N-1].
    Sinon, on suppose que step.depends_on contient déjà des IDs réels.
    """
    resolved = []
    for dep in step.depends_on:
        if dep.startswith("step_"):
            try:
                idx = int(dep.split("_")[1]) - 1
                if 0 <= idx < len(steps):
                    resolved.append(steps[idx].step_id)
                else:
                    resolved.append(dep)
            except (ValueError, IndexError):
                resolved.append(dep)
        else:
            resolved.append(dep)
    return resolved[0] if resolved else ""


# ═══════════════════════════════════════════════════════════════════════
# AgentOrchestrator — Fusionné V12 + V9
# ═══════════════════════════════════════════════════════════════════════


class AgentOrchestrator:
    """Orchestrateur agentique fusionné (V15 P0 #1).

    Deux modes d'utilisation :

    **Mode simple Q&A** (V12 origin) :
        orch = AgentOrchestrator()
        result = await orch.run("Quelles sont mes compétences ?")
        # → dict avec query, status, synthesis, trace

    **Mode multi-step** (V9 origin) :
        result = await orch.run_goal("Analyse ce fichier et résume-le", "session_1")
        # → dict avec goal, status, steps, final_response

    Les deux modes partagent :
    - Singleton thread-safe
    - RAGEngine et MemoryManager lazy-initialisés
    - Error recovery via run_step()
    - Session tracking
    - V15 Phase 0B : max_steps=3
    """

    _instance: Optional[AgentOrchestrator] = None
    _singleton_lock: threading.Lock = threading.Lock()
    _initialized: bool = False

    def __new__(cls, *args: Any, **kwargs: Any) -> AgentOrchestrator:
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def __init__(
        self,
        rag_engine: Optional[Any] = None,
        memory_manager: Optional[Any] = None,
    ) -> None:
        """Initialise l'orchestrateur.

        Args:
            rag_engine: Instance de RAGEngine (créée paresseusement si None)
            memory_manager: Instance de MemoryManager (créée paresseusement si None)
        """
        if self._initialized:
            return

        # V12 : lazy RAG/Memory
        self._rag_engine = rag_engine
        self._memory_manager = memory_manager
        self._rag_initialized = False
        self._memory_initialized = False

        # V9 : sous-modules agent (lazy import)
        self._planner = None
        self._executor = None
        self._verifier = None
        self._recovery = None
        self._resume = None

        # V9 : limites de sécurité
        self.limits = dict(AGENT_LIMITS)
        self.limits["max_steps"] = 3  # V15 Phase 0B (P0 #20)

        # V9 : sessions actives
        self._sessions: dict[str, AgentState] = {}

        self._initialized = True
        logger.debug("AgentOrchestrator fusionné (V15 P0 #1) initialisé")

    # ── Singleton helpers ─────────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> AgentOrchestrator:
        """Retourne l'instance unique."""
        return cls()

    @classmethod
    def _reset_singleton(cls) -> None:
        """Réinitialise le singleton (usage tests uniquement)."""
        with cls._singleton_lock:
            cls._instance = None

    # ── Propriétés paresseuses (V12) ──────────────────────────────────

    @property
    def rag_engine(self) -> Any:
        """Accès paresseux à RAGEngine."""
        if self._rag_engine is None and not self._rag_initialized:
            self._rag_initialized = True
            try:
                from src.rag_engine import RAGEngine
                self._rag_engine = RAGEngine()
            except Exception as e:
                logger.warning("RAGEngine non disponible: %s", e)
        return self._rag_engine

    @property
    def memory_manager(self) -> Any:
        """Accès paresseux à MemoryManager."""
        if self._memory_manager is None and not self._memory_initialized:
            self._memory_initialized = True
            try:
                from src.memory.manager import MemoryManager
                self._memory_manager = MemoryManager()
            except Exception as e:
                logger.warning("MemoryManager non disponible: %s", e)
        return self._memory_manager

    # ── Sous-modules agent paresseux (V9) ─────────────────────────────

    @property
    def planner(self) -> Any:
        if self._planner is None:
            from src.agent.planner import TaskPlanner
            self._planner = TaskPlanner()
        return self._planner

    @property
    def executor(self) -> Any:
        if self._executor is None:
            from src.agent.executor import TaskExecutor
            self._executor = TaskExecutor()
        return self._executor

    @property
    def verifier(self) -> Any:
        if self._verifier is None:
            from src.agent.verifier import TaskVerifier
            self._verifier = TaskVerifier()
        return self._verifier

    @property
    def recovery(self) -> Any:
        if self._recovery is None:
            from src.agent.recovery import ErrorRecovery
            self._recovery = ErrorRecovery()
        return self._recovery

    @property
    def resume(self) -> Any:
        if self._resume is None:
            from src.agent.resume import ResumeManager
            self._resume = ResumeManager()
        return self._resume

    # ═══════════════════════════════════════════════════════════════════
    # MODE 1 : Simple Q&A (V12) — 4-phase run(query)
    # ═══════════════════════════════════════════════════════════════════

    async def run(self, query: str) -> dict[str, Any]:
        """Boucle agentique simple : Plan→Execute→Verify→Synthesize.

        Args:
            query: Requête utilisateur

        Returns:
            Dictionnaire structuré avec :
              - query : requête originale
              - status : 'success' | 'partial' | 'error'
              - synthesis : réponse finale synthétisée
              - trace : AgentTrace sérialisé
              - trace_summary : résumé lisible de la trace
        """
        trace = AgentTrace(query=query, status="planning")
        start_time = time.monotonic()

        try:
            if not query or not query.strip():
                trace.status = "error"
                trace.error = "Requête vide"
                return self._build_response(trace)

            # ── 1. PLAN ───────────────────────────────────────────
            plan_start = time.monotonic()
            plan = await self._plan(query)
            trace.plan_phase = {
                "decomposed": plan.decomposed,
                "steps": plan.steps,
                "rag_available": plan.rag_available,
                "rag_documents_found": plan.rag_documents_found,
                "rag_confidence": plan.rag_confidence,
                "memory_available": plan.memory_available,
                "memory_recalled": plan.memory_recalled,
                "duration_ms": round((time.monotonic() - plan_start) * 1000, 1),
            }

            # ── 2. EXECUTE ────────────────────────────────────────
            trace.status = "executing"
            exec_start = time.monotonic()
            execute_result = await self._execute(query, plan)
            trace.rag_context = execute_result.get("rag_context", "")
            trace.memory_context = execute_result.get("memory_context", "")
            trace.execute_phase = {
                "rag_context_length": len(trace.rag_context),
                "memory_context_length": len(trace.memory_context),
                "sources_count": execute_result.get("sources_count", 0),
                "duration_ms": round((time.monotonic() - exec_start) * 1000, 1),
            }

            # ── 3. VERIFY ─────────────────────────────────────────
            trace.status = "verifying"
            verify_start = time.monotonic()
            verify_result = self._verify(trace, plan)
            trace.verify_phase = {
                "passed": verify_result.passed,
                "score": round(verify_result.score, 3),
                "reason": verify_result.reason,
                "has_content": verify_result.has_content,
                "has_sources": verify_result.has_sources,
                "has_memory_context": verify_result.has_memory_context,
                "duration_ms": round((time.monotonic() - verify_start) * 1000, 1),
            }

            # ── 4. SYNTHESIZE ─────────────────────────────────────
            trace.status = "done"
            trace.synthesis = self._synthesize(query, trace, plan, verify_result)
            if verify_result.passed:
                trace.status = "success"
            else:
                trace.status = "partial"

        except Exception as e:
            logger.exception("AgentOrchestrator.run error: %s", e)
            trace.status = "error"
            trace.error = str(e)

        trace.duration_ms = (time.monotonic() - start_time) * 1000
        return self._build_response(trace)

    # ── Phase 1 : PLAN (V12) ──────────────────────────────────────────

    async def _plan(self, query: str) -> PlanResult:
        """Phase de planification : décompose la requête et collecte les contextes.

        1. Décompose la requête en sous-étapes logiques
        2. Consulte RAG pour la recherche documentaire
        3. Consulte MemoryManager pour le contexte utilisateur
        """
        plan = PlanResult()

        # 1. Décomposition simple par mots-clés
        plan.steps = self._decompose_query(query)
        plan.decomposed = len(plan.steps) >= 1

        # 2. Recherche RAG
        rag = self.rag_engine
        if rag is not None:
            try:
                context, result = await rag.retrieve(query)
                plan.rag_available = bool(context and context.strip())
                plan.rag_documents_found = getattr(result, 'documents_found', 0)
                plan.rag_confidence = getattr(result, 'confidence_label', "NONE")
            except Exception as e:
                logger.debug("RAG retrieve failed during plan: %s", e)
                plan.rag_available = False

        # 3. Consultation mémoire
        mem = self.memory_manager
        if mem is not None:
            try:
                memory_context = mem.get_full_context(query)
                if memory_context and memory_context.strip():
                    plan.memory_available = True
                    plan.memory_recalled = len(memory_context.split("\n"))
            except Exception as e:
                logger.debug("Memory recall failed during plan: %s", e)
                plan.memory_available = False

        return plan

    def _decompose_query(self, query: str) -> list[str]:
        """Décompose une requête complexe en sous-requêtes simples.

        Stratégie basée sur la détection de connecteurs (et, ou, puis,
        ainsi que) et de mots interrogatifs multiples.
        """
        if not query:
            return []

        connectors = [
            " et ", " ou ", " puis ", " ainsi que ",
            " de plus ", " également ", " aussi ",
        ]
        for conn in connectors:
            if conn in query.lower():
                parts = [q.strip() for q in query.split(conn) if q.strip()]
                if len(parts) > 1:
                    result = []
                    for p in parts:
                        if not any(w in p.lower() for w in [
                            "quoi", "qui", "où", "quand", "comment",
                            "pourquoi", "quel", "quelle",
                        ]):
                            continue
                        result.append(p)
                    if not result:
                        result = [query]
                    return result

        # Détection de questions multiples (?, ?)
        if query.count("?") > 1:
            parts = [q.strip() + "?" for q in query.split("?") if q.strip()]
            if len(parts) > 1:
                return parts

        return [query]

    # ── Phase 2 : EXECUTE (V12) ───────────────────────────────────────

    async def _execute(
        self,
        query: str,
        plan: PlanResult,
    ) -> dict[str, Any]:
        """Phase d'exécution : collecte les contextes RAG et mémoire.

        Args:
            query: Requête originale
            plan: Résultat de la phase de planification

        Returns:
            Dictionnaire avec rag_context, memory_context, sources_count
        """
        result: dict[str, Any] = {
            "rag_context": "",
            "memory_context": "",
            "sources_count": 0,
        }

        # Collecte RAG
        if plan.rag_available:
            rag = self.rag_engine
            if rag is not None:
                try:
                    context, rag_result = await rag.retrieve(query)
                    result["rag_context"] = context or ""
                    result["sources_count"] = (
                        rag_result.documents_found
                        if hasattr(rag_result, "documents_found")
                        else 0
                    )
                except Exception as e:
                    logger.debug("RAG retrieve failed during execute: %s", e)

        # Collecte mémoire utilisateur
        mem = self.memory_manager
        if mem is not None:
            try:
                profile = mem.get_user_profile()
                if profile:
                    result["memory_context"] = str(profile)
            except Exception as e:
                logger.debug("Memory profile failed during execute: %s", e)

        return result

    # ── Phase 3 : VERIFY (V12) ────────────────────────────────────────

    def _verify(
        self,
        trace: AgentTrace,
        plan: PlanResult,
    ) -> VerifyResult:
        """Phase de vérification : évalue la qualité du résultat.

        Critères :
          - Présence de contenu RAG pertinent
          - Présence de contexte mémoire utilisateur
          - Score de confiance RAG suffisant
          - Cohérence de la réponse

        Args:
            trace: Trace d'exécution
            plan: Résultat de la phase de planification

        Returns:
            VerifyResult avec score, passed, et raison
        """
        has_content = bool(trace.rag_context or trace.memory_context)
        has_sources = plan.rag_documents_found > 0
        has_memory_context = bool(trace.memory_context)

        score = 0.0
        reasons = []

        # Score basé sur la disponibilité RAG
        if plan.rag_confidence == "HAUTE":
            score += 0.4
            reasons.append("confiance RAG haute")
        elif plan.rag_confidence == "MOYENNE":
            score += 0.25
            reasons.append("confiance RAG moyenne")
        elif plan.rag_available:
            score += 0.15
            reasons.append("RAG disponible mais score bas")

        # Score basé sur le contexte mémoire
        if has_memory_context:
            score += 0.3
            reasons.append("contexte mémoire disponible")

        # Score basé sur la présence de contenu
        if has_content:
            score += 0.2
            reasons.append("contexte total présent")

        # Score basé sur les sources documentaires
        if has_sources:
            score += 0.1
            reasons.append(f"{plan.rag_documents_found} source(s)")
        else:
            reasons.append("aucune source documentaire")

        passed = score >= 0.35
        reason_str = ", ".join(reasons)

        return VerifyResult(
            passed=passed,
            score=min(score, 1.0),
            reason=reason_str,
            has_content=has_content,
            has_sources=has_sources,
            has_memory_context=has_memory_context,
        )

    # ── Phase 4 : SYNTHESIZE (V12) ────────────────────────────────────

    def _synthesize(
        self,
        query: str,
        trace: AgentTrace,
        plan: PlanResult,
        verify: VerifyResult,
    ) -> str:
        """Phase de synthèse : construit la réponse finale structurée.

        Combine les contextes RAG et mémoire en une réponse lisible,
        avec indication de confiance et de sources.
        """
        parts = []

        # En-tête de confiance
        if verify.passed:
            confidence_tag = "Confiance: HAUTE" if verify.score >= 0.7 else "Confiance: MOYENNE"
        else:
            confidence_tag = "Confiance: FAIBLE"

        parts.append(f"[RÉSULTAT — {confidence_tag}]")
        parts.append("")

        # Contenu RAG
        if trace.rag_context:
            parts.append("Contexte documentaire :")
            parts.append(trace.rag_context)

        # Contexte mémoire
        if trace.memory_context:
            parts.append("Contexte mémoire :")
            parts.append(trace.memory_context)

        # Synthèse de la réponse basée sur les éléments collectés
        synthesis = self._build_answer(query, trace, plan)
        if synthesis:
            parts.append("")
            parts.append("Synthèse :")
            parts.append(synthesis)

        # Pied de page avec traçabilité
        parts.append("")
        parts.append("---")
        parts.append(
            f"Sources: {plan.rag_documents_found} document(s) | "
            f"Mémoire: {'✅' if plan.memory_available else '❌'} | "
            f"Score: {round(verify.score, 2)}"
        )

        return "\n".join(parts)

    def _build_answer(
        self,
        query: str,
        trace: AgentTrace,
        plan: PlanResult,
    ) -> str:
        """Construit la réponse textuelle à partir des contextes collectés."""
        if not plan.rag_available and not plan.memory_available:
            return (
                "Je n'ai pas trouvé d'information pertinente dans ma base "
                "de connaissance ni dans mes souvenirs pour répondre à cette question."
            )

        lines = []
        if trace.memory_context:
            lines.append("D'après les informations que j'ai sur vous :")
            mem_lines = [l.strip() for l in trace.memory_context.split("\n") if l.strip()]
            lines.extend(mem_lines[:5])

        if trace.rag_context:
            if lines:
                lines.append("")
                lines.append("D'après les documents indexés :")
            rag_preview = trace.rag_context[:500]
            lines.append(rag_preview)

        if not lines:
            return "Informations collectées mais impossibles à synthétiser."

        return "\n".join(lines)

    def _build_response(self, trace: AgentTrace) -> dict[str, Any]:
        """Construit la réponse structurée finale (mode simple Q&A)."""
        return {
            "query": trace.query,
            "status": trace.status,
            "synthesis": trace.synthesis,
            "trace": trace.to_dict(),
            "trace_summary": self._format_trace_summary(trace),
        }

    def _format_trace_summary(self, trace: AgentTrace) -> str:
        """Formate un résumé lisible de la trace d'exécution."""
        parts = [
            f"Agent — {trace.status.upper()}",
            f"  Durée: {trace.duration_ms:.0f} ms",
        ]
        if trace.plan_phase:
            parts.append(
                f"  Plan: {len(trace.plan_phase.get('steps', []))} étape(s), "
                f"RAG={'✅' if trace.plan_phase.get('rag_available') else '❌'}, "
                f"Mémoire={'✅' if trace.plan_phase.get('memory_available') else '❌'}"
            )
        if trace.verify_phase:
            parts.append(
                f"  Vérification: {'✅' if trace.verify_phase.get('passed') else '❌'} "
                f"(score={trace.verify_phase.get('score', 0)})"
            )
        if trace.error:
            parts.append(f"  Erreur: {trace.error}")
        return "\n".join(parts)

    # ═══════════════════════════════════════════════════════════════════
    # MODE 2 : Multi-step (V9) — run_goal() avec plan→steps→recovery
    # ═══════════════════════════════════════════════════════════════════

    async def run_goal(
        self, goal: str, session_id: str = "default"
    ) -> dict[str, Any]:
        """Boucle agentique multi-step.

        1. Planification via TaskPlanner
        2. Exécution séquentielle des étapes avec vérification + recovery
        3. Gestion des erreurs (retry, alternatives, escalation)
        4. Synthèse finale
        5. Sauvegarde état + mémoire

        Args:
            goal:       Objectif utilisateur
            session_id: Identifiant de session

        Returns:
            dict avec :
              - goal           : objectif original
              - status         : 'success' | 'partial' | 'error' | 'interrupted'
              - steps          : liste des résultats d'étapes
              - duration_s     : durée totale en secondes
              - final_response : réponse finale synthétisée
              - session_id     : identifiant de session
        """
        # ── Validation ─────────────────────────────────────────────
        if not goal or not goal.strip():
            return {
                "goal": goal,
                "status": "error",
                "steps": [],
                "duration_s": 0.0,
                "final_response": "Objectif vide — impossible de planifier.",
                "session_id": session_id,
            }

        start_time = time.monotonic()
        max_wall = self.limits.get("max_wall_time_seconds", 300)
        max_steps_limit = self.limits.get("max_steps", 3)
        max_retries = self.limits.get("max_retries_per_step", 3)

        state = AgentState(
            session_id=session_id,
            current_goal=goal,
            started_at=time.time(),
            status="planning",
        )
        self._sessions[session_id] = state

        step_results_list: list[dict[str, Any]] = []
        final_status = "success"

        try:
            # ── 1. Contexte mémoire (si disponible) ────────────────
            memory_ctx = ""
            if self.memory_manager is not None:
                try:
                    similar_errors = self.memory_manager.check_errors(goal)
                    if similar_errors:
                        memory_ctx = "Erreurs similaires détectées : "
                        memory_ctx += "; ".join(
                            f"[{e.get('error_type', '?')}] {e.get('description', '')[:60]}"
                            for e in similar_errors[:3]
                        )
                        logger.info(
                            "⚠️ %s erreur(s) similaire(s) déjà en mémoire",
                            len(similar_errors),
                        )
                except Exception as e:
                    logger.debug("Erreur check_errors: %s", e)

                try:
                    profile = self.memory_manager.get_user_profile()
                    if profile:
                        memory_ctx += "\n" + profile if memory_ctx else profile
                except Exception as e:
                    logger.debug("Erreur get_user_profile: %s", e)

            # ── 2. Planification ───────────────────────────────────
            logger.info("📋 Planification pour : %s…", goal[:80])
            plan: TaskPlan = self.planner.plan(goal)
            state.plan = plan
            state.status = "executing"

            # ── Contrôle max_steps : tronquer si trop d'étapes ─────
            if len(plan.steps) > max_steps_limit:
                logger.warning(
                    "⚠️ Plan tronqué : %d étapes → %d",
                    len(plan.steps), max_steps_limit,
                )
                plan.steps = plan.steps[:max_steps_limit]

            # ── 3. Exécution séquentielle avec recovery ────────────
            for step_idx, step in enumerate(plan.steps):
                elapsed = time.monotonic() - start_time
                if elapsed >= max_wall:
                    logger.warning(
                        "⏰ Temps imparti dépassé (%.1fs ≥ %ds)",
                        elapsed, max_wall,
                    )
                    final_status = "interrupted"
                    break

                state.current_step_index = step_idx
                state.status = "executing"

                remaining_wall = max(0.1, max_wall - elapsed)
                try:
                    step_result = await asyncio.wait_for(
                        self.run_step(step, state),
                        timeout=remaining_wall,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "⏰ Wall timeout étape %d", step_idx + 1,
                    )
                    step_result = StepResult(
                        step_id=step.step_id,
                        status=TaskStatus.FAILED,
                        output=None,
                        error=f"Wall timeout après {elapsed:.1f}s",
                        duration_s=round(elapsed, 3),
                    )
                    final_status = "interrupted"

                state.step_results[step.step_id] = step_result

                step_dict = {
                    "step_id": step.step_id,
                    "description": step.description,
                    "status": step_result.status.value,
                    "output": step_result.output,
                    "error": step_result.error,
                    "duration_s": step_result.duration_s,
                    "confidence": step_result.confidence,
                }
                step_results_list.append(step_dict)

                # Si escalade → arrêt en erreur
                if step_result.status == TaskStatus.FAILED and step_result.error:
                    if "ESCALATE" in (step_result.error or ""):
                        final_status = "error"
                        break
                    final_status = "error"
                    break

            # ── 4. Synthèse ────────────────────────────────────────
            state.status = "done"
            final_response = self.synthesize(state)

            # ── 5. Sauvegarde état (ResumeManager) ─────────────────
            try:
                self.resume.save_state(
                    session_id,
                    {
                        "session_id": session_id,
                        "current_goal": goal,
                        "status": final_status,
                        "step_count": len(step_results_list),
                        "completed_at": time.time(),
                    },
                )
            except Exception as e:
                logger.warning("⚠️ Échec sauvegarde ResumeManager : %s", e)

            # ── 6. Mémoire épisodique ─────────────────────────────
            if self.memory_manager is not None:
                try:
                    self.memory_manager.add_episode(
                        session_id=session_id,
                        goal=goal,
                        status=final_status,
                        steps=step_results_list,
                    )
                except Exception as e:
                    logger.warning("⚠️ Échec enregistrement mémoire : %s", e)

                try:
                    for step_result in step_results_list:
                        if (
                            step_result.get("status") == "failed"
                            and step_result.get("error")
                        ):
                            err_msg = step_result.get("error", "")
                            if "ESCALATE" in err_msg:
                                self.memory_manager.record_error(
                                    error_type="tool_failure",
                                    description=step_result.get("description", ""),
                                    root_cause="Retry épuisé",
                                    correction="",
                                )
                except Exception as e:
                    logger.debug("Échec enregistrement erreurs: %s", e)

        except asyncio.CancelledError:
            final_status = "interrupted"
            final_response = "Tâche interrompue."
        except Exception as exc:
            logger.exception("💥 Erreur orchestrateur : %s", exc)
            final_status = "error"
            final_response = f"Erreur interne : {exc}"

        total_duration = round(time.monotonic() - start_time, 3)

        return {
            "goal": goal,
            "status": final_status,
            "steps": step_results_list,
            "duration_s": total_duration,
            "final_response": final_response,
            "session_id": session_id,
        }

    async def run_step(
        self,
        step: TaskStep,
        state: Optional[AgentState] = None,
    ) -> StepResult:
        """Exécute une étape avec retry et recovery.

        Boucle interne :
        - Exécute via executor.execute(step)
        - Vérifie via verifier.verify(step, result)
        - Si échec et retry possible : recovery.decide → RETRY → ré-exécute
        - Si échec et plus de retry : recovery.decide → ESCALATE → arrête

        Args:
            step:  L'étape à exécuter
            state: État agent optionnel

        Returns:
            StepResult final (succès ou échec avec escalade)
        """
        max_retries = self.limits.get("max_retries_per_step", 3)
        attempt = 0
        last_error: Optional[str] = None

        while attempt <= max_retries:
            if state is not None:
                state.status = "executing"

            try:
                result = await asyncio.wait_for(
                    self.executor.execute(step),
                    timeout=step.timeout_s,
                )
            except asyncio.TimeoutError:
                result = StepResult(
                    step_id=step.step_id,
                    status=TaskStatus.FAILED,
                    output=None,
                    error=f"Timeout après {step.timeout_s}s (étape)",
                    duration_s=float(step.timeout_s),
                )
            except Exception as exc:
                result = StepResult(
                    step_id=step.step_id,
                    status=TaskStatus.FAILED,
                    output=None,
                    error=f"Exception : {exc}",
                    duration_s=0.0,
                )

            # Vérification
            if state is not None:
                state.status = "verifying"

            try:
                is_ok, score, reason = self.verifier.verify(step, result)
            except Exception as exc:
                is_ok, score, reason = False, 0.0, f"Erreur vérification : {exc}"

            result.confidence = score

            # Succès → retour
            if is_ok:
                if state is not None:
                    state.status = "executing"
                return result

            # Échec → décider de la récupération
            error_type = _detect_error_type(result, (is_ok, score, reason))

            if attempt < max_retries:
                decision = self.recovery.decide(
                    error_type=error_type,
                    attempt=attempt,
                    context={
                        "step_id": step.step_id,
                        "step_description": step.description,
                        "result_status": result.status.value,
                        "error": result.error,
                        "verifier_reason": reason,
                    },
                )
            else:
                decision = RecoveryDecision(
                    action=RecoveryAction.ESCALATE,
                    params={
                        "error_type": error_type.value,
                        "attempt": attempt,
                        "max_retries": max_retries,
                    },
                    message=(
                        f"Échec après {attempt + 1} tentative(s). "
                        "Escalade nécessaire."
                    ),
                )

            last_error = (
                f"Tentative {attempt + 1}/{max_retries + 1} échouée : "
                f"{result.error or reason} → {decision.action.value}"
            )

            if decision.action == RecoveryAction.ESCALATE:
                return StepResult(
                    step_id=step.step_id,
                    status=TaskStatus.FAILED,
                    output=result.output,
                    error=(
                        f"ESCALATE: {decision.message} | "
                        f"Dernière erreur : {result.error or reason}"
                    ),
                    duration_s=result.duration_s,
                    confidence=result.confidence,
                    tool_results=result.tool_results,
                )

            if decision.action == RecoveryAction.RETRY_BACKOFF:
                backoff = decision.params.get("backoff_seconds", 2)
                await asyncio.sleep(backoff)

            attempt += 1

        # Sortie de secours (normalement non atteinte)
        return StepResult(
            step_id=step.step_id,
            status=TaskStatus.FAILED,
            output=None,
            error=f"ESCALATE: {last_error or 'Échec inexpliqué'}",
            duration_s=0.0,
        )

    def synthesize(self, state: AgentState) -> str:
        """Agrège les résultats des étapes en une réponse finale (mode multi-step).

        Args:
            state: L'état final de l'agent

        Returns:
            Réponse texte formatée
        """
        if not state.plan or not state.plan.steps:
            return "Aucune étape n'a été exécutée."

        parts: list[str] = []
        success_count = 0
        fail_count = 0

        for step in state.plan.steps:
            result = state.step_results.get(step.step_id)
            if result is None:
                continue

            if result.is_success:
                success_count += 1
                output = result.output or ""
                if output:
                    parts.append(f"✅ {step.description}\n{output}")
            else:
                fail_count += 1
                error = result.error or "Erreur inconnue"
                parts.append(f"❌ {step.description}\nErreur : {error}")

        if not parts:
            return "Aucun résultat disponible."

        header = f"📊 Synthèse : {success_count} étape(s) réussie(s)"
        if fail_count > 0:
            header += f", {fail_count} échec(s)"

        return header + "\n\n" + "\n\n".join(parts)

    def get_progress(self, session_id: str) -> dict[str, Any] | None:
        """Retourne l'état actuel d'une session via ResumeManager.

        Args:
            session_id: Identifiant de la session

        Returns:
            Dictionnaire d'état ou None si introuvable
        """
        # D'abord chercher dans les sessions actives
        state = self._sessions.get(session_id)
        if state is not None:
            return state.to_dict()

        # Sinon chercher dans ResumeManager
        try:
            saved = self.resume.load_state(session_id)
            if saved is not None:
                return saved
        except Exception:
            pass

        return None

    # ── API publiques auxiliaires (V12) ───────────────────────────────

    async def plan(self, goal: str) -> list[str]:
        """Décompose un objectif en étapes (API publique pour agent_plan).

        Args:
            goal: Objectif à décomposer

        Returns:
            Liste d'étapes
        """
        plan = await self._plan(goal)
        return plan.steps

    async def verify_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Vérifie la qualité d'un résultat (API publique pour agent_verify).

        Args:
            result: Résultat à vérifier (dict)

        Returns:
            Dictionnaire avec passed, score, reason
        """
        query = result.get("query", "") if isinstance(result, dict) else str(result)
        plan = PlanResult()

        if isinstance(result, dict):
            plan.rag_available = bool(result.get("rag_context", ""))
            plan.rag_documents_found = result.get("sources_count", 0)
            plan.memory_available = bool(result.get("memory_context", ""))

        trace = AgentTrace(
            query=query,
            rag_context=(
                result.get("rag_context", "")
                if isinstance(result, dict)
                else result
            ),
            memory_context=(
                result.get("memory_context", "")
                if isinstance(result, dict)
                else ""
            ),
        )

        v = self._verify(trace, plan)
        return {
            "passed": v.passed,
            "score": v.score,
            "reason": v.reason,
        }
