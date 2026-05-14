from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .runtime import RuntimeTool, ToolSource


@dataclass(frozen=True, slots=True)
class LocalToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[..., Any]


def local_definition_to_runtime_tool(defn: LocalToolDefinition) -> RuntimeTool:
    _validate_local_tool_definition(defn)
    return RuntimeTool(
        name=defn.name,
        spec={
            "type": "function",
            "function": {
                "name": defn.name,
                "description": defn.description,
                "parameters": defn.input_schema,
            },
        },
        execute=defn.fn,
        source=ToolSource(type="local_python", id="builtin_tools"),
    )


def _validate_local_tool_definition(defn: LocalToolDefinition) -> None:
    if not defn.name.strip():
        raise ValueError("Local tool name must not be empty.")
    if not defn.description.strip():
        raise ValueError(f"Local tool {defn.name!r} description must not be empty.")
    if defn.input_schema.get("type") != "object":
        raise ValueError(f"Local tool {defn.name!r} input_schema.type must be 'object'.")
    if not callable(defn.fn):
        raise ValueError(f"Local tool {defn.name!r} execute function must be callable.")
