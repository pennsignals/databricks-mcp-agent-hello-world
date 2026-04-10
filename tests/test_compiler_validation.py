from types import SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world.models import FilterDecision, ToolSpec
from databricks_mcp_agent_hello_world.profiles.compiler import ToolProfileCompiler


def _tool(name: str) -> ToolSpec:
    return ToolSpec(
        tool_name=name,
        description=f"{name} description",
        input_schema={"type": "object", "properties": {}, "required": []},
        provider_type="local_python",
        provider_id="builtin_tools",
    )


def test_validate_decision_rejects_missing_tool() -> None:
    compiler = ToolProfileCompiler.__new__(ToolProfileCompiler)
    compiler.settings = SimpleNamespace(max_allowed_tools=2)
    decision = FilterDecision(
        allowed_tools=["one"],
        disallowed_tools=[],
        tool_justifications={"one": "needed"},
    )

    with pytest.raises(ValueError, match="exactly once"):
        compiler._validate_decision([_tool("one"), _tool("two")], decision)


def test_validate_decision_rejects_unknown_or_duplicate_tools() -> None:
    compiler = ToolProfileCompiler.__new__(ToolProfileCompiler)
    compiler.settings = SimpleNamespace(max_allowed_tools=2)
    decision = FilterDecision(
        allowed_tools=["one", "one"],
        disallowed_tools=["three"],
        tool_justifications={"one": "needed", "two": "not needed"},
    )

    with pytest.raises(ValueError):
        compiler._validate_decision([_tool("one"), _tool("two")], decision)
