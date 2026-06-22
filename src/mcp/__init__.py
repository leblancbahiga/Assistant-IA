"""NURU MCP — Model Context Protocol (Phase 4).

Client et serveur MCP pour connecter NURU à l'écosystème d'outils externes.
Permet à d'autres applications d'appeler les capacités de NURU et vice-versa.
"""

from .client import MCPClient, MCPConnection
from .server import MCPServer, MCPTool

__all__ = [
    "MCPClient", "MCPConnection",
    "MCPServer", "MCPTool",
]
