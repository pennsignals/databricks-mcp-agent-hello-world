from __future__ import annotations

from collections.abc import Mapping

from ..app.registry import build_app_local_tool_registry
from ..tools.runtime import RuntimeTool
from .base import ToolProvider


class LocalPythonToolProvider(ToolProvider):
    provider_id = "local_python"

    def __init__(
        self,
        tool_registry: Mapping[str, RuntimeTool] | None = None,
    ) -> None:
        self._tool_registry = dict(
            tool_registry if tool_registry is not None else build_app_local_tool_registry()
        )

    def list_tools(self) -> list[RuntimeTool]:
        return list(self._tool_registry.values())
