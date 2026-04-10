from __future__ import annotations

from typing import Any, Callable

from ..models import ToolSpec
from . import builtin


class LocalToolDefinition:
    def __init__(self, spec: ToolSpec, fn: Callable[..., dict[str, Any]]):
        self.spec = spec
        self.fn = fn


TOOL_DEFINITIONS: dict[str, LocalToolDefinition] = {
    "search_incident_kb": LocalToolDefinition(
        spec=ToolSpec(
            tool_name="search_incident_kb",
            description=(
                "Search the incident knowledge base for relevant prior incidents, "
                "runbooks, and operational guidance."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural-language retrieval query."},
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return.",
                        "default": 3,
                    },
                },
                "required": ["query"],
            },
            provider_type="local_python",
            provider_id="builtin_tools",
            tags=["rag", "incidents", "runbooks"],
        ),
        fn=builtin.search_incident_kb,
    ),
    "search_runbook_sections": LocalToolDefinition(
        spec=ToolSpec(
            tool_name="search_runbook_sections",
            description="Retrieve runbook sections relevant to a service and optional symptom.",
            input_schema={
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Logical service name such as billing-api.",
                    },
                    "symptom": {
                        "type": "string",
                        "description": "Optional symptom or clue to filter runbook sections.",
                    },
                },
                "required": ["service_name"],
            },
            provider_type="local_python",
            provider_id="builtin_tools",
            tags=["rag", "runbooks", "service"],
        ),
        fn=builtin.search_runbook_sections,
    ),
    "lookup_customer_summary": LocalToolDefinition(
        spec=ToolSpec(
            tool_name="lookup_customer_summary",
            description="Retrieve a structured customer summary for a known customer identifier.",
            input_schema={
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "description": "Customer identifier such as CUST-12345.",
                    },
                },
                "required": ["customer_id"],
            },
            provider_type="local_python",
            provider_id="builtin_tools",
            tags=["structured_lookup", "customer"],
        ),
        fn=builtin.lookup_customer_summary,
    ),
    "lookup_service_dependencies": LocalToolDefinition(
        spec=ToolSpec(
            tool_name="lookup_service_dependencies",
            description=(
                "Return the structured downstream dependency list "
                "for a known service name."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Logical service name, such as billing-api.",
                    },
                },
                "required": ["service_name"],
            },
            provider_type="local_python",
            provider_id="builtin_tools",
            tags=["structured_lookup", "service", "dependencies"],
        ),
        fn=builtin.lookup_service_dependencies,
    ),
    "get_open_incidents_for_service": LocalToolDefinition(
        spec=ToolSpec(
            tool_name="get_open_incidents_for_service",
            description="Return currently open incidents for a specific service name.",
            input_schema={
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Logical service name, such as billing-api.",
                    },
                },
                "required": ["service_name"],
            },
            provider_type="local_python",
            provider_id="builtin_tools",
            tags=["structured_lookup", "incidents", "service"],
        ),
        fn=builtin.get_open_incidents_for_service,
    ),
}


def list_tool_specs() -> list[ToolSpec]:
    return [definition.spec for definition in TOOL_DEFINITIONS.values()]


def get_tool_function(name: str):
    return TOOL_DEFINITIONS[name].fn
