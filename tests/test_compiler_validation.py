from types import SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world.models import AgentTaskRequest, FilterDecision, ToolSpec
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


class StubProvider:
    provider_id = "builtin_tools"

    def __init__(self, tools):
        self._tools = tools

    def list_tools(self):
        return self._tools

    def inventory_hash(self):
        return "hash-1"


class StubRepo:
    def __init__(self):
        self.saved = None

    def save(self, profile):
        self.saved = profile


class StubLLM:
    def complete_json(self, *args, **kwargs):  # pragma: no cover - should not be called
        raise AssertionError("hello_world_demo compilation should not call the LLM")

    def complete_text(self, *args, **kwargs):  # pragma: no cover - should not be called
        raise AssertionError("hello_world_demo compilation should not call the LLM")


def test_compile_hello_world_profile_is_deterministic() -> None:
    compiler = ToolProfileCompiler.__new__(ToolProfileCompiler)
    compiler.settings = SimpleNamespace(
        active_profile_name="default",
        provider_type="local_python",
        llm_endpoint_name="endpoint-a",
        max_allowed_tools=4,
    )
    compiler.provider = StubProvider(
        [
            _tool("greet_user"),
            _tool("search_demo_handbook"),
            _tool("get_demo_setting"),
            _tool("tell_demo_joke"),
        ]
    )
    compiler.repo = StubRepo()
    compiler.llm = StubLLM()

    profile = compiler.compile(
        AgentTaskRequest(
            task_name="hello_world_demo",
            instructions="Write the hello-world report.",
            payload={
                "name": "Ada",
                "handbook_query": "local setup tip",
                "setting_key": "runtime_target",
            },
        )
    )

    assert profile.allowed_tools == [
        "greet_user",
        "search_demo_handbook",
        "get_demo_setting",
    ]
    assert profile.disallowed_tools == ["tell_demo_joke"]
    assert "temperature=0" in profile.selection_policy
    assert "strict JSON" in profile.selection_policy
    assert compiler.repo.saved == profile
    assert profile.audit_report_text.startswith("{")
