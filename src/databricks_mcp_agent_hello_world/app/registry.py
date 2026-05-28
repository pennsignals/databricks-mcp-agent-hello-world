from __future__ import annotations

from databricks_mcp_agent_hello_world.app.tools import (
    create_support_ticket,
    lookup_customer,
)
from databricks_mcp_agent_hello_world.tools.local import (
    LocalToolDefinition,
    build_local_tool_registry,
)
from databricks_mcp_agent_hello_world.tools.runtime import RuntimeTool

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
        handler=lookup_customer,
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
        handler=create_support_ticket,
    ),
)


def build_app_local_tool_registry() -> dict[str, RuntimeTool]:
    return build_local_tool_registry(LOCAL_TOOL_DEFINITIONS)
