"""
NURU V9 — AgentOrchestrator : boucle agentique principale.

Architecture :
1. plan(goal) → TaskPlan via TaskPlanner
2. Pour chaque étape du plan :
   a. execute(step) → StepResult via TaskExecutor
   b. verify(step, result) → (ok, score, reason) via TaskVerifier
   c. Si échec : recovery.decide(error_type, attempt) → RecoveryDecision
   d. Si recovery=RETRY : ré-exécuter (max max_retries_per_step fois)
   e. Si recovery=ESCALATE : arrêter, retourner erreur
3. Synthétiser les résultats → réponse finale
4. Sauvegarder l'état via ResumeManager
5. Enregistrer dans EpisodicMemory (via MemoryManager, si fourni)

Single active model instance — pas d'agent multi-LLM.
Toutes les étapes sont séquentielles pour respecter le budget RAM.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Optional

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
    ToolCall,
)

logger = logging.getLogger(__name__)


# ── Helpers pour la détection du type d'erreur ────────────────────────


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
# AgentOrchestrator
# ═══════════════════════════════════════════════════════════════════════


class AgentOrchestrator:
    """
    Boucle agentique principale : reçoit un objectif utilisateur,
    planifie, exécute, vérifie, et gère les erreurs.

    Utilise les limites de sécurité définies dans AGENT_LIMITS :
      - max_steps : nombre maximum d'étapes
      - max_retries_per_step : nombre maximum de tentatives par étape
      - max_wall_time_seconds : temps total d'exécution maximum
      - max_tool_calls_per_step : outils maximum par étape (appliqué par l'executor)
    """

    def __init__(
        self,
        planner: Optional[Callable] = None,
        executor: Optional[Callable] = None,
        verifier: Optional[Callable] = None,
        recovery: Optional[Callable] = None,
        resume: Optional[Callable] = None,
        memory_manager: Optional[object] = None,
    ):
        """
        Initialise l'orchestrateur avec les sous-modules nécessaires.

        Args:
            planner:       Instance de TaskPlanner (ou créée automatiquement)
            executor:      Instance de TaskExecutor (ou créée automatiquement)
            verifier:      Instance de TaskVerifier (ou créée automatiquement)
            recovery:      Instance de ErrorRecovery (ou créée automatiquement)
            resume:        Instance de ResumeManager (ou créée automatiquement)
            memory_manager: Optionnel, pour enregistrer dans EpisodicMemory
        """
        from src.agent.planner import TaskPlanner as _P
        from src.agent.executor import TaskExecutor as _E
        from src.agent.verifier import TaskVerifier as _V
        from src.agent.recovery import ErrorRecovery as _R
        from src.agent.resume import ResumeManager as _Res

        self.planner = planner if planner is not None else _P()
        self.executor = executor if executor is not None else _E()
        self.verifier = verifier if verifier is not None else _V()
        self.recovery = recovery if recovery is not None else _R()
        self.resume = resume if resume is not None else _Res()
        self.memory_manager = memory_manager

        # Limites de sécurité
        self.limits = dict(AGENT_LIMITS)

        # Stockage des sessions actives
        self._sessions: dict[str, AgentState] = {}

    # ── Interface publique ─────────────────────────────────────────────

    async def run(self, goal: str, session_id: str = "default") -> dict[str, Any]:
        """
        Boucle agentique complète.

        1. Planification
        2. Exécution séquentielle des étapes avec vérification
        3. Gestion des erreurs (retry, alternatives, escalation)
        4. Synthèse finale
        5. Sauvegarde état + mémoire

        Args:
            goal:       Objectif utilisateur
            session_id: Identifiant de session

        Returns:
            dict avec les clés :
              - goal          : objectif original
              - status        : 'success' | 'partial' | 'error' | 'interrupted'
              - steps         : liste des résultats d'étapes
              - duration_s    : durée totale en secondes
              - final_response: réponse finale synthétisée
              - session_id    : identifiant de session
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
        max_steps_limit = self.limits.get("max_steps", 3)  # V15 Phase 0B : 3 itérations max (P0 #20)
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
            # ── 1. Vérification d'erreurs similaires (si MemoryManager) ──
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
                        logger.info("⚠️ %s erreur(s) similaire(s) déjà en mémoire", len(similar_errors))
                except Exception as e:
                    logger.debug("Erreur check_errors: %s", e)

                try:
                    profile = self.memory_manager.get_user_profile()
                    if profile:
                        memory_ctx += "\n" + profile if memory_ctx else profile
                except Exception as e:
                    logger.debug("Erreur get_user_profile: %s", e)

            # ── 2. Planification ──────────────────────────────────
            logger.info(f"📋 Planification pour : {goal[:80]}…")
            plan: TaskPlan = self.planner.plan(goal)
            state.plan = plan
            state.status = "executing"

            # ── Contrôle max_steps : tronquer si trop d'étapes ────
            if len(plan.steps) > max_steps_limit:
                logger.warning(
                    f"⚠️ Plan tronqué : {len(plan.steps)} étapes → {max_steps_limit}"
                )
                plan.steps = plan.steps[:max_steps_limit]

            # ── 2. Exécution séquentielle ─────────────────────────
            for step_idx, step in enumerate(plan.steps):
                elapsed = time.monotonic() - start_time
                if elapsed >= max_wall:
                    logger.warning(
                        f"⏰ Temps imparti dépassé ({elapsed:.1f}s ≥ {max_wall}s)"
                    )
                    final_status = "interrupted"
                    break

                state.current_step_index = step_idx
                state.status = "executing"

                # Timeout dynamique basé sur le temps restant
                remaining_wall = max(0.1, max_wall - elapsed)
                try:
                    step_result = await asyncio.wait_for(
                        self.run_step(step, state),
                        timeout=remaining_wall,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        f"⏰ Wall timeout dépassé pendant l'étape {step_idx + 1}"
                    )
                    step_result = StepResult(
                        step_id=step.step_id,
                        status=TaskStatus.FAILED,
                        output=None,
                        error=f"Wall timeout dépassé après {elapsed:.1f}s",
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
                    # Vérifier si c'est une escalade définitive
                    if "ESCALATE" in (step_result.error or ""):
                        final_status = "error"
                        break
                    # Retry épuisé → error
                    final_status = "error"
                    break

            # ── 3. Synthèse ───────────────────────────────────────
            state.status = "done"
            final_response = self.synthesize(state)

            # ── 4. Sauvegarde état ────────────────────────────────
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
                logger.warning(f"⚠️ Échec sauvegarde ResumeManager : {e}")

            # ── 5. Mémoire épisodique (optionnel) ────────────────
            if self.memory_manager is not None:
                try:
                    # Enregistrer la session complète
                    self.memory_manager.add_episode(
                        session_id=session_id,
                        goal=goal,
                        status=final_status,
                        steps=step_results_list,
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Échec enregistrement mémoire : {e}")

                try:
                    # Enregistrer chaque étape en échec dans ErrorMemory
                    for step_result in step_results_list:
                        if step_result.get("status") == "failed" and step_result.get("error"):
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
            logger.exception(f"💥 Erreur orchestrateur : {exc}")
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
        """
        Exécute une étape avec retry et recovery.

        Boucle interne :
        - Exécute via executor.execute(step)
        - Vérifie via verifier.verify(step, result)
        - Si échec et retry possible : recovery.decide → RETRY → ré-exécute
        - Si échec et plus de retry : recovery.decide → ESCALATE → arrête

        Args:
            step:  L'étape à exécuter
            state: État agent optionnel (pour suivi de statut)

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
                # Exécution avec timeout
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
                # Dernière tentative épuisée → ESCALATE
                decision = RecoveryDecision(
                    action=RecoveryAction.ESCALATE,
                    params={
                        "error_type": error_type.value,
                        "attempt": attempt,
                        "max_retries": max_retries,
                    },
                    message=(
                        f"Échec après {attempt + 1} tentative(s). "
                        f"Escalade nécessaire."
                    ),
                )

            last_error = (
                f"Tentative {attempt + 1}/{max_retries + 1} échouée : "
                f"{result.error or reason} → {decision.action.value}"
            )

            # Si escalation → arrêter immédiatement
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

            # Backoff optionnel
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
        """
        Agrège les résultats des étapes en une réponse finale.

        Concatène les outputs de chaque étape réussie, ou retourne
        un message d'erreur en cas d'échec.

        Args:
            state: L'état final de l'agent après exécution

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

        header = (
            f"📊 Synthèse : {success_count} étape(s) réussie(s)"
        )
        if fail_count > 0:
            header += f", {fail_count} échec(s)"

        return header + "\n\n" + "\n\n".join(parts)

    def get_progress(self, session_id: str) -> dict[str, Any] | None:
        """
        Retourne l'état actuel d'une session via ResumeManager.

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
