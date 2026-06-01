from __future__ import annotations

from jsonschema import Draft202012Validator

from databricks_tool_agent_template.app.registry import (
    LOCAL_TOOL_DEFINITIONS,
    build_app_local_tool_registry,
)
from databricks_tool_agent_template.tools.runtime import RuntimeTool


def test_demo_local_tools_are_registered() -> None:
    assert [definition.name for definition in LOCAL_TOOL_DEFINITIONS] == [
        "lookup_customer",
        "create_support_ticket",
    ]


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


def test_lookup_customer_description_supports_model_tool_selection() -> None:
    descriptions = {
        definition.name: definition.description for definition in LOCAL_TOOL_DEFINITIONS
    }
    lookup_description = descriptions["lookup_customer"].lower()

    assert "customer_id" in lookup_description
    assert "customer name" in lookup_description
    assert "tier" in lookup_description
    assert "region" in lookup_description


def test_local_tool_schemas_are_valid_current_json_schemas() -> None:
    for definition in LOCAL_TOOL_DEFINITIONS:
        assert definition.name
        assert definition.input_schema["type"] == "object"
        assert "properties" in definition.input_schema
        Draft202012Validator.check_schema(dict(definition.input_schema))
