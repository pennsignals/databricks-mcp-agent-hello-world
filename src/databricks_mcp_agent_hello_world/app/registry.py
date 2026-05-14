from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..tools.local import LocalToolDefinition
from . import tools as app_tools

# TEMPLATE_CUSTOMIZE_HERE
# Replace these example app registry entries with your real local tools.
TOOL_DEFINITIONS: dict[str, LocalToolDefinition] = {
    "get_user_profile": LocalToolDefinition(
        name="get_user_profile",
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
        fn=app_tools.get_user_profile,
    ),
    "search_onboarding_docs": LocalToolDefinition(
        name="search_onboarding_docs",
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
        fn=app_tools.search_onboarding_docs,
    ),
    "get_workspace_setting": LocalToolDefinition(
        name="get_workspace_setting",
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
        fn=app_tools.get_workspace_setting,
    ),
    "list_recent_job_runs": LocalToolDefinition(
        name="list_recent_job_runs",
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
        fn=app_tools.list_recent_job_runs,
    ),
    "create_support_ticket": LocalToolDefinition(
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
}


def list_local_tools() -> list[LocalToolDefinition]:
    _validate_unique_names(TOOL_DEFINITIONS.values())
    return list(TOOL_DEFINITIONS.values())


def get_tool_function(name: str) -> Callable[..., Any]:
    return TOOL_DEFINITIONS[name].fn


def _validate_unique_names(definitions) -> None:
    names = [definition.name for definition in definitions]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"Local tool names must be unique: {', '.join(duplicates)}")
