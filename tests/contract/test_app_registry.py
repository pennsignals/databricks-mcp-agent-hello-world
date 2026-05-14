from __future__ import annotations

import pytest

from databricks_mcp_agent_hello_world.app import registry
from databricks_mcp_agent_hello_world.app.registry import TOOL_DEFINITIONS, list_local_tools
from databricks_mcp_agent_hello_world.tools.local import (
    LocalToolDefinition,
    local_definition_to_runtime_tool,
)


def test_authored_app_registry_exposes_expected_inventory() -> None:
    assert list(TOOL_DEFINITIONS) == [
        "get_user_profile",
        "search_onboarding_docs",
        "get_workspace_setting",
        "list_recent_job_runs",
        "create_support_ticket",
    ]


def test_local_tool_definitions_include_required_runtime_contract() -> None:
    for definition in list_local_tools():
        tool = local_definition_to_runtime_tool(definition)

        assert tool.name == definition.name
        assert tool.spec["function"]["name"] == definition.name
        assert tool.spec["function"]["description"] == definition.description
        assert tool.spec["function"]["parameters"] == definition.input_schema
        assert definition.input_schema["type"] == "object"


def test_local_registry_does_not_own_provider_or_governance_metadata() -> None:
    for definition in list_local_tools():
        assert not hasattr(definition, "provider_type")
        assert not hasattr(definition, "provider_id")
        assert not hasattr(definition, "capability_tags")
        assert not hasattr(definition, "side_effect_level")
        assert not hasattr(definition, "data_domains")
        assert not hasattr(definition, "example_uses")


def test_local_registry_rejects_duplicate_tool_names(monkeypatch) -> None:
    duplicate_tool = LocalToolDefinition(
        name="duplicate",
        description="Duplicate tool",
        input_schema={"type": "object", "properties": {}},
        fn=lambda: {},
    )
    monkeypatch.setattr(
        registry,
        "TOOL_DEFINITIONS",
        {"first": duplicate_tool, "second": duplicate_tool},
    )

    with pytest.raises(ValueError, match="Local tool names must be unique: duplicate"):
        registry.list_local_tools()
