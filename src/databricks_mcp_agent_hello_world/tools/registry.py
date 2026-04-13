from __future__ import annotations

from typing import Any, Callable

from ..models import ToolSpec
from . import builtin


class LocalToolDefinition:
    def __init__(self, spec: ToolSpec, fn: Callable[..., dict[str, Any]]):
        self.spec = spec
        self.fn = fn


TOOL_DEFINITIONS: dict[str, LocalToolDefinition] = {
    "greet_user": LocalToolDefinition(
        spec=ToolSpec(
            tool_name="greet_user",
            description="Return a short friendly greeting for a named person.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Person name to greet.",
                    }
                },
                "required": ["name"],
            },
            provider_type="local_python",
            provider_id="builtin_tools",
        ),
        fn=builtin.greet_user,
    ),
    "search_demo_handbook": LocalToolDefinition(
        spec=ToolSpec(
            tool_name="search_demo_handbook",
            description="Search the tiny local handbook for beginner setup tips.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search text for the local handbook.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of handbook entries to return.",
                        "default": 1,
                    },
                },
                "required": ["query"],
            },
            provider_type="local_python",
            provider_id="builtin_tools",
        ),
        fn=builtin.search_demo_handbook,
    ),
    "get_demo_setting": LocalToolDefinition(
        spec=ToolSpec(
            tool_name="get_demo_setting",
            description="Look up one hardcoded demo setting value.",
            input_schema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Setting key to look up.",
                    }
                },
                "required": ["key"],
            },
            provider_type="local_python",
            provider_id="builtin_tools",
        ),
        fn=builtin.get_demo_setting,
    ),
    "tell_demo_joke": LocalToolDefinition(
        spec=ToolSpec(
            tool_name="tell_demo_joke",
            description=(
                "Tell a harmless joke. This is intentionally not useful for the hello-world setup task."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Topic to use as joke inspiration.",
                    }
                },
                "required": ["topic"],
            },
            provider_type="local_python",
            provider_id="builtin_tools",
        ),
        fn=builtin.tell_demo_joke,
    ),
}


def list_tool_specs() -> list[ToolSpec]:
    return [definition.spec for definition in TOOL_DEFINITIONS.values()]


def get_tool_function(name: str):
    return TOOL_DEFINITIONS[name].fn
