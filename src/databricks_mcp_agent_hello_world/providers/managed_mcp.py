from __future__ import annotations

from ..models import ToolCall, ToolResult, ToolSpec
from .base import ToolExecutor, ToolProvider


class ManagedMCPToolProvider(ToolProvider):
    provider_type = "managed_mcp"
    provider_id = "managed_mcp_placeholder"

    def list_tools(self) -> list[ToolSpec]:
        raise NotImplementedError(
            "Managed MCP is a future extension point for this template. It is "
            "not implemented today, and the supported runtime flow remains "
            "provider discovery plus LLM-driven tool selection once an MCP "
            "provider exists."
        )

    def inventory_hash(self) -> str:
        raise NotImplementedError(
            "Managed MCP is a future extension point for this template. It is "
            "not implemented today, and the supported runtime flow remains "
            "provider discovery plus LLM-driven tool selection once an MCP "
            "provider exists."
        )


class ManagedMCPToolExecutor(ToolExecutor):
    def call_tool(self, tool_call: ToolCall) -> ToolResult:
        raise NotImplementedError(
            "Managed MCP is a future extension point for this template. It is "
            "not implemented today, and the supported runtime flow remains "
            "provider discovery plus LLM-driven tool selection once an MCP "
            "provider exists."
        )
