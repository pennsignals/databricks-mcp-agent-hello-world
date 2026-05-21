from __future__ import annotations

import pytest

from databricks_mcp_agent_hello_world.tools.local import (
    LocalToolDefinition,
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
                fn=dict,
            ),
            "name must not be empty",
            id="blank-name",
        ),
        pytest.param(
            LocalToolDefinition(
                name="tool",
                description="desc",
                input_schema={"type": "array"},
                fn=dict,
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
                fn=dict,
            ),
            "Local tool 'tool' has invalid input_schema",
            id="invalid-json-schema",
        ),
        pytest.param(
            LocalToolDefinition(
                name="tool",
                description="  ",
                input_schema={"type": "object", "properties": {}},
                fn=dict,
            ),
            "description",
            id="blank-description",
        ),
        pytest.param(
            LocalToolDefinition(
                name="tool",
                description="desc",
                input_schema={"type": "object", "properties": {}},
                fn=None,
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
            fn=dict,
        )
    )

    assert normalized_tool.name == "sample_tool"
    assert normalized_tool.spec["function"]["name"] == "sample_tool"
    assert normalized_tool.spec["function"]["description"] == "Sample description"
