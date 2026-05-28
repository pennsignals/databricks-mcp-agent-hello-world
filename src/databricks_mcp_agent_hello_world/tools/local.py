from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator, SchemaError

from .runtime import RuntimeTool, ToolSource


@dataclass(frozen=True, slots=True)
class LocalToolDefinition:
    name: str
    description: str
    input_schema: Mapping[str, Any]
    handler: Callable[..., Any]


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
                "parameters": dict(defn.input_schema),
            },
        },
        execute=defn.handler,
        source=ToolSource(type="local_python", id="local_python"),
    )


def build_local_tool_registry(
    definitions: Iterable[LocalToolDefinition],
) -> dict[str, RuntimeTool]:
    registry: dict[str, RuntimeTool] = {}

    for definition in definitions:
        runtime_tool = local_definition_to_runtime_tool(definition)
        if runtime_tool.name in registry:
            raise ValueError(f"Duplicate local tool name: {runtime_tool.name}")
        registry[runtime_tool.name] = runtime_tool

    return registry


def _validate_local_tool_definition(defn: LocalToolDefinition) -> None:
    if not defn.name.strip():
        raise ValueError("Local tool name must not be empty.")
    if not defn.description.strip():
        raise ValueError(f"Local tool {defn.name!r} description must not be empty.")
    if not isinstance(defn.input_schema, Mapping) or not defn.input_schema:
        raise ValueError(f"Local tool {defn.name!r} input_schema must be a non-empty mapping.")
    if defn.input_schema.get("type") != "object":
        raise ValueError(f"Local tool {defn.name!r} input_schema.type must be 'object'.")
    try:
        Draft202012Validator.check_schema(dict(defn.input_schema))
    except SchemaError as exc:
        raise ValueError(
            f"Local tool {defn.name!r} has invalid input_schema: {exc.message}"
        ) from exc
    if not callable(defn.handler):
        raise ValueError(f"Local tool {defn.name!r} execute function must be callable.")
