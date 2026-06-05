"""Points d'entrée des actions UI vers l'orchestrateur."""
from dataclasses import dataclass, field
from typing import Optional, Callable


@dataclass
class UIActions:
    """Collection de callbacks que l'UI peut invoquer.

    Remplis par le wiring au démarrage (main.py ou dashboard).
    """
    send_query: Optional[Callable] = None
    cancel_generation: Optional[Callable] = None
    toggle_debug: Optional[Callable] = None
    toggle_tts: Optional[Callable] = None
    reindex_documents: Optional[Callable] = None
