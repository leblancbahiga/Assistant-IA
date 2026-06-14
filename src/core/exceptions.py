"""
NURU V10.2 — Hiérarchie d'exceptions pour tout le pipeline.

Hiérarchie :
  OrchestratorError(Exception)
  ├─ RAGError        → Récupération/assemblage RAG
  ├─ LLMError        → Génération LLM locale ou cloud
  ├─ MemoryError     → Store mémoire (SQLite, dual-write)
  ├─ RouterError     → Routage d'intent
  ├─ ConfigError     → Configuration invalide
  └─ GuardError      → Rejet par les gardes (StrictRAGGuard, PromptGuard)
"""


class OrchestratorError(Exception):
    """Erreur de base de l'orchestrateur NURU."""
    def __init__(self, message: str, component: str = "unknown", recoverable: bool = False):
        self.component = component
        self.recoverable = recoverable
        super().__init__(message)


class RAGError(OrchestratorError):
    """Erreur durant la récupération ou l'assemblage RAG."""
    def __init__(self, message: str, query: str = "", recoverable: bool = False):
        self.query = query
        super().__init__(message, component="rag", recoverable=recoverable)


class LLMError(OrchestratorError):
    """Erreur durant la génération LLM (local ou cloud)."""
    def __init__(self, message: str, provider: str = "unknown", recoverable: bool = True):
        self.provider = provider
        super().__init__(message, component=f"llm/{provider}", recoverable=recoverable)


class MemoryError(OrchestratorError):
    """Erreur du store mémoire (SQLite, traces, dual-write)."""
    def __init__(self, message: str, store: str = "unknown", recoverable: bool = False):
        self.store = store
        super().__init__(message, component=f"memory/{store}", recoverable=recoverable)


class RouterError(OrchestratorError):
    """Erreur de routage d'intent."""
    def __init__(self, message: str, query: str = "", recoverable: bool = True):
        self.query = query
        super().__init__(message, component="router", recoverable=recoverable)


class ConfigError(OrchestratorError):
    """Erreur de configuration (champ manquant, valeur invalide)."""
    def __init__(self, message: str, field: str = ""):
        self.field = field
        super().__init__(message, component="config", recoverable=False)


class GuardError(OrchestratorError):
    """Rejet par un garde de sécurité (PromptGuard, StrictRAGGuard)."""
    def __init__(self, message: str, guard: str = "unknown"):
        self.guard = guard
        super().__init__(message, component=f"guard/{guard}", recoverable=False)
