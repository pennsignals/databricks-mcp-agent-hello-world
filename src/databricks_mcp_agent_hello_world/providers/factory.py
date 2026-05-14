from __future__ import annotations

from ..config import Settings
from .base import ToolProvider
from .databricks_mcp import DatabricksMCPToolProvider
from .local_python import LocalPythonToolProvider


def get_tool_provider(settings: Settings) -> ToolProvider:
    if settings.tool_provider_type == "local_python":
        return LocalPythonToolProvider(settings)
    if settings.tool_provider_type == "databricks_mcp":
        return DatabricksMCPToolProvider(settings)
    if settings.tool_provider_type == "managed_mcp":
        raise ValueError(
            "managed_mcp has been replaced by databricks_mcp. "
            "Configure mcp.server.url and mcp.server.name."
        )
    raise ValueError(f"Unsupported tool_provider_type: {settings.tool_provider_type}")
