from __future__ import annotations

from ..config import Settings
from ..providers.base import ToolExecutor
from ..providers.local_python import LocalPythonToolExecutor


def get_tool_executor(settings: Settings) -> ToolExecutor:
    if settings.tool_provider_type == "local_python":
        return LocalPythonToolExecutor(settings)
    if settings.tool_provider_type == "managed_mcp":
        raise NotImplementedError(
            "tool_provider_type='managed_mcp' is reserved for future support and is not "
            "implemented in this MVP runtime."
        )
    raise ValueError(f"Unsupported tool_provider_type: {settings.tool_provider_type}")
