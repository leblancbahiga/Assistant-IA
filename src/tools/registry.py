from __future__ import annotations
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable


@dataclass
class ToolParameter:
    name: str
    type: str  # "str", "int", "float", "bool", "list"
    description: str
    required: bool = True
    default: Any = None


@dataclass
class ToolDefinition:
    name: str
    description: str
    category: str  # "document", "code", "web", "memory", "system"
    parameters: list[ToolParameter]

    def to_schema(self) -> dict:
        """Convertit en schéma JSON pour le LLM."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    p.name: {
                        "type": p.type,
                        "description": p.description,
                        **({"default": p.default} if p.default is not None else {}),
                    }
                    for p in self.parameters
                },
                "required": [p.name for p in self.parameters if p.required],
            },
        }


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Enregistre un outil. Écrase si même nom."""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> bool:
        """Supprime un outil. Retourne True si trouvé."""
        return self._tools.pop(name, None) is not None

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def list_by_category(self, category: str) -> list[ToolDefinition]:
        return [t for t in self._tools.values() if t.category == category]

    def search(self, query: str) -> list[ToolDefinition]:
        """Recherche par nom ou description (insensible à la casse)."""
        q = query.lower()
        return [
            t
            for t in self._tools.values()
            if q in t.name.lower() or q in t.description.lower()
        ]

    def to_llm_schema(self) -> list[dict]:
        """Exporte la liste des schémas pour le prompt LLM."""
        return [t.to_schema() for t in self._tools.values()]

    def load_from_file(self, path: str | Path) -> int:
        """Charge des outils depuis un fichier JSON. Retourne le nombre chargé."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        count = 0
        for item in data.get("tools", []):
            params = [ToolParameter(**p) for p in item.get("parameters", [])]
            tool = ToolDefinition(
                name=item["name"],
                description=item["description"],
                category=item.get("category", "system"),
                parameters=params,
            )
            self.register(tool)
            count += 1
        return count

    def save_to_file(self, path: str | Path) -> None:
        """Sauvegarde les outils dans un fichier JSON."""
        data = {"tools": [asdict(t) for t in self._tools.values()]}
        Path(path).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def __len__(self) -> int:
        return len(self._tools)


# ── ToolResult & ToolExecutor ──────────────────────────────────


@dataclass
class ToolResult:
    """Résultat d'exécution d'un outil."""

    tool_name: str
    success: bool
    output: Any
    error: str | None = None
    duration_ms: float = 0.0


class ToolExecutor:
    """Exécute des outils du registre avec gestion d'erreurs et timing."""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self._handlers: dict[str, Callable] = {}

    def register_handler(self, tool_name: str, handler: Callable) -> None:
        """Enregistre une fonction d'exécution pour un outil."""
        self._handlers[tool_name] = handler

    def execute(self, tool_name: str, params: dict[str, Any]) -> ToolResult:
        """Exécute un outil par son nom avec les paramètres donnés."""
        # Vérifier que l'outil existe dans le registre
        tool = self.registry.get(tool_name)
        if tool is None:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output=None,
                error=f"Outil inconnu: {tool_name}",
            )
        # Vérifier qu'un handler est enregistré
        handler = self._handlers.get(tool_name)
        if handler is None:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output=None,
                error=f"Pas de handler pour: {tool_name}",
            )
        # Exécuter
        start = time.time()
        try:
            output = handler(**params)
            duration = (time.time() - start) * 1000
            return ToolResult(
                tool_name=tool_name,
                success=True,
                output=output,
                duration_ms=duration,
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output=None,
                error=str(e),
                duration_ms=duration,
            )
