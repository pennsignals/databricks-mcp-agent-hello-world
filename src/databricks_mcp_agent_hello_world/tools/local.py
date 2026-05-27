from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator, SchemaError

from .runtime import RuntimeTool, ToolSource


@dataclass(frozen=True, slots=True)
class LocalToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[..., Any]


def local_definition_to_runtime_tool(defn: LocalToolDefinition) -> RuntimeTool:
    _validate_local_tool_definition(defn)
    name = defn.name.strip()
    description = defn.description.strip()
    return RuntimeTool(
        name=name,
        spec={
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": defn.input_schema,
            },
        },
        execute=defn.fn,
        source=ToolSource(type="local_python", id="local_python"),
    )


def _validate_local_tool_definition(defn: LocalToolDefinition) -> None:
    if not defn.name.strip():
        raise ValueError("Local tool name must not be empty.")
    if not defn.description.strip():
        raise ValueError(f"Local tool {defn.name!r} description must not be empty.")
    if defn.input_schema.get("type") != "object":
        raise ValueError(f"Local tool {defn.name!r} input_schema.type must be 'object'.")
    try:
        Draft202012Validator.check_schema(defn.input_schema)
    except SchemaError as exc:
        raise ValueError(
            f"Local tool {defn.name!r} has invalid input_schema: {exc.message}"
        ) from exc
    if not callable(defn.fn):
        raise ValueError(f"Local tool {defn.name!r} execute function must be callable.")
