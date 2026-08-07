"""NURU Kernel — Façade centrale.

Point d'entrée unique de NURU. Tout passe par lui.
Singleton — une seule instance par processus.

Contrairement à l'ancienne architecture où chaque module importait
directement les autres, ici :
  1. Les modules sont enregistrés dans le ServiceRegistry
  2. Les modules accèdent aux autres via kernel.get('nom')
  3. Le Kernel gère le cycle de vie (boot → services → shutdown)

Le Kernel ne répond jamais — il n'est pas un LLM, il orchestre.
"""

import logging
from typing import Any

from src.kernel.registry import ServiceRegistry

logger = logging.getLogger(__name__)


class NuruKernel:
    """Noyau central de NURU.

    Singleton. Tous les composants sont accessibles via ses propriétés
    ou via kernel.get('nom_du_service').

    Usage ::

        kernel = NuruKernel()
        kernel.register('llm', mon_llm)
        llm = kernel.get('llm')          # ou kernel.local_llm
        rag = kernel.get('rag_engine')    # ou kernel.rag_engine
    """

    _instance: "NuruKernel | None" = None
    _initialized: bool = False

    def __new__(cls) -> "NuruKernel":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._services = ServiceRegistry()
        logger.info("🧱 NuruKernel initialisé")

    # ── Propriétés — ServiceRegistry ──────────────────────────

    @property
    def services(self) -> ServiceRegistry:
        """Accès au registre des services (bas niveau)."""
        return self._services

    # ── Accesseurs typés ──────────────────────────────────────
    # Chaque propriété donne accès à un service du registre.
    # Retourne None si le service n'est pas encore enregistré.

    @property
    def router(self) -> Any:
        """Routeur sémantique (classification de requêtes)."""
        return self._services.get_or_none("router")

    @property
    def rag_engine(self) -> Any:
        """Moteur RAG (retrieve + rerank)."""
        return self._services.get_or_none("rag_engine")

    @property
    def local_llm(self) -> Any:
        """LLM local (MLX, Phi-4-mini)."""
        return self._services.get_or_none("local_llm")

    @property
    def cloud_llm(self) -> Any:
        """LLM cloud (Groq / OpenRouter)."""
        return self._services.get_or_none("cloud_llm")

    @property
    def memory(self) -> Any:
        """Store mémoire (V5 + V9)."""
        return self._services.get_or_none("memory")

    @property
    def orchestrator(self) -> Any:
        """Orchestrateur principal du pipeline."""
        return self._services.get_or_none("orchestrator")

    @property
    def embedder(self) -> Any:
        """Embedder MLX (Qwen3-0.6B)."""
        return self._services.get_or_none("embedder")

    @property
    def event_bus(self) -> Any:
        """Bus d'événements interne."""
        return self._services.get_or_none("event_bus")

    @property
    def state(self) -> Any:
        """État global du système (KernelState)."""
        return self._services.get_or_none("state")

    @property
    def metrics(self) -> Any:
        """Métriques système (RAM, CPU, threads, QObjects)."""
        return self._services.get_or_none("metrics")

    @property
    def resources(self) -> Any:
        """Gestionnaire de ressources (RAMBudgetManager wrapper)."""
        return self._services.get_or_none("resources")

    @property
    def pipeline(self) -> Any:
        """Pipeline Engine (steps composables)."""
        return self._services.get_or_none("pipeline")

    @property
    def kernel_router(self) -> Any:
        """Routeur 5-bucket minimal."""
        return self._services.get_or_none("kernel_router")

    @property
    def scheduler(self) -> Any:
        """Ordonnanceur de tâches."""
        return self._services.get_or_none("scheduler")

    @property
    def cache(self) -> Any:
        """Cache centralisé."""
        return self._services.get_or_none("cache")

    @property
    def audio(self) -> Any:
        """Moteur audio (capture + TTS)."""
        return self._services.get_or_none("audio")

    @property
    def web_search(self) -> Any:
        """Recherche web."""
        return self._services.get_or_none("web_search")

    @property
    def ingestion(self) -> Any:
        """Moteur d'indexation de documents."""
        return self._services.get_or_none("ingestion")

    @property
    def memory_bridge(self) -> Any:
        """Pont mémoire V5 → V9."""
        return self._services.get_or_none("memory_bridge")

    @property
    def long_term_memory(self) -> Any:
        """Mémoire long terme."""
        return self._services.get_or_none("long_term_memory")

    @property
    def knowledge_graph(self) -> Any:
        """Graphe de connaissances."""
        return self._services.get_or_none("knowledge_graph")

    @property
    def sleep_cycle(self) -> Any:
        """Cycle de sommeil (consolidation mémoire)."""
        return self._services.get_or_none("sleep_cycle")

    @property
    def proactive(self) -> Any:
        """Moteur proactif (suggestions, routines)."""
        return self._services.get_or_none("proactive")

    @property
    def persona(self) -> Any:
        """Moteur de personnalité."""
        return self._services.get_or_none("persona")

    @property
    def model_router(self) -> Any:
        """Routeur de modèles (ModelRouter V17)."""
        return self._services.get_or_none("model_router")

    @property
    def runtime(self) -> Any:
        """Gestionnaire d'exécution de code."""
        return self._services.get_or_none("runtime")

    # ── Méthodes génériques ───────────────────────────────────

    def register(self, name: str, service: Any, *, replace: bool = False) -> None:
        """Enregistre un service dans le registre."""
        self._services.register(name, service, replace=replace)

    def register_factory(
        self, name: str, factory: Any, *, replace: bool = False
    ) -> None:
        """Enregistre une factory pour instanciation lazy."""
        self._services.register_factory(name, factory, replace=replace)

    def get(self, name: str) -> Any:
        """Récupère un service par son nom."""
        return self._services.get(name)

    def has(self, name: str) -> bool:
        """Vérifie si un service est enregistré."""
        return self._services.has(name)

    def unregister(self, name: str) -> None:
        """Supprime un service."""
        self._services.unregister(name)

    # ── Cycle de vie ──────────────────────────────────────────

    def boot(self) -> None:
        """Démarre tous les services enregistrés.

        Appelé après que tous les services ont été enregistrés.
        """
        logger.info("🚀 NURU Kernel boot — démarrage des services...")
        self._services.start_all()
        n = len(self._services)
        logger.info("✅ Kernel boot terminé — %d services enregistrés", n)

    def shutdown(self) -> None:
        """Arrête tous les services proprement."""
        logger.info("🛑 NURU Kernel shutdown...")
        self._services.stop_all()
        self._services = ServiceRegistry()  # reset
        NuruKernel._instance = None
        NuruKernel._initialized = False
        logger.info("✅ Kernel arrêté")

    # ── Debug ─────────────────────────────────────────────────

    def snapshot(self) -> dict[str, str]:
        """État actuel du Kernel (debug)."""
        return self._services.snapshot()

    def __repr__(self) -> str:
        n = len(self._services)
        return f"<NuruKernel ({n} services)>"
