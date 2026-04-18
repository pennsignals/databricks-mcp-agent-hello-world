from __future__ import annotations

from databricks_mcp_agent_hello_world.app.registry import TOOL_DEFINITIONS, list_authored_tools
from databricks_mcp_agent_hello_world.models import ToolSpec


def test_authored_app_registry_exposes_expected_inventory() -> None:
    assert list(TOOL_DEFINITIONS) == [
        "get_user_profile",
        "search_onboarding_docs",
        "get_workspace_setting",
        "list_recent_job_runs",
        "create_support_ticket",
    ]


def test_authored_tool_definitions_include_required_metadata_and_valid_schema() -> None:
    for definition in list_authored_tools():
        tool = ToolSpec(
            tool_name=definition.tool_name,
            description=definition.description,
            input_schema=definition.input_schema,
            provider_type="local_python",
            provider_id="builtin_tools",
            capability_tags=definition.capability_tags,
            side_effect_level=definition.side_effect_level,
            data_domains=definition.data_domains,
            example_uses=definition.example_uses,
        )

        assert tool.tool_name == definition.tool_name
        assert definition.capability_tags
        assert definition.data_domains
        assert definition.example_uses
        assert definition.side_effect_level in {"read_only", "write"}
        assert definition.input_schema["type"] == "object"


def test_authored_registry_does_not_own_provider_metadata() -> None:
    for definition in list_authored_tools():
        assert not hasattr(definition, "provider_type")
        assert not hasattr(definition, "provider_id")
