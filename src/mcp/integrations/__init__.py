"""MCP Integrations — Connecteurs prêts à l'emploi NURU.

Intégrations clés : Gmail, Calendar, Apple Notes, Rappels macOS.
Chaque intégration expose un ensemble d'outils MCP compatibles.
"""

from .gmail import GmailIntegration
from .calendar import CalendarIntegration

__all__ = [
    "GmailIntegration",
    "CalendarIntegration",
]
