from __future__ import annotations

from .config import Settings
from .models import DiscoveredTool, DiscoveryReport
from .providers.factory import get_tool_provider
from .tools.runtime import inventory_hash


def discover_tools(settings: Settings) -> DiscoveryReport:
    provider = get_tool_provider(settings)
    tools = provider.list_tools()
    return DiscoveryReport(
        tool_provider_type=provider.tool_provider_type,
        tool_count=len(tools),
        provider_id=provider.provider_id,
        inventory_hash=inventory_hash(tools),
        tools=[
            DiscoveredTool(
                name=tool.name,
                source_type=tool.source.type,
                source_id=tool.source.id,
                spec=tool.spec,
            )
            for tool in tools
        ],
    )
