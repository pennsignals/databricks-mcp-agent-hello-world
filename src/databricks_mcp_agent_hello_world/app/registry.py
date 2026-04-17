from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from . import tools as app_tools


@dataclass(frozen=True)
class AuthoredToolDefinition:
    tool_name: str
    description: str
    input_schema: dict[str, Any]
    capability_tags: list[str]
    side_effect_level: Literal["read_only", "write"]
    data_domains: list[str]
    example_uses: list[str]
    fn: Callable[..., dict[str, Any]]


# TEMPLATE_CUSTOMIZE_HERE
# Replace these example app registry entries with your real tool metadata.
# Keep registry metadata neutral and capability-based so the runtime model can
# reason over the full tool inventory without task-specific routing hints.
TOOL_DEFINITIONS: dict[str, AuthoredToolDefinition] = {
    "get_user_profile": AuthoredToolDefinition(
        tool_name="get_user_profile",
        description=(
            "Fetch a user's information by user_id. Use this when a task "
            "needs a user's display name, team, role, or other identity details."
        ),
        input_schema={
            "type": "object",
            "properties": {"user_id": {"type": "string"}},
            "required": ["user_id"],
            "additionalProperties": False,
        },
        capability_tags=["identity", "user_lookup"],
        side_effect_level="read_only",
        data_domains=["user"],
        example_uses=[
            "Look up the display name for a user",
            "Retrieve user details for an onboarding brief",
        ],
        fn=app_tools.get_user_profile,
    ),
    "search_onboarding_docs": AuthoredToolDefinition(
        tool_name="search_onboarding_docs",
        description=(
            "Search onboarding and setup documentation by keyword. Use this "
            "when a task needs setup guidance, onboarding tips, or repository "
            "workflow guidance."
        ),
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
        capability_tags=["docs", "onboarding", "search"],
        side_effect_level="read_only",
        data_domains=["documentation"],
        example_uses=[
            "Find a local development setup tip",
            "Search onboarding docs for repository workflow guidance",
        ],
        fn=app_tools.search_onboarding_docs,
    ),
    "get_workspace_setting": AuthoredToolDefinition(
        tool_name="get_workspace_setting",
        description=(
            "Fetch a named workspace setting. Use this when a task needs "
            "current configuration values such as runtime target, workspace "
            "region, or storage settings."
        ),
        input_schema={
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
            "additionalProperties": False,
        },
        capability_tags=["config", "settings"],
        side_effect_level="read_only",
        data_domains=["workspace_config"],
        example_uses=[
            "Retrieve the runtime target",
            "Look up the workspace region",
        ],
        fn=app_tools.get_workspace_setting,
    ),
    "list_recent_job_runs": AuthoredToolDefinition(
        tool_name="list_recent_job_runs",
        description=(
            "List recent job runs and their summary notes. Use this when a "
            "task needs a recent operational update or recent job execution "
            "context."
        ),
        input_schema={
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1}},
            "additionalProperties": False,
        },
        capability_tags=["jobs", "operations", "status"],
        side_effect_level="read_only",
        data_domains=["operations"],
        example_uses=[
            "Fetch a recent operational note",
            "Review recent job run summaries",
        ],
        fn=app_tools.list_recent_job_runs,
    ),
    "create_support_ticket": AuthoredToolDefinition(
        tool_name="create_support_ticket",
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
        capability_tags=["support", "ticketing"],
        side_effect_level="write",
        data_domains=["support"],
        example_uses=[
            "File a support ticket for an incident",
            "Create a support request for a broken workflow",
        ],
        fn=app_tools.create_support_ticket,
    ),
}


def list_authored_tools() -> list[AuthoredToolDefinition]:
    return list(TOOL_DEFINITIONS.values())


def get_tool_function(name: str) -> Callable[..., dict[str, Any]]:
    return TOOL_DEFINITIONS[name].fn
