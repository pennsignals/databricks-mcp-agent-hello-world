from __future__ import annotations

from typing import Any, Callable

from ..demo import tools as demo_tools
from ..models import ToolSpec


class LocalToolDefinition:
    def __init__(self, spec: ToolSpec, fn: Callable[..., dict[str, Any]]):
        self.spec = spec
        self.fn = fn


# TEMPLATE_CUSTOMIZE_HERE
# Replace these demo registry entries with your real tool metadata and keep the ToolSpec fields populated.
# Keep registry metadata neutral and capability-based so the compiler model can
# reason over the full tool inventory without task-specific routing hints.
TOOL_DEFINITIONS: dict[str, LocalToolDefinition] = {
    "get_user_profile": LocalToolDefinition(
        spec=ToolSpec(
            tool_name="get_user_profile",
            description="Fetch a user's profile information by user_id. Use this when a task needs a user's display name, team, role, or other profile details.",
            input_schema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"}
                },
                "required": ["user_id"],
                "additionalProperties": False,
            },
            provider_type="local_python",
            provider_id="builtin_tools",
            capability_tags=["profile", "identity"],
            side_effect_level="read_only",
            data_domains=["user"],
            example_uses=[
                "Look up the display name for a user",
                "Retrieve profile details for an onboarding brief",
            ],
        ),
        fn=demo_tools.get_user_profile,
    ),
    "search_onboarding_docs": LocalToolDefinition(
        spec=ToolSpec(
            tool_name="search_onboarding_docs",
            description="Search onboarding and setup documentation by keyword. Use this when a task needs setup guidance, onboarding tips, or repository workflow guidance.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {
                        "type": "integer",
                        "minimum": 1,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            provider_type="local_python",
            provider_id="builtin_tools",
            capability_tags=["search", "docs", "onboarding"],
            side_effect_level="read_only",
            data_domains=["documentation"],
            example_uses=[
                "Find a local development setup tip",
                "Search onboarding docs for repository workflow guidance",
            ],
        ),
        fn=demo_tools.search_onboarding_docs,
    ),
    "get_workspace_setting": LocalToolDefinition(
        spec=ToolSpec(
            tool_name="get_workspace_setting",
            description="Fetch a named workspace setting. Use this when a task needs current configuration values such as runtime target, workspace region, or storage settings.",
            input_schema={
                "type": "object",
                "properties": {
                    "key": {"type": "string"}
                },
                "required": ["key"],
                "additionalProperties": False,
            },
            provider_type="local_python",
            provider_id="builtin_tools",
            capability_tags=["config", "settings"],
            side_effect_level="read_only",
            data_domains=["workspace_config"],
            example_uses=[
                "Retrieve the runtime target",
                "Look up the workspace region",
            ],
        ),
        fn=demo_tools.get_workspace_setting,
    ),
    "list_recent_job_runs": LocalToolDefinition(
        spec=ToolSpec(
            tool_name="list_recent_job_runs",
            description="List recent job runs and their summary notes. Use this when a task needs a recent operational update or recent job execution context.",
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1}
                },
                "additionalProperties": False,
            },
            provider_type="local_python",
            provider_id="builtin_tools",
            capability_tags=["operations", "jobs", "status"],
            side_effect_level="read_only",
            data_domains=["operations"],
            example_uses=[
                "Fetch a recent operational note",
                "Review recent job run summaries",
            ],
        ),
        fn=demo_tools.list_recent_job_runs,
    ),
    "create_support_ticket": LocalToolDefinition(
        spec=ToolSpec(
            tool_name="create_support_ticket",
            description="Create a support ticket with a short summary and severity. Use this only when the task explicitly asks to create or file a support request.",
            input_schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                },
                "required": ["summary"],
                "additionalProperties": False,
            },
            provider_type="local_python",
            provider_id="builtin_tools",
            capability_tags=["support", "ticketing"],
            side_effect_level="write",
            data_domains=["support"],
            example_uses=[
                "File a support ticket for an incident",
                "Create a support request for a broken workflow",
            ],
        ),
        fn=demo_tools.create_support_ticket,
    ),
}


def list_tool_specs() -> list[ToolSpec]:
    return [definition.spec for definition in TOOL_DEFINITIONS.values()]


def get_tool_function(name: str):
    return TOOL_DEFINITIONS[name].fn
