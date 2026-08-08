"""MCP Server — Expose les capacités de NURU via MCP.

Permet aux applications externes d'appeler NURU (outils, mémoire, recherche).
Serveur léger : stdio (asyncio) ou HTTP (aiohttp optionnel).
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    """Définition d'un outil exposé par le serveur MCP."""
    name: str
    description: str
    handler: Callable[..., Any]
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {},
    })


@dataclass
class MCPResource:
    """Ressource MCP exposée."""
    uri: str
    name: str
    description: str
    mime_type: str = "text/plain"


def tools_from_registry(registry, executor) -> dict[str, "MCPTool"]:
    """Projette une ToolRegistry (source de vérité unique) en outils MCP.

    V18.1 C5 (V18-10) — unification MCP ↔ ToolRegistry : le serveur MCP
    devient une **vue** du registre d'outils actif du pipeline
    (`src.tools.ToolRegistry` / `ToolOrchestrator`), et non plus un deuxième
    registre parallèle avec des outils codés en dur.

    Chaque `ToolDefinition` du registre est projetée en un `MCPTool` dont le
    `handler` dispatche vers `executor.execute(name, **params)` — l'exécution
    réelle reste la propriété du registre unique. Aucune seconde
    implémentation d'outil n'existe ici.

    L'import de `src.tools.registry` est LAZY (dans la fonction) : ce module
    reste autonome et léger au boot (gel V18-21 respecté — `src.mcp.server`
    n'importe pas `src.tools` au chargement).
    """
    from src.tools.registry import ToolRegistry, ToolExecutor

    if not isinstance(registry, ToolRegistry):
        raise TypeError(f"registry doit être un ToolRegistry, reçu {type(registry).__name__}")
    if not isinstance(executor, ToolExecutor):
        raise TypeError(f"executor doit être un ToolExecutor, reçu {type(executor).__name__}")

    def _make_handler(ex: ToolExecutor, tool_name: str):
        def _handler(**params: Any) -> dict:
            result = ex.execute(tool_name, params)
            return {
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "duration_ms": getattr(result, "duration_ms", 0.0),
            }
        return _handler

    tools: dict[str, MCPTool] = {}
    for definition in registry.list_tools():
        schema = definition.to_schema()
        tools[definition.name] = MCPTool(
            name=definition.name,
            description=definition.description,
            handler=_make_handler(executor, definition.name),
            parameters=schema["parameters"],
        )
    return tools


@dataclass
class MCPServer:
    """Serveur MCP exposant les capacités de NURU.

    Usage :
        server = MCPServer("nuru-mcp")
        server.register_tool(MCPTool("search_memory", "Recherche en mémoire", handler_fn))
        await server.start_stdio()
        # Ou (si aiohttp installé) :
        # await server.start_http(port=8765)
    """

    name: str = "nuru-mcp"
    version: str = "0.1.0"
    tools: dict[str, MCPTool] = field(default_factory=dict)
    resources: dict[str, MCPResource] = field(default_factory=dict)
    _running: bool = False

    def register_tool(self, tool: MCPTool) -> None:
        """Enregistre un outil MCP."""
        self.tools[tool.name] = tool
        logger.info(f"MCP outil enregistré: {tool.name}")

    def register_resource(self, resource: MCPResource) -> None:
        """Enregistre une ressource MCP."""
        self.resources[resource.uri] = resource

    async def start_stdio(self) -> None:
        """Démarre le serveur en mode stdio (lecture ligne par ligne)."""
        self._running = True
        logger.info(f"MCP Server '{self.name}' démarré (stdio)")

        while self._running:
            try:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )
                if not line:
                    break

                request = json.loads(line)
                response = await self._handle_request(request)
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

            except json.JSONDecodeError:
                continue
            except Exception as e:
                logger.error(f"Erreur MCP: {e}")

    async def start_http(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        """Démarre en mode HTTP (nécessite aiohttp)."""
        try:
            from aiohttp import web

            async def handle_tool(request):
                name = request.match_info["name"]
                tool = self.tools.get(name)
                if not tool:
                    return web.json_response({"error": f"Tool '{name}' not found"}, status=404)
                try:
                    body = await request.json()
                    result = tool.handler(**body)
                    return web.json_response({"result": result})
                except Exception as e:
                    return web.json_response({"error": str(e)}, status=500)

            async def list_tools(request):
                return web.json_response({
                    "tools": [
                        {"name": t.name, "description": t.description, "parameters": t.parameters}
                        for t in self.tools.values()
                    ]
                })

            async def health(request):
                return web.json_response({"status": "ok", "server": self.name})

            app = web.Application()
            app.router.add_post("/tools/{name}", handle_tool)
            app.router.add_get("/tools", list_tools)
            app.router.add_get("/health", health)

            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host, port)
            await site.start()

            self._running = True
            logger.info(f"MCP HTTP: http://{host}:{port}")

        except ImportError:
            logger.warning("aiohttp non installé — serveur HTTP indisponible")
        except Exception as e:
            logger.error(f"Erreur HTTP: {e}")

    async def _handle_request(self, request: dict) -> dict:
        """Gère une requête JSON-RPC."""
        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id", 0)

        if method == "tools/call":
            tool_name = params.get("name", "")
            args = params.get("arguments", {})
            tool = self.tools.get(tool_name)
            if not tool:
                return {"jsonrpc": "2.0", "error": {"code": -32601, "message": f"Tool '{tool_name}' not found"}, "id": req_id}
            try:
                result = tool.handler(**args)
                return {"jsonrpc": "2.0", "result": {"content": [{"type": "text", "text": str(result)}]}, "id": req_id}
            except Exception as e:
                return {"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}, "id": req_id}

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "result": {
                    "tools": [
                        {"name": t.name, "description": t.description, "inputSchema": t.parameters}
                        for t in self.tools.values()
                    ]
                },
                "id": req_id,
            }

        elif method == "resources/list":
            return {
                "jsonrpc": "2.0",
                "result": {
                    "resources": [
                        {"uri": r.uri, "name": r.name, "description": r.description, "mimeType": r.mime_type}
                        for r in self.resources.values()
                    ]
                },
                "id": req_id,
            }

        return {"jsonrpc": "2.0", "result": {}, "id": req_id}

    def stop(self) -> None:
        self._running = False
        logger.info("MCP Server arrêté")


import asyncio
