from __future__ import annotations

from ..clients.databricks import get_workspace_client
from ..config import Settings
from ..tools.runtime import RuntimeTool, ToolSource
from .base import ToolProvider


class DatabricksMCPToolProvider(ToolProvider):
    def __init__(self, settings: Settings):
        server = settings.tools.databricks_mcp.server
        if server is None:
            raise ValueError(
                "databricks_mcp requires tools.databricks_mcp.server.name and "
                "tools.databricks_mcp.server.url."
            )
        self.settings = settings
        self.provider_id = server.name
        from databricks_openai.mcp_server_toolkit import McpServerToolkit

        self.toolkit = McpServerToolkit(
            url=server.url,
            name=server.name,
            workspace_client=get_workspace_client(settings),
        )

    def list_tools(self) -> list[RuntimeTool]:
        return [
            RuntimeTool(
                name=tool.name,
                spec=tool.spec,
                execute=tool.execute,
                source=ToolSource(type="databricks_mcp", id=self.provider_id),
            )
            for tool in self.toolkit.get_tools()
        ]
