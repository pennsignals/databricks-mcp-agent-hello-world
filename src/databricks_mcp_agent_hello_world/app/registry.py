from __future__ import annotations

from collections.abc import Iterable

from ..tools.local import LocalToolDefinition
from . import tools as app_tools

# TEMPLATE_CUSTOMIZE_HERE
# Replace these example app registry entries with your real local tools.
LOCAL_TOOL_DEFINITIONS: tuple[LocalToolDefinition, ...] = (
    LocalToolDefinition(
        name="lookup_customer",
        description=(
            "Fetch a demo customer's account details by customer_id. Use this "
            "when a task needs the customer's name, tier, or region."
        ),
        input_schema={
            "type": "object",
            "properties": {"customer_id": {"type": "string"}},
            "required": ["customer_id"],
            "additionalProperties": False,
        },
        fn=app_tools.lookup_customer,
    ),
    LocalToolDefinition(
        name="create_support_ticket",
        description=(
            "Create a support ticket with a short summary and severity. Use "
            "this only when the task explicitly asks to create or file a "
            "support request."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "severity": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["summary"],
            "additionalProperties": False,
        },
        fn=app_tools.create_support_ticket,
    ),
)


def build_local_tool_registry(
    definitions: Iterable[LocalToolDefinition] = LOCAL_TOOL_DEFINITIONS,
) -> dict[str, LocalToolDefinition]:
    registry: dict[str, LocalToolDefinition] = {}

    for definition in definitions:
        if not definition.name.strip():
            raise ValueError("Local tool definition has empty name.")

        if not callable(definition.fn):
            raise ValueError(f"Local tool `{definition.name}` has non-callable fn.")

        if definition.name in registry:
            raise ValueError(f"Duplicate local tool name: {definition.name}")

        registry[definition.name] = definition

    return registry


LOCAL_TOOL_REGISTRY = build_local_tool_registry()


def list_local_tools() -> list[LocalToolDefinition]:
    return list(LOCAL_TOOL_DEFINITIONS)
