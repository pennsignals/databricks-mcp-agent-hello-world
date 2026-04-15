import pytest
from pydantic import ValidationError

from databricks_mcp_agent_hello_world.models import ToolSpec


def _base_tool_spec(**overrides) -> dict:
    payload = {
        "tool_name": "sample_tool",
        "description": "Sample description",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "provider_type": "local_python",
        "provider_id": "builtin_tools",
    }
    payload.update(overrides)
    return payload


def test_tool_spec_metadata_defaults_are_applied() -> None:
    tool = ToolSpec(**_base_tool_spec())

    assert tool.capability_tags == []
    assert tool.side_effect_level == "read_only"
    assert tool.data_domains == []
    assert tool.example_uses == []


def test_tool_spec_metadata_is_normalized_deduplicated_and_sorted() -> None:
    tool = ToolSpec(
        **_base_tool_spec(
            capability_tags=["Docs_Search", "docs_search", "config_lookup"],
            data_domains=["Workspace_Config", "workspace_config", "docs"],
        )
    )

    assert tool.capability_tags == ["config_lookup", "docs_search"]
    assert tool.data_domains == ["docs", "workspace_config"]


def test_tool_spec_example_uses_preserves_order_and_deduplicates() -> None:
    tool = ToolSpec(
        **_base_tool_spec(
            example_uses=[
                "Retrieve the runtime target",
                "Retrieve the runtime target",
                "Look up the workspace region",
            ]
        )
    )

    assert tool.example_uses == [
        "Retrieve the runtime target",
        "Look up the workspace region",
    ]


@pytest.mark.parametrize(
    "field_name,bad_values",
    [
        ("capability_tags", [""]),
        ("capability_tags", ["bad tag"]),
        ("capability_tags", ["bad-tag"]),
        ("data_domains", [""]),
        ("data_domains", ["Bad Domain"]),
        ("example_uses", [""]),
    ],
)
def test_tool_spec_rejects_invalid_metadata_values(field_name: str, bad_values: list[str]) -> None:
    with pytest.raises(ValidationError):
        ToolSpec(**_base_tool_spec(**{field_name: bad_values}))


def test_tool_spec_rejects_invalid_side_effect_level() -> None:
    with pytest.raises(ValidationError):
        ToolSpec(**_base_tool_spec(side_effect_level="mutate"))
