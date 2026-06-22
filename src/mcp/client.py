"""MCP Client — Connexion à des serveurs MCP externes.

Permet à NURU de consommer des outils exposés par des serveurs MCP
(météo, calendrier, email, etc.).
"""

from __future__ import annotations

import enum
import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MCPTransport(enum.Enum):
    """Type de transport MCP."""
    STDIO = "stdio"
    HTTP = "http"
    WEBSOCKET = "websocket"


@dataclass
class MCPConnection:
    """Configuration de connexion à un serveur MCP."""
    name: str
    transport: MCPTransport = MCPTransport.STDIO
    command: str = ""
    args: list[str] = field(default_factory=list)
    url: str = ""
    api_key: str = ""
    enabled: bool = True


@dataclass
class MCPToolDef:
    """Définition d'un outil MCP distant."""
    name: str
    description: str
    parameters: dict = field(default_factory=dict)
    server: str = ""


@dataclass
class MCPClient:
    """Client MCP pour se connecter à des serveurs externes.

    Usage :
        client = MCPClient()
        client.add_connection(MCPConnection(
            name="weather", command="python", args=["-m", "weather_mcp_server"]
        ))
        result = await client.call_tool("weather", "get_forecast", {"city": "Paris"})
    """

    connections: dict[str, MCPConnection] = field(default_factory=dict)
    _processes: dict[str, Any] = field(default_factory=dict)

    def add_connection(self, conn: MCPConnection) -> None:
        """Ajoute une connexion MCP."""
        self.connections[conn.name] = conn
        logger.info(f"MCP connexion ajoutée: {conn.name} ({conn.transport.value})")

    def remove_connection(self, name: str) -> None:
        self.connections.pop(name, None)
        self._disconnect(name)

    async def connect(self, name: str) -> bool:
        """Établit la connexion à un serveur MCP."""
        conn = self.connections.get(name)
        if not conn:
            logger.error(f"Connexion inconnue: {name}")
            return False

        if name in self._processes:
            return True  # Déjà connecté

        try:
            if conn.transport == MCPTransport.STDIO and conn.command:
                proc = await asyncio.create_subprocess_exec(
                    conn.command, *conn.args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self._processes[name] = proc
                logger.info(f"MCP connecté: {name}")
                return True

            elif conn.transport == MCPTransport.HTTP and conn.url:
                # HTTP client — pas de processus persistant
                import httpx
                self._processes[name] = {"url": conn.url, "api_key": conn.api_key}
                logger.info(f"MCP HTTP connecté: {name}")
                return True

            return False

        except Exception as e:
            logger.error(f"Erreur connexion MCP '{name}': {e}")
            return False

    async def call_tool(self, server: str, tool: str, arguments: dict) -> dict:
        """Appelle un outil sur un serveur MCP.

        Args:
            server: Nom du serveur
            tool: Nom de l'outil
            arguments: Paramètres de l'outil

        Returns:
            Résultat de l'appel
        """
        conn = self.connections.get(server)
        if not conn:
            return {"error": f"Serveur inconnu: {server}"}

        if server not in self._processes:
            ok = await self.connect(server)
            if not ok:
                return {"error": f"Impossible de se connecter à {server}"}

        request = json.dumps({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
            "id": 1,
        })

        try:
            if conn.transport == MCPTransport.STDIO:
                proc = self._processes.get(server)
                if proc and proc.stdin:
                    proc.stdin.write((request + "\n").encode())
                    await proc.stdin.drain()
                    response = await asyncio.wait_for(proc.stdout.readline(), timeout=30)
                    return json.loads(response.decode())

            elif conn.transport == MCPTransport.HTTP:
                import httpx
                headers = {"Content-Type": "application/json"}
                if conn.api_key:
                    headers["Authorization"] = f"Bearer {conn.api_key}"
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        f"{conn.url}/tools/{tool}",
                        json=arguments,
                        headers=headers,
                    )
                    return resp.json()

            return {"error": "Transport non supporté"}

        except Exception as e:
            logger.error(f"Erreur appel MCP {server}/{tool}: {e}")
            return {"error": str(e)}

    async def list_tools(self, server: str) -> list[MCPToolDef]:
        """Liste les outils disponibles sur un serveur MCP."""
        result = await self.call_tool(server, "list_tools", {})
        if "error" in result:
            return []
        tools = result.get("tools", result.get("result", {}).get("tools", []))
        return [
            MCPToolDef(
                name=t.get("name", ""),
                description=t.get("description", ""),
                parameters=t.get("parameters", {}),
                server=server,
            ) for t in tools
        ]

    def _disconnect(self, name: str) -> None:
        """Déconnecte un serveur."""
        proc = self._processes.pop(name, None)
        if proc and hasattr(proc, "terminate"):
            try:
                proc.terminate()
            except Exception:
                pass

    def disconnect_all(self) -> None:
        """Déconnecte tous les serveurs."""
        for name in list(self._processes.keys()):
            self._disconnect(name)

    def get_connected_servers(self) -> list[str]:
        return list(self._processes.keys())


import asyncio
