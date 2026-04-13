from types import SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world.models import AgentTaskRequest, FilterDecision, ToolProfile, ToolSpec
from databricks_mcp_agent_hello_world.profiles.compiler import ToolProfileCompiler


def _tool(name: str) -> ToolSpec:
    return ToolSpec(
        tool_name=name,
        description=f"{name} description",
        input_schema={"type": "object", "properties": {}, "required": []},
        provider_type="local_python",
        provider_id="builtin_tools",
    )


def _profile(version: str, inventory_hash: str = "hash-1") -> ToolProfile:
    return ToolProfile(
        profile_name="default",
        profile_version=version,
        inventory_hash=inventory_hash,
        provider_type="local_python",
        llm_endpoint_name="endpoint-a",
        prompt_version="v1",
        discovered_tools=[
            _tool("greet_user"),
            _tool("search_demo_handbook"),
            _tool("get_demo_setting"),
            _tool("tell_demo_joke"),
        ],
        allowed_tools=["greet_user", "search_demo_handbook", "get_demo_setting"],
        disallowed_tools=["tell_demo_joke"],
        justifications={
            "greet_user": "needed",
            "search_demo_handbook": "needed",
            "get_demo_setting": "needed",
            "tell_demo_joke": "not needed",
        },
        audit_report_text="audit",
        selection_policy="small allowlist",
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
    def __init__(self, tools, inventory_hash="hash-1"):
        self._tools = tools
        self._inventory_hash = inventory_hash

    def list_tools(self):
        return self._tools

    def inventory_hash(self):
        return self._inventory_hash


class StubRepo:
    def __init__(self, active_profile=None):
        self.active_profile = active_profile
        self.saved = None

    def load_active(self, profile_name):
        return self.active_profile

    def save(self, profile):
        self.saved = profile


class StubLLM:
    def complete_json(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("hello_world_demo compilation should not call the LLM")

    def complete_text(self, *args, **kwargs):  # pragma: no cover
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

    result = compiler.compile(
        AgentTaskRequest(
            task_name="hello_world_demo",
            instructions="Write the hello-world report.",
            payload={"name": "Ada"},
        )
    )

    assert result.reused_existing is False
    assert result.profile.allowed_tools == [
        "greet_user",
        "search_demo_handbook",
        "get_demo_setting",
    ]
    assert result.profile.disallowed_tools == ["tell_demo_joke"]
    assert "temperature=0" in result.profile.selection_policy
    assert compiler.repo.saved == result.profile


def test_compile_reuses_existing_profile_when_inventory_matches() -> None:
    active_profile = _profile("existing-version", inventory_hash="hash-1")
    compiler = ToolProfileCompiler.__new__(ToolProfileCompiler)
    compiler.settings = SimpleNamespace(
        active_profile_name="default",
        provider_type="local_python",
        llm_endpoint_name="endpoint-a",
        max_allowed_tools=4,
    )
    compiler.provider = StubProvider(active_profile.discovered_tools, inventory_hash="hash-1")
    compiler.repo = StubRepo(active_profile=active_profile)
    compiler.llm = StubLLM()

    result = compiler.compile(
        AgentTaskRequest(task_name="hello_world_demo", instructions="Run", payload={})
    )

    assert result.reused_existing is True
    assert result.profile == active_profile
    assert compiler.repo.saved is None


def test_force_refresh_creates_new_profile_version() -> None:
    active_profile = _profile("existing-version", inventory_hash="hash-1")
    compiler = ToolProfileCompiler.__new__(ToolProfileCompiler)
    compiler.settings = SimpleNamespace(
        active_profile_name="default",
        provider_type="local_python",
        llm_endpoint_name="endpoint-a",
        max_allowed_tools=4,
    )
    compiler.provider = StubProvider(active_profile.discovered_tools, inventory_hash="hash-1")
    compiler.repo = StubRepo(active_profile=active_profile)
    compiler.llm = StubLLM()

    result = compiler.compile(
        AgentTaskRequest(task_name="hello_world_demo", instructions="Run", payload={}),
        force_refresh=True,
    )

    assert result.reused_existing is False
    assert result.profile.profile_version != active_profile.profile_version
    assert compiler.repo.saved == result.profile
