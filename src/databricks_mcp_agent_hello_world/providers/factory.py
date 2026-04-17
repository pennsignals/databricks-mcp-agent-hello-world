from __future__ import annotations

from ..config import Settings
from .base import ToolProvider
from .local_python import LocalPythonToolProvider
from .managed_mcp import ManagedMCPToolProvider


def get_tool_provider(settings: Settings) -> ToolProvider:
    if settings.tool_provider_type == "local_python":
        return LocalPythonToolProvider(settings)
    if settings.tool_provider_type == "managed_mcp":
        return ManagedMCPToolProvider()
    raise ValueError(f"Unsupported tool_provider_type: {settings.tool_provider_type}")
