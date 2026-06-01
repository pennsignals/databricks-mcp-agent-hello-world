from __future__ import annotations

from dataclasses import replace

from databricks_tool_agent_template.config import (
    MCPServerConfig,
    PromptConfig,
    Settings,
    StorageConfig,
    ToolsConfig,
)


def make_settings(**overrides: object) -> Settings:
    storage_overrides = overrides.pop("storage", None)
    prompts_overrides = overrides.pop("prompts", None)
    tools_overrides = overrides.pop("tools", None)

    settings = Settings(
        llm_endpoint_name="endpoint-a",
        max_agent_steps=8,
        tools=ToolsConfig(),
        storage=StorageConfig(
            agent_events_table="main.agent.agent_events",
            local_data_dir="./.local_state",
        ),
        prompts=PromptConfig(
            agent_system_prompt_path="tests/prompt.txt",
            agent_system_prompt="Use the provided tools when helpful.",
        ),
    )
    if storage_overrides is not None:
        if not isinstance(storage_overrides, dict):
            raise TypeError("storage overrides must be a dict")
        settings = replace(settings, storage=replace(settings.storage, **storage_overrides))
    if prompts_overrides is not None:
        if not isinstance(prompts_overrides, dict):
            raise TypeError("prompts overrides must be a dict")
        settings = replace(settings, prompts=replace(settings.prompts, **prompts_overrides))
    if tools_overrides is not None:
        if not isinstance(tools_overrides, dict):
            raise TypeError("tools overrides must be a dict")
        tools_overrides = dict(tools_overrides)
        local_python_overrides = tools_overrides.pop("local_python", None)
        databricks_mcp_overrides = tools_overrides.pop("databricks_mcp", None)
        tools = settings.tools
        if local_python_overrides is not None:
            tools = replace(
                tools,
                local_python=replace(tools.local_python, **local_python_overrides),
            )
        if databricks_mcp_overrides is not None:
            databricks_mcp_overrides = dict(databricks_mcp_overrides)
            server_overrides = databricks_mcp_overrides.pop("server", None)
            databricks_mcp = tools.databricks_mcp
            if server_overrides is not None:
                databricks_mcp = replace(
                    databricks_mcp,
                    server=MCPServerConfig(**server_overrides),
                )
            databricks_mcp = replace(databricks_mcp, **databricks_mcp_overrides)
            tools = replace(tools, databricks_mcp=databricks_mcp)
        if tools_overrides:
            tools = replace(tools, **tools_overrides)
        settings = replace(settings, tools=tools)
    if overrides:
        settings = replace(settings, **overrides)
    return settings
