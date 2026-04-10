from __future__ import annotations

from ..models import ToolCall, ToolResult, ToolSpec
from .base import ToolExecutor, ToolProvider


class ManagedMCPToolProvider(ToolProvider):
    provider_type = "managed_mcp"
    provider_id = "managed_mcp_placeholder"

    def list_tools(self) -> list[ToolSpec]:
        raise NotImplementedError(
            "Managed MCP is intentionally a future adapter target "
            "and is not implemented at runtime."
        )

    def inventory_hash(self) -> str:
        raise NotImplementedError(
            "Managed MCP is intentionally a future adapter target "
            "and is not implemented at runtime."
        )


class ManagedMCPToolExecutor(ToolExecutor):
    def call_tool(self, tool_call: ToolCall) -> ToolResult:
        raise NotImplementedError(
            "Managed MCP is intentionally a future adapter target "
            "and is not implemented at runtime."
        )
