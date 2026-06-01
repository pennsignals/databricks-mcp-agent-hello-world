from __future__ import annotations

from ..tools.runtime import RuntimeTool
from .base import ToolProvider


class CompositeToolProvider(ToolProvider):
    def __init__(self, providers: list[ToolProvider]) -> None:
        self._providers = providers
        self.provider_id = f"composite:{','.join(provider.provider_id for provider in providers)}"
        self._tools: list[RuntimeTool] | None = None

    def list_tools(self) -> list[RuntimeTool]:
        if self._tools is None:
            self._tools = self._discover_tools()
        return list(self._tools)

    def _discover_tools(self) -> list[RuntimeTool]:
        tools: list[RuntimeTool] = []
        seen: dict[str, ToolProvider] = {}

        for provider in self._providers:
            for tool in provider.list_tools():
                if tool.name in seen:
                    first_provider = seen[tool.name]
                    raise ValueError(
                        f"Duplicate tool name {tool.name!r} from "
                        f"{first_provider.provider_id} and {provider.provider_id}"
                    )
                seen[tool.name] = provider
                tools.append(tool)

        return tools
