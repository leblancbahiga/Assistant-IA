"""
NURU V9 — Module Mémoire unifiée.

Point d'entrée du sous-paquet memory.
Les imports sont paresseux pour permettre une construction incrémentale.
"""

import logging

logger = logging.getLogger(__name__)

__all__ = [
    "MemorySchema",
    "get_db_path",
    "EpisodicMemory",
    "SemanticMemory",
    "UserMemory",
    "ErrorMemory",
    "MemoryRetriever",
    "MemoryManager",
    "ConsolidationWorker",
]


def MemorySchema(*args, **kwargs):
    from src.memory.schema import MemorySchema as _cls
    return _cls(*args, **kwargs)


def get_db_path(*args, **kwargs):
    from src.memory.schema import get_db_path as _fn
    return _fn(*args, **kwargs)


def EpisodicMemory(*args, **kwargs):
    from src.memory.episodic import EpisodicMemory as _cls
    return _cls(*args, **kwargs)


def SemanticMemory(*args, **kwargs):
    from src.memory.semantic import SemanticMemory as _cls
    return _cls(*args, **kwargs)


def UserMemory(*args, **kwargs):
    from src.memory.user import UserMemory as _cls
    return _cls(*args, **kwargs)


def ErrorMemory(*args, **kwargs):
    from src.memory.errors import ErrorMemory as _cls
    return _cls(*args, **kwargs)


def MemoryRetriever(*args, **kwargs):
    from src.memory.retriever import MemoryRetriever as _cls
    return _cls(*args, **kwargs)


def MemoryManager(*args, **kwargs):
    from src.memory.manager import MemoryManager as _cls
    return _cls(*args, **kwargs)


def ConsolidationWorker(*args, **kwargs):
    from src.memory.consolidation import ConsolidationWorker as _cls
    return _cls(*args, **kwargs)
