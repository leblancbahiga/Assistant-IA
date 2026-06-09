"""
NURU V8+ — Types partagés du pipeline RAG.

Centralise les dataclasses utilisées par plusieurs modules
pour éviter les imports circulaires (ex: multi_search ↔ hyde).
"""

from dataclasses import dataclass, field
from typing import Optional

# ──────────────────────────────────────────
# SearchResult
# ──────────────────────────────────────────

@dataclass
class SearchResult:
    """Résultat d'une stratégie de recherche."""
    content: str
    source: str
    score: float       # Score normalisé [0, 1]
    strategy: str      # 'vectoriel', 'fts', 'grep', 'hyde', 'metadata'
    rank: int = 0      # Rang dans sa stratégie (pour RRF)
