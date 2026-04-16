from __future__ import annotations

from ..config import Settings
from .base import ToolProvider
from .local_python import LocalPythonToolProvider


def get_tool_provider(settings: Settings) -> ToolProvider:
    if settings.tool_provider_type == "local_python":
        return LocalPythonToolProvider()
    if settings.tool_provider_type == "managed_mcp":
        raise NotImplementedError(
            "tool_provider_type='managed_mcp' is a future extension point in this "
            "template. It is not implemented today; once supported, the same "
            "runtime discovery and LLM-driven tool-selection architecture will apply."
        )
    raise ValueError(f"Unsupported tool_provider_type: {settings.tool_provider_type}")
