from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import ToolCall, ToolResult, ToolSpec


class ToolProvider(ABC):
    provider_type: str
    provider_id: str

    @abstractmethod
    def list_tools(self) -> list[ToolSpec]:
        raise NotImplementedError

    @abstractmethod
    def inventory_hash(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def call_tool(self, tool_call: ToolCall) -> ToolResult:
        raise NotImplementedError
