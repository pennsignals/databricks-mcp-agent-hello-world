from __future__ import annotations

from dataclasses import replace

from databricks_mcp_agent_hello_world.config import PromptConfig, Settings, StorageConfig


def make_settings(**overrides: object) -> Settings:
    storage_overrides = overrides.pop("storage", None)
    prompts_overrides = overrides.pop("prompts", None)

    settings = Settings(
        tool_provider_type="local_python",
        llm_endpoint_name="endpoint-a",
        max_agent_steps=8,
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
    if overrides:
        settings = replace(settings, **overrides)
    return settings
