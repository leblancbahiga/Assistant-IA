"""
NURU Kernel — State.

Index léger de l'état global du système.
Le kernel "sait" — il ne décide pas, ne possède pas, ne duplique pas.

Contrairement aux singletons SessionMemory / MemoryStore / RAMBudgetManager
qui détiennent l'état réel, KernelState ne fait que les référencer et exposer
un point d'accès unique pour savoir "ce qui est chargé, ce qui est libre,
quel modèle tourne, quel worker travaille, quelle conversation est active".

Usage:
    state = KernelState()
    state.activate_model("phi-4-mini")
    state.conversation_id = "session_abc123"
    snapshot = state.snapshot()  # dict pour debug/monitoring UI
"""

import logging
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Services optionnels — résolus lazy via kernel, pas d'import direct
# pour éviter les dépendances circulaires.
_RAM_BUDGET_ATTR = "ram_budget"  # clé sous laquelle RAMBudgetManager sera enregistré


class KernelState:
    """État global du système NURU.

    Thread-safe (RLock). Accessible via ``kernel.state``.
    Propriétés principales :
        - active_model / activate_model()  — LLM actif (local ou cloud)
        - active_worker / activate_worker()  — worker en cours
        - conversation_id  — ID de la conversation courante
        - current_intent  — dernier intent classifié par le router
        - ram_pressure()  — délègue à RAMBudgetManager si enregistré
        - snapshot()  — dict complet pour monitoring/debug
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # Registre clé-valeur pour état arbitraire
        self._data: dict[str, Any] = {
            "active_model": None,
            "active_worker": None,
            "conversation_id": None,
            "current_intent": None,
            "current_query": None,
            "started_at": None,
            "query_count": 0,
        }
        logger.info("🧠 KernelState initialisé")

    # ── Propriétés directes ─────────────────────────────────────

    @property
    def active_model(self) -> Optional[str]:
        """Nom du LLM actuellement chargé (ex: 'phi-4-mini', 'groq/llama-3.1')."""
        return self._data.get("active_model")

    @active_model.setter
    def active_model(self, value: Optional[str]) -> None:
        with self._lock:
            self._data["active_model"] = value

    def activate_model(self, model_name: str) -> None:
        """Change le modèle actif et log."""
        with self._lock:
            old = self._data.get("active_model")
            self._data["active_model"] = model_name
            self._data["current_intent"] = None  # reset intent au changement de modèle
        logger.info("🔄 Modèle actif: %s → %s", old, model_name)

    @property
    def active_worker(self) -> Optional[str]:
        """Nom du worker/tâche en cours d'exécution."""
        return self._data.get("active_worker")

    @active_worker.setter
    def active_worker(self, value: Optional[str]) -> None:
        with self._lock:
            self._data["active_worker"] = value

    def activate_worker(self, worker_name: str) -> None:
        """Définit le worker actif."""
        with self._lock:
            self._data["active_worker"] = worker_name
        logger.debug("⚙️ Worker actif: %s", worker_name)

    def deactivate_worker(self) -> None:
        """Libère le worker actif."""
        with self._lock:
            self._data["active_worker"] = None

    @property
    def conversation_id(self) -> Optional[str]:
        return self._data.get("conversation_id")

    @conversation_id.setter
    def conversation_id(self, value: Optional[str]) -> None:
        with self._lock:
            self._data["conversation_id"] = value

    @property
    def current_intent(self) -> Optional[str]:
        """Dernier intent classifié (GENERAL, RAG, WEB, TOOL, HYBRID)."""
        return self._data.get("current_intent")

    @current_intent.setter
    def current_intent(self, value: Optional[str]) -> None:
        with self._lock:
            self._data["current_intent"] = value

    # ── Accès générique ─────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    # ─── Accès RAM (délégation, pas de dépendance) ─────────────

    def ram_pressure(self) -> Optional[str]:
        """Retourne le niveau de pression RAM, ou None si pas de budget.

        Délègue à RAMBudgetManager *si* celui-ci est enregistré dans
        le kernel. Aucune importation directe — ne casse pas si absent.
        """
        try:
            budget = self._resolve_budget()
            if budget is not None:
                return budget.get_pressure()
        except Exception:
            logger.debug("⚠️ ram_pressure: budget non disponible", exc_info=True)
        return None

    def ram_summary(self) -> Optional[str]:
        """Rapport textuel RAM, ou None si pas de budget."""
        try:
            budget = self._resolve_budget()
            if budget is not None:
                return budget.summary()
        except Exception:
            pass
        return None

    @staticmethod
    def _resolve_budget():
        """Résout RAMBudgetManager via NuruKernel (lazy, sans import direct).

        Évite le couplage à l'import : importe NuruKernel localement
        et ne fait rien si le service n'est pas enregistré.
        """
        try:
            from src.kernel import NuruKernel
            kernel = NuruKernel()
            return kernel.get(_RAM_BUDGET_ATTR) if kernel.has(_RAM_BUDGET_ATTR) else None
        except Exception:
            return None

    # ── Cycle de vie ────────────────────────────────────────────

    def start(self) -> None:
        """Appelé par le kernel boot()."""
        with self._lock:
            import time
            self._data["started_at"] = time.time()
        logger.info("▶️ KernelState démarré")

    def stop(self) -> None:
        """Appelé par le kernel shutdown()."""
        with self._lock:
            self._data.clear()
            self._data["started_at"] = None
        logger.info("⏹️ KernelState arrêté")

    # ── Snapshot ────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        """État complet pour monitoring / debug UI.

        Inclut :
        - état du registre interne
        - pression RAM (si disponnible)
        - durée de fonctionnement
        """
        with self._lock:
            result = dict(self._data)
        # Ajouter RAM en lecture seule (ne pas bloquer le lock)
        try:
            budget = self._resolve_budget()
            if budget is not None:
                state = budget.probe()
                result["ram_free_gb"] = round(state.free_ram_gb, 2)
                result["ram_swap_pct"] = round(state.swap_percent, 1)
                result["ram_pressure"] = state.pressure_level
                result["ram_rss_mb"] = round(state.process_rss_mb, 0)
        except Exception:
            result["ram_pressure"] = "unknown"
        return result

    def __repr__(self) -> str:
        model = self._data.get("active_model", "none")
        worker = self._data.get("active_worker", "idle")
        return f"<KernelState model={model} worker={worker}>"
