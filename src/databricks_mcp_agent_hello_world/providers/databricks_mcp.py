from __future__ import annotations

from ..config import Settings
from ..tools.runtime import RuntimeTool, ToolSource
from .base import ToolProvider


class DatabricksMCPToolProvider(ToolProvider):
    provider_type = "databricks_mcp"

    def __init__(self, settings: Settings):
        if settings.mcp.server is None:
            raise ValueError(
                "databricks_mcp requires mcp.server.url. "
                "Configure mcp.server.url and mcp.server.name."
            )
        self.settings = settings
        self.provider_id = settings.mcp.server.name
        from databricks_openai import McpServerToolkit

        self.toolkit = McpServerToolkit(
            url=settings.mcp.server.url,
            name=settings.mcp.server.name,
            workspace_client=_build_workspace_client(settings),
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


def _build_workspace_client(settings: Settings):
    from databricks.sdk import WorkspaceClient

    if settings.databricks_config_profile:
        return WorkspaceClient(profile=settings.databricks_config_profile)
    return WorkspaceClient()
