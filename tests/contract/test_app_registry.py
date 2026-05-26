from __future__ import annotations

import pytest

from databricks_mcp_agent_hello_world.app.registry import (
    LOCAL_TOOL_DEFINITIONS,
    LOCAL_TOOL_REGISTRY,
    build_local_tool_registry,
    list_local_tools,
)
from databricks_mcp_agent_hello_world.tools.local import (
    LocalToolDefinition,
    local_definition_to_runtime_tool,
)


def test_authored_app_registry_exposes_expected_inventory() -> None:
    assert [definition.name for definition in LOCAL_TOOL_DEFINITIONS] == [
        "get_user_profile",
        "search_onboarding_docs",
        "get_workspace_setting",
        "list_recent_job_runs",
        "create_support_ticket",
    ]


def test_public_local_tool_names_are_stable() -> None:
    assert {definition.name for definition in LOCAL_TOOL_DEFINITIONS} == {
        "get_user_profile",
        "search_onboarding_docs",
        "get_workspace_setting",
        "list_recent_job_runs",
        "create_support_ticket",
    }


def test_build_local_tool_registry_keys_by_definition_name() -> None:
    registry = build_local_tool_registry(LOCAL_TOOL_DEFINITIONS)

    assert registry == LOCAL_TOOL_REGISTRY
    assert registry["get_user_profile"].name == "get_user_profile"


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
        assert not hasattr(definition, "provider_id")
        assert not hasattr(definition, "capability_tags")
        assert not hasattr(definition, "side_effect_level")
        assert not hasattr(definition, "data_domains")
        assert not hasattr(definition, "example_uses")


def test_build_local_tool_registry_rejects_duplicate_names() -> None:
    duplicate_tool = LocalToolDefinition(
        name="duplicate",
        description="Duplicate tool",
        input_schema={"type": "object", "properties": {}},
        fn=dict,
    )

    with pytest.raises(ValueError, match="Duplicate local tool name: duplicate"):
        build_local_tool_registry((duplicate_tool, duplicate_tool))


def test_build_local_tool_registry_rejects_empty_name() -> None:
    definition = LocalToolDefinition(
        name="",
        description="Empty name",
        input_schema={"type": "object", "properties": {}},
        fn=dict,
    )

    with pytest.raises(ValueError, match=r"Local tool definition has empty name\."):
        build_local_tool_registry((definition,))


def test_build_local_tool_registry_rejects_whitespace_only_name() -> None:
    definition = LocalToolDefinition(
        name="   ",
        description="Whitespace-only name",
        input_schema={"type": "object", "properties": {}},
        fn=dict,
    )

    with pytest.raises(ValueError, match=r"Local tool definition has empty name\."):
        build_local_tool_registry((definition,))


def test_build_local_tool_registry_rejects_non_callable_fn() -> None:
    definition = LocalToolDefinition(
        name="not_callable",
        description="Non-callable fn",
        input_schema={"type": "object", "properties": {}},
        fn="not callable",  # type: ignore[arg-type]
    )

    with pytest.raises(
        ValueError,
        match=r"Local tool `not_callable` has non-callable fn\.",
    ):
        build_local_tool_registry((definition,))
