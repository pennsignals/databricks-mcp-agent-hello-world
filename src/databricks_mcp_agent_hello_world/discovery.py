from __future__ import annotations

from .config import Settings
from .models import DiscoveryReport
from .providers.factory import get_tool_provider


def discover_tools(settings: Settings) -> DiscoveryReport:
    provider = get_tool_provider(settings)
    tools = provider.list_tools()
    return DiscoveryReport(
        provider_type=provider.provider_type,
        tool_count=len(tools),
        provider_id=provider.provider_id,
        inventory_hash=provider.inventory_hash(),
        tools=tools,
    )
