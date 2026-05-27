from __future__ import annotations

from typing import Any

from ..app.registry import build_local_tool_registry
from ..tools.local import local_definition_to_runtime_tool
from ..tools.runtime import RuntimeTool
from ..tools.validation import validate_tool_arguments
from .base import ToolProvider


class LocalPythonToolProvider(ToolProvider):
    provider_id = "local_python"

    def __init__(self) -> None:
        self._registry = build_local_tool_registry()
        self._runtime_tools = {
            name: local_definition_to_runtime_tool(definition)
            for name, definition in self._registry.items()
        }

    def list_tools(self) -> list[RuntimeTool]:
        return list(self._runtime_tools.values())

    def invoke_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        try:
            tool = self._runtime_tools[name]
        except KeyError as exc:
            raise ValueError(f"Unknown local tool: {name}") from exc
        validated_arguments = validate_tool_arguments(
            tool_name=tool.name,
            tool_spec=tool.spec,
            arguments=arguments,
        )
        return tool.execute(**validated_arguments)
