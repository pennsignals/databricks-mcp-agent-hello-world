from __future__ import annotations

from ..config import Settings
from .base import ToolProvider
from .composite import CompositeToolProvider
from .databricks_mcp import DatabricksMCPToolProvider
from .local_python import LocalPythonToolProvider


def get_tool_provider(settings: Settings) -> ToolProvider:
    providers: list[ToolProvider] = []

    if settings.tools.local_python.enabled:
        providers.append(LocalPythonToolProvider())

    if settings.tools.databricks_mcp.enabled:
        providers.append(DatabricksMCPToolProvider(settings))

    if not providers:
        raise ValueError("At least one tool source must be enabled.")

    if len(providers) == 1:
        return providers[0]

    return CompositeToolProvider(providers)
