"""
NURU V12 — AgentOrchestrator : boucle Plan→Execute→Verify→Synthesize.

Intègre RAGEngine (recherche documentaire) + MemoryManager (contexte utilisateur)
dans une boucle agentique légère destinée au ToolRegistry.

Architecture :
  1. PLAN   — Décompose la requête, consulte RAG + mémoire
  2. EXECUTE — Construit la réponse à partir des contextes collectés
  3. VERIFY — Évalue la qualité et la confiance du résultat
  4. SYNTHESIZE — Produit une réponse structurée avec traçabilité

Chaque étape est traçable via le dict AgentTrace retourné par run().
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Data classes de traçabilité ────────────────────────────────────────


@dataclass
class AgentTrace:
    """Trace complète d'une exécution agentique.

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
    """Résultat de la phase de planification."""
    decomposed: bool = False
    steps: list[str] = field(default_factory=list)
    rag_available: bool = False
    rag_documents_found: int = 0
    rag_confidence: str = "NONE"
    memory_available: bool = False
    memory_recalled: int = 0


@dataclass
class VerifyResult:
    """Résultat de la phase de vérification."""
    passed: bool = False
    score: float = 0.0
    reason: str = ""
    has_content: bool = False
    has_sources: bool = False
    has_memory_context: bool = False


# ── AgentOrchestrator ─────────────────────────────────────────────────


