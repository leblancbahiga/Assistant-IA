"""NURU Routing Package — Routeur unifié + DynamicPromptBuilder."""
from .router import Router, RouterResult
from .prompt_builder import DynamicPromptBuilder

__all__ = ["Router", "RouterResult", "DynamicPromptBuilder"]
