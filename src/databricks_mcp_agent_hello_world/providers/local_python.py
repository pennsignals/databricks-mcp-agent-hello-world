from __future__ import annotations

from ..app.registry import build_app_local_tool_registry
from ..tools.runtime import RuntimeTool
from .base import ToolProvider


class LocalPythonToolProvider(ToolProvider):
    provider_id = "local_python"

    def __init__(self) -> None:
        self._tool_registry = build_app_local_tool_registry()

    def list_tools(self) -> list[RuntimeTool]:
        return list(self._tool_registry.values())
