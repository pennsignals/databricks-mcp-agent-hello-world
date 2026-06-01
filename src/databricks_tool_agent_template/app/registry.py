from __future__ import annotations

from databricks_tool_agent_template.app.tools import (
    create_support_ticket,
    lookup_customer,
)
from databricks_tool_agent_template.tools.local import (
    LocalToolDefinition,
    build_local_tool_registry,
)
from databricks_tool_agent_template.tools.runtime import RuntimeTool

# TEMPLATE_CUSTOMIZE_HERE
# Replace these example app registry entries with your real local tools.
LOCAL_TOOL_DEFINITIONS: tuple[LocalToolDefinition, ...] = (
    LocalToolDefinition(
        name="lookup_customer",
        description=(
            "Fetch a demo customer's account details by customer_id, including "
            "customer name, tier, and region. Use this when a task needs factual "
            "customer account context."
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
            "Create a demo support-ticket record. Use only when the task explicitly "
            "asks to create, draft, or file a support ticket."
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
