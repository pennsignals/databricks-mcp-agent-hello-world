from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator, SchemaError, ValidationError


class ToolValidationError(ValueError):
    error_type: str

    def __init__(self, tool_name: str, message: str):
        super().__init__(message)
        self.tool_name = tool_name
        self.message = message


class ToolInputValidationError(ToolValidationError):
    error_type = "invalid_tool_arguments"


class ToolSchemaValidationError(ToolValidationError):
    error_type = "invalid_tool_schema"


def get_tool_parameters_schema(tool_spec: dict[str, Any]) -> dict[str, Any] | None:
    function = tool_spec.get("function")
    if not isinstance(function, dict):
        return None

    parameters = function.get("parameters")
    if not isinstance(parameters, dict):
        return None

    return parameters


def validate_tool_arguments(
    *,
    tool_name: str,
    tool_spec: dict[str, Any],
    arguments: dict[str, Any],
) -> dict[str, Any]:
    schema = get_tool_parameters_schema(tool_spec)

    if schema is None:
        return arguments

    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(arguments)
    except SchemaError as exc:
        raise ToolSchemaValidationError(
            tool_name=tool_name,
            message=f"Invalid schema for tool `{tool_name}`: {exc.message}",
        ) from exc
    except ValidationError as exc:
        path = ".".join(str(part) for part in exc.path)
        location = f" at `{path}`" if path else ""
        raise ToolInputValidationError(
            tool_name=tool_name,
            message=f"Invalid arguments for tool `{tool_name}`{location}: {exc.message}",
        ) from exc

    return arguments
