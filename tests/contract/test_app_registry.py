from __future__ import annotations

from databricks_mcp_agent_hello_world.app.registry import (
    LOCAL_TOOL_DEFINITIONS,
    build_app_local_tool_registry,
)
from databricks_mcp_agent_hello_world.tools.runtime import RuntimeTool


def test_authored_app_registry_exposes_expected_inventory() -> None:
    assert [definition.name for definition in LOCAL_TOOL_DEFINITIONS] == [
        "lookup_customer",
        "create_support_ticket",
    ]


def test_public_local_tool_names_are_stable() -> None:
    assert {definition.name for definition in LOCAL_TOOL_DEFINITIONS} == {
        "lookup_customer",
        "create_support_ticket",
    }


def test_build_app_local_tool_registry_returns_demo_runtime_tools() -> None:
    registry = build_app_local_tool_registry()

    assert list(registry) == ["lookup_customer", "create_support_ticket"]
    assert registry["lookup_customer"].name == "lookup_customer"
    assert registry["create_support_ticket"].name == "create_support_ticket"
    assert all(isinstance(tool, RuntimeTool) for tool in registry.values())


def test_local_tool_names_are_unique() -> None:
    names = [definition.name for definition in LOCAL_TOOL_DEFINITIONS]

    assert len(names) == len(set(names))


def test_local_tool_definitions_include_required_runtime_contract() -> None:
    registry = build_app_local_tool_registry()

    for definition in LOCAL_TOOL_DEFINITIONS:
        tool = registry[definition.name]

        assert tool.name == definition.name
        assert tool.spec["function"]["name"] == definition.name
        assert tool.spec["function"]["description"] == definition.description
        assert tool.spec["function"]["parameters"] == definition.input_schema
        assert definition.input_schema["type"] == "object"


def test_lookup_customer_description_supports_model_tool_selection() -> None:
    descriptions = {
        definition.name: definition.description for definition in LOCAL_TOOL_DEFINITIONS
    }
    lookup_description = descriptions["lookup_customer"].lower()

    assert "customer_id" in lookup_description
    assert "customer name" in lookup_description
    assert "tier" in lookup_description
    assert "region" in lookup_description


def test_local_definitions_do_not_own_provider_or_governance_metadata() -> None:
    for definition in LOCAL_TOOL_DEFINITIONS:
        assert not hasattr(definition, "provider_id")
        assert not hasattr(definition, "capability_tags")
        assert not hasattr(definition, "side_effect_level")
        assert not hasattr(definition, "data_domains")
        assert not hasattr(definition, "example_uses")
