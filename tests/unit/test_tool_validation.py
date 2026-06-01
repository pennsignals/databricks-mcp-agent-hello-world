from __future__ import annotations

import pytest

from databricks_tool_agent_template.tools.validation import (
    ToolInputValidationError,
    ToolSchemaValidationError,
    get_tool_parameters_schema,
    validate_tool_arguments,
)


def _tool_spec(schema: dict | None = None) -> dict:
    function = {"name": "get_user_profile"}
    if schema is not None:
        function["parameters"] = schema
    return {"type": "function", "function": function}


def test_get_tool_parameters_schema_returns_schema_when_present() -> None:
    schema = {"type": "object", "properties": {}}

    assert get_tool_parameters_schema(_tool_spec(schema)) is schema


def test_get_tool_parameters_schema_returns_none_for_missing_or_malformed_schema() -> None:
    assert get_tool_parameters_schema({"type": "function"}) is None
    assert get_tool_parameters_schema({"type": "function", "function": "not-a-dict"}) is None
    assert get_tool_parameters_schema(_tool_spec()) is None
    assert get_tool_parameters_schema(_tool_spec({"type": "object"}) | {"function": {}}) is None


def test_validate_tool_arguments_accepts_valid_arguments_without_mutation() -> None:
    arguments = {"user_id": "usr_ada_01"}

    validated = validate_tool_arguments(
        tool_name="get_user_profile",
        tool_spec=_tool_spec(
            {
                "type": "object",
                "required": ["user_id"],
                "properties": {"user_id": {"type": "string"}},
            }
        ),
        arguments=arguments,
    )

    assert validated is arguments
    assert validated == {"user_id": "usr_ada_01"}


def test_validate_tool_arguments_rejects_missing_required_field() -> None:
    with pytest.raises(ToolInputValidationError) as exc_info:
        validate_tool_arguments(
            tool_name="get_user_profile",
            tool_spec=_tool_spec(
                {
                    "type": "object",
                    "required": ["user_id"],
                    "properties": {"user_id": {"type": "string"}},
                }
            ),
            arguments={},
        )

    assert exc_info.value.tool_name == "get_user_profile"
    assert "Invalid arguments for tool `get_user_profile`" in exc_info.value.message
    assert "user_id" in exc_info.value.message
    assert "required property" in exc_info.value.message


def test_validate_tool_arguments_rejects_wrong_type_with_field_path() -> None:
    with pytest.raises(ToolInputValidationError) as exc_info:
        validate_tool_arguments(
            tool_name="get_user_profile",
            tool_spec=_tool_spec(
                {
                    "type": "object",
                    "required": ["user_id"],
                    "properties": {"user_id": {"type": "string"}},
                }
            ),
            arguments={"user_id": 123},
        )

    assert "Invalid arguments for tool `get_user_profile` at `user_id`" in exc_info.value.message
    assert "123" in exc_info.value.message
    assert "not of type" in exc_info.value.message
    assert "string" in exc_info.value.message


def test_validate_tool_arguments_rejects_invalid_enum_value() -> None:
    with pytest.raises(ToolInputValidationError) as exc_info:
        validate_tool_arguments(
            tool_name="set_status",
            tool_spec=_tool_spec(
                {
                    "type": "object",
                    "properties": {"status": {"type": "string", "enum": ["open", "closed"]}},
                }
            ),
            arguments={"status": "blue"},
        )

    assert "Invalid arguments for tool `set_status` at `status`" in exc_info.value.message
    assert "blue" in exc_info.value.message
    assert "open" in exc_info.value.message
    assert "closed" in exc_info.value.message


def test_validate_tool_arguments_rejects_unexpected_extra_arguments() -> None:
    with pytest.raises(ToolInputValidationError) as exc_info:
        validate_tool_arguments(
            tool_name="get_user_profile",
            tool_spec=_tool_spec(
                {
                    "type": "object",
                    "properties": {"user_id": {"type": "string"}},
                    "additionalProperties": False,
                }
            ),
            arguments={"user_id": "usr_ada_01", "unexpected": "field"},
        )

    assert "Invalid arguments for tool `get_user_profile`" in exc_info.value.message
    assert "Additional properties" in exc_info.value.message
    assert "unexpected" in exc_info.value.message


def test_validate_tool_arguments_passes_through_when_schema_missing() -> None:
    arguments = {"anything": 123}

    assert (
        validate_tool_arguments(
            tool_name="schema_free",
            tool_spec=_tool_spec(),
            arguments=arguments,
        )
        is arguments
    )


def test_validate_tool_arguments_reports_invalid_tool_schema() -> None:
    with pytest.raises(ToolSchemaValidationError) as exc_info:
        validate_tool_arguments(
            tool_name="bad_schema",
            tool_spec=_tool_spec(
                {
                    "type": "object",
                    "properties": {"value": {"type": "not-a-json-schema-type"}},
                }
            ),
            arguments={"value": "x"},
        )

    assert exc_info.value.error_type == "invalid_tool_schema"
    assert exc_info.value.message.startswith("Invalid schema for tool `bad_schema`:")
