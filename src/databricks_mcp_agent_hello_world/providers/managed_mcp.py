from __future__ import annotations

from ..models import ToolCall, ToolResult, ToolSpec
from .base import ToolProvider

MANAGED_MCP_NOT_IMPLEMENTED_MESSAGE = (
    "managed_mcp is retained as a near-term extension point but is not implemented yet."
)


class ManagedMCPToolProvider(ToolProvider):
    provider_type = "managed_mcp"
    provider_id = "managed_mcp_placeholder"

    def list_tools(self) -> list[ToolSpec]:
        raise NotImplementedError(MANAGED_MCP_NOT_IMPLEMENTED_MESSAGE)

    def inventory_hash(self) -> str:
        raise NotImplementedError(MANAGED_MCP_NOT_IMPLEMENTED_MESSAGE)

    def call_tool(self, tool_call: ToolCall) -> ToolResult:
        raise NotImplementedError(MANAGED_MCP_NOT_IMPLEMENTED_MESSAGE)
