"""Store d'état immutable pour l'UI NURU V4.5."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AppState:
    """État immutable de l'interface NURU.

    Mis à jour via les événements de l'orchestrateur.
    L'UI lit cet état ; seules les actions le modifient.
    """
    # Modèle
    current_model: str = "local"
    active_route: str = "idle"      # idle | routing | rag | generating | streaming
    rag_confidence: float = 0.0
    chunks_used: int = 0
    sources: list[str] = field(default_factory=list)

    # Télémétrie
    ram_free_mb: int = 0
    tokens_per_sec: float = 0.0
    response_time_ms: float = 0.0
    ram_status: str = "ok"          # ok | warning | critical

    # État
    is_busy: bool = False
    last_error: Optional[str] = None
    pipeline_stage: str = "idle"    # idle | retrieving | reranking | generating

    # Streaming
    streaming_text: str = ""
    streaming_active: bool = False