class AgentOrchestrator:
    """Boucle agentique Plan→Execute→Verify→Synthesize.

    Intègre RAGEngine pour la recherche documentaire et MemoryManager
    pour le contexte utilisateur dans une boucle traçable.

    Utilisation :
        orch = AgentOrchestrator()
        result = await orch.run("Quelles sont les compétences de l'utilisateur ?")
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
        """Initialise l'orchestrateur avec RAG et mémoire.

        Args:
            rag_engine: Instance de RAGEngine (créée paresseusement si None)
            memory_manager: Instance de MemoryManager (créée paresseusement si None)
        """
        if self._initialized:
            return

        self._rag_engine = rag_engine
        self._memory_manager = memory_manager
        self._rag_initialized = False
        self._memory_initialized = False
        self._initialized = True
        logger.debug("AgentOrchestrator initialisé")

    @classmethod
    def get_instance(cls) -> AgentOrchestrator:
        """Retourne l'instance unique."""
        return cls()

    @classmethod
    def _reset_singleton(cls) -> None:
        """Réinitialise le singleton (usage tests uniquement)."""
        with cls._singleton_lock:
            cls._instance = None

    # ── Propriétés paresseuses ────────────────────────────────────────

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

    # ── Boucle principale ─────────────────────────────────────────────

    async def run(self, query: str) -> dict[str, Any]:
        """Boucle agentique complète : Plan→Execute→Verify→Synthesize.

        Args:
            query: Requête utilisateur

        Returns:
            Dictionnaire structuré avec les clés :
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

    # ── Phase 1 : PLAN ────────────────────────────────────────────────

    async def _plan(self, query: str) -> PlanResult:
        """Phase de planification : décompose la requête et collecte les contextes.

        1. Décompose la requête en sous-étapes logiques
        2. Consulte RAG pour la recherche documentaire
        3. Consulte MemoryManager pour le contexte utilisateur
        """
        plan = PlanResult()

        # 1. Décomposition simple par mots-clés
        plan.steps = self._decompose_query(query)
        plan.decomposed = len(plan.steps) > 0

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

        Args:
            query: Requête utilisateur brute

        Returns:
            Liste de sous-requêtes
        """
        if not query:
            return []

        # Détection de connecteurs de coordination
        connectors = [
            " et ", " ou ", " puis ", " ainsi que ",
            " de plus ", " également ", " aussi ",
        ]
        for conn in connectors:
            if conn in query.lower():
                parts = [q.strip() for q in query.split(conn) if q.strip()]
                if len(parts) > 1:
                    # Préserver l'intention interrogative de chaque partie
                    result = []
                    for p in parts:
                        if not any(w in p.lower() for w in ["quoi", "qui", "où", "quand", "comment", "pourquoi", "quel", "quelle"]):
                            # Si la sous-partie n'a pas de mot interrogatif,
                            # on l'attache à la première qui en a un
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

        # Requête simple
        return [query]

    # ── Phase 2 : EXECUTE ─────────────────────────────────────────────

    async def _execute(
        self,
        query: str,
        plan: PlanResult,
    ) -> dict[str, Any]:
        """Phase d'exécution : collecte les contextes RAG et mémoire.

        Utilise les résultats du plan pour rassembler les informations
        nécessaires à la synthèse.

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
                    result["sources_count"] = rag_result.documents_found if hasattr(rag_result, "documents_found") else 0
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

    # ── Phase 3 : VERIFY ──────────────────────────────────────────────

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
            trace: Trace d'exécution contenant les contextes collectés
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

    # ── Phase 4 : SYNTHESIZE ──────────────────────────────────────────

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

        Args:
            query: Requête originale
            trace: Trace d'exécution complète
            plan: Résultat de la phase de planification
            verify: Résultat de la phase de vérification

        Returns:
            Réponse synthétisée sous forme de texte structuré
        """
        parts = []

        # En-tête de confiance
        if verify.passed:
            confidence_tag = "✅ Confiance: HAUTE" if verify.score >= 0.7 else "✅ Confiance: MOYENNE"
        else:
            confidence_tag = "⚠️ Confiance: FAIBLE"

        parts.append(f"[RÉSULTAT — {confidence_tag}]")
        parts.append("")

        # Contenu RAG
        if trace.rag_context:
            parts.append("📚 Contexte documentaire :")
            parts.append(trace.rag_context)

        # Contexte mémoire
        if trace.memory_context:
            parts.append("🧠 Contexte mémoire :")
            parts.append(trace.memory_context)

        # Synthèse de la réponse basée sur les éléments collectés
        synthesis = self._build_answer(query, trace, plan)

        if synthesis:
            parts.append("")
            parts.append("📝 Synthèse :")
            parts.append(synthesis)

        # Pied de page avec traçabilité
        parts.append("")
        parts.append("---")
        parts.append(f"Sources: {plan.rag_documents_found} document(s) | "
                      f"Mémoire: {'✅' if plan.memory_available else '❌'} | "
                      f"Score: {round(verify.score, 2)}")

        return "\n".join(parts)

    def _build_answer(
        self,
        query: str,
        trace: AgentTrace,
        plan: PlanResult,
    ) -> str:
        """Construit la réponse textuelle à partir des contextes collectés.

        Args:
            query: Requête originale
            trace: Trace d'exécution
            plan: Résultat du plan

        Returns:
            Réponse textuelle ou chaîne vide si absence de contexte
        """
        if not plan.rag_available and not plan.memory_available:
            return "Je n'ai pas trouvé d'information pertinente dans ma base de connaissance ni dans mes souvenirs pour répondre à cette question."

        lines = []
        if trace.memory_context:
            lines.append("D'après les informations que j'ai sur vous :")
            # Extraire les lignes pertinentes du contexte mémoire
            mem_lines = [l.strip() for l in trace.memory_context.split("\n") if l.strip()]
            lines.extend(mem_lines[:5])

        if trace.rag_context:
            if lines:
                lines.append("")
                lines.append("D'après les documents indexés :")
            # Extraire les informations clés du contexte RAG
            rag_preview = trace.rag_context[:500]
            lines.append(rag_preview)

        if not lines:
            return "Informations collectées mais impossibles à synthétiser."

        return "\n".join(lines)

    # ── Construction de la réponse ─────────────────────────────────────

    def _build_response(self, trace: AgentTrace) -> dict[str, Any]:
        """Construit la réponse structurée finale.

        Args:
            trace: Trace d'exécution complète

        Returns:
            Dictionnaire de réponse structurée
        """
        return {
            "query": trace.query,
            "status": trace.status,
            "synthesis": trace.synthesis,
            "trace": trace.to_dict(),
            "trace_summary": self._format_trace_summary(trace),
        }

    def _format_trace_summary(self, trace: AgentTrace) -> str:
        """Formate un résumé lisible de la trace d'exécution.

        Args:
            trace: Trace d'exécution

        Returns:
            Résumé textuel de l'exécution
        """
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

    # ── Méthodes auxiliaires ──────────────────────────────────────────

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
            result: Résultat à vérifier (dict ou str)

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
            rag_context=result.get("rag_context", "") if isinstance(result, dict) else result,
            memory_context=result.get("memory_context", "") if isinstance(result, dict) else "",
        )

        v = self._verify(trace, plan)
        return {
            "passed": v.passed,
            "score": v.score,
            "reason": v.reason,
        }
