from __future__ import annotations

import pytest

from databricks_mcp_agent_hello_world.tools.local import (
    LocalToolDefinition,
    build_local_tool_registry,
    local_definition_to_runtime_tool,
)


@pytest.mark.parametrize(
    ("definition", "message"),
    [
        pytest.param(
            LocalToolDefinition(
                name="   ",
                description="desc",
                input_schema={"type": "object", "properties": {}},
                handler=dict,
            ),
            "name must not be empty",
            id="blank-name",
        ),
        pytest.param(
            LocalToolDefinition(
                name="tool",
                description="desc",
                input_schema={"type": "array"},
                handler=dict,
            ),
            r"input_schema\.type",
            id="non-object-schema",
        ),
        pytest.param(
            LocalToolDefinition(
                name="tool",
                description="desc",
                input_schema={
                    "type": "object",
                    "properties": {"value": {"type": "not-a-json-schema-type"}},
                },
                handler=dict,
            ),
            "Local tool 'tool' has invalid input_schema",
            id="invalid-json-schema",
        ),
        pytest.param(
            LocalToolDefinition(
                name="tool",
                description="  ",
                input_schema={"type": "object", "properties": {}},
                handler=dict,
            ),
            "description",
            id="blank-description",
        ),
        pytest.param(
            LocalToolDefinition(
                name="tool",
                description="desc",
                input_schema={},
                handler=dict,
            ),
            "non-empty mapping",
            id="empty-schema",
        ),
        pytest.param(
            LocalToolDefinition(
                name="tool",
                description="desc",
                input_schema={"type": "object", "properties": {}},
                handler=None,
            ),
            "callable",
            id="non-callable",
        ),
    ],
)
def test_local_definition_to_runtime_tool_rejects_invalid_definitions(
    definition: LocalToolDefinition,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        local_definition_to_runtime_tool(definition)


def test_local_definition_to_runtime_tool_normalizes_metadata() -> None:
    normalized_tool = local_definition_to_runtime_tool(
        LocalToolDefinition(
            name=" sample_tool ",
            description=" Sample description ",
            input_schema={"type": "object", "properties": {}},
            handler=dict,
        )
    )

    assert normalized_tool.name == "sample_tool"
    assert normalized_tool.spec["function"]["name"] == "sample_tool"
    assert normalized_tool.spec["function"]["description"] == "Sample description"


def test_local_definition_to_runtime_tool_preserves_handler() -> None:
    def custom_handler(value: str) -> dict[str, str]:
        return {"value": value}

    runtime_tool = local_definition_to_runtime_tool(
        LocalToolDefinition(
            name="custom_tool",
            description="Custom tool",
            input_schema={
                "type": "object",
                "properties": {"value": {"type": "string"}},
            },
            handler=custom_handler,
        )
    )

    assert runtime_tool.execute is custom_handler
    assert runtime_tool.execute("sample") == {"value": "sample"}


def test_build_local_tool_registry_rejects_duplicate_runtime_names() -> None:
    first_tool = LocalToolDefinition(
        name="duplicate",
        description="First duplicate tool",
        input_schema={"type": "object", "properties": {}},
        handler=dict,
    )
    second_tool = LocalToolDefinition(
        name=" duplicate ",
        description="Second duplicate tool",
        input_schema={"type": "object", "properties": {}},
        handler=dict,
    )

    with pytest.raises(ValueError, match="Duplicate local tool name: duplicate"):
        build_local_tool_registry((first_tool, second_tool))
