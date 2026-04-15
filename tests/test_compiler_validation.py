import json
from types import SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world.models import (
    AgentTaskRequest,
    FilterDecision,
    ToolProfile,
    ToolSpec,
)
from databricks_mcp_agent_hello_world.profiles.compiler import ToolProfileCompiler


def _tool(name: str) -> ToolSpec:
    return ToolSpec(
        tool_name=name,
        description=f"{name} description",
        input_schema={"type": "object", "properties": {}, "required": []},
        provider_type="local_python",
        provider_id="builtin_tools",
    )


def _task(
    task_name: str = "task-a",
    *,
    instructions: str = "Use the tools carefully.",
    payload: dict[str, object] | None = None,
    run_id: str = "run-1",
) -> AgentTaskRequest:
    return AgentTaskRequest(
        task_name=task_name,
        instructions=instructions,
        payload=payload or {"topic": "demo"},
        run_id=run_id,
    )


def _settings(*, max_allowed_tools: int = 4) -> SimpleNamespace:
    return SimpleNamespace(
        active_profile_name="default",
        provider_type="local_python",
        llm_endpoint_name="endpoint-a",
        max_allowed_tools=max_allowed_tools,
        prompts=SimpleNamespace(
            filter_prompt="filter prompt",
            audit_prompt="audit prompt",
        ),
    )


def _profile(
    version: str,
    *,
    inventory_hash: str = "hash-1",
    compile_task_hash: str = "task-hash",
    prompt_version: str = "v1",
    profile_name: str = "default",
) -> ToolProfile:
    profile = ToolProfile(
        profile_name=profile_name,
        profile_version=version,
        inventory_hash=inventory_hash,
        provider_type="local_python",
        llm_endpoint_name="endpoint-a",
        prompt_version=prompt_version,
        compile_task_name="task-a",
        compile_task_hash=compile_task_hash,
        compile_task_summary="task-a: Use the tools carefully.",
        discovered_tools=[_tool("alpha"), _tool("beta")],
        allowed_tools=["alpha"],
        disallowed_tools=["beta"],
        justifications={"alpha": "needed", "beta": "not needed"},
        audit_report_text="audit",
        selection_policy="small allowlist",
    )
    return profile


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
    def __init__(self, decision=None, audit_text="audit"):
        self.decision = decision or {
            "allowed_tools": ["alpha"],
            "disallowed_tools": ["beta"],
            "tool_justifications": {
                "alpha": "needed",
                "beta": "not needed",
            },
            "summary_reasoning": "smallest useful subset",
        }
        self.audit_text = audit_text
        self.complete_json_calls = []
        self.complete_text_calls = []

    def complete_json(self, system_prompt, user_prompt):
        self.complete_json_calls.append((system_prompt, user_prompt))
        return self.decision

    def complete_text(self, system_prompt, user_prompt):
        self.complete_text_calls.append((system_prompt, user_prompt))
        return self.audit_text


def test_compile_requires_task_argument() -> None:
    compiler = ToolProfileCompiler.__new__(ToolProfileCompiler)

    with pytest.raises(TypeError):
        compiler.compile()  # type: ignore[misc]


def test_validate_decision_rejects_missing_tool() -> None:
    compiler = ToolProfileCompiler.__new__(ToolProfileCompiler)
    compiler.settings = _settings(max_allowed_tools=2)
    decision = FilterDecision(
        allowed_tools=["one"],
        disallowed_tools=[],
        tool_justifications={"one": "needed"},
    )

    with pytest.raises(ValueError, match="exactly once"):
        compiler._validate_decision([_tool("one"), _tool("two")], decision)


def test_validate_decision_rejects_unknown_or_duplicate_tools() -> None:
    compiler = ToolProfileCompiler.__new__(ToolProfileCompiler)
    compiler.settings = _settings(max_allowed_tools=2)
    decision = FilterDecision(
        allowed_tools=["one", "one"],
        disallowed_tools=["three"],
        tool_justifications={"one": "needed", "two": "not needed"},
    )

    with pytest.raises(ValueError):
        compiler._validate_decision([_tool("one"), _tool("two")], decision)


def test_filter_tools_prompt_includes_task_context() -> None:
    compiler = ToolProfileCompiler.__new__(ToolProfileCompiler)
    compiler.settings = _settings(max_allowed_tools=2)
    compiler.llm = StubLLM(
        decision={
            "allowed_tools": ["alpha"],
            "disallowed_tools": ["beta"],
            "tool_justifications": {"alpha": "needed", "beta": "not needed"},
            "summary_reasoning": "smallest useful subset",
        }
    )
    task = _task(payload={"topic": "prompt-check"})

    decision = compiler._filter_tools(task, [_tool("alpha"), _tool("beta")])

    assert decision.allowed_tools == ["alpha"]
    assert compiler.llm.complete_json_calls[0][0] == "filter prompt"
    prompt = compiler.llm.complete_json_calls[0][1]
    payload = json.loads(prompt)
    assert payload["task_name"] == task.task_name
    assert payload["instructions"] == task.instructions
    assert payload["payload"] == task.payload
    assert payload["max_allowed_tools"] == 2
    assert payload["selection_policy"]
    assert payload["discovered_tools"][0]["tool_name"] == "alpha"
    assert payload["discovered_tools"][1]["tool_name"] == "beta"


def test_compile_task_hash_changes_with_task_content() -> None:
    compiler = ToolProfileCompiler.__new__(ToolProfileCompiler)
    task_a = _task(instructions="Use the tools carefully.")
    task_b = _task(instructions="Use the tools differently.")
    task_c = _task(payload={"topic": "changed"})

    assert compiler._compile_task_hash(task_a) == compiler._compile_task_hash(task_a)
    assert compiler._compile_task_hash(task_a) != compiler._compile_task_hash(task_b)
    assert compiler._compile_task_hash(task_a) != compiler._compile_task_hash(task_c)


def test_compile_task_summary_truncates_to_240_chars() -> None:
    compiler = ToolProfileCompiler.__new__(ToolProfileCompiler)
    task = _task(instructions="x" * 300)

    summary = compiler._compile_task_summary(task)

    assert len(summary) == 240
    assert summary == f"{task.task_name}: {task.instructions}"[:240]


def test_compile_reuses_existing_profile_only_when_identity_matches() -> None:
    task = _task()
    active_profile = _profile(
        "existing-version",
        inventory_hash="hash-1",
        compile_task_hash=ToolProfileCompiler._compile_task_hash(task),
        prompt_version="v1",
    )
    compiler = ToolProfileCompiler.__new__(ToolProfileCompiler)
    compiler.settings = _settings()
    compiler.provider = StubProvider([_tool("alpha"), _tool("beta")], inventory_hash="hash-1")
    compiler.repo = StubRepo(active_profile=active_profile)
    compiler.llm = StubLLM()

    result = compiler.compile(task)

    assert result.reused_existing is True
    assert result.profile is active_profile
    assert compiler.repo.saved is None
    assert compiler.llm.complete_json_calls == []
    assert compiler.llm.complete_text_calls == []
    assert result.profile.compile_task_name == task.task_name
    assert result.profile.compile_task_hash == ToolProfileCompiler._compile_task_hash(task)


def test_compile_recompiles_when_task_hash_differs() -> None:
    task = _task()
    active_profile = _profile(
        "existing-version",
        inventory_hash="hash-1",
        compile_task_hash="different-task-hash",
        prompt_version="v1",
    )
    compiler = ToolProfileCompiler.__new__(ToolProfileCompiler)
    compiler.settings = _settings()
    compiler.provider = StubProvider([_tool("alpha"), _tool("beta")], inventory_hash="hash-1")
    compiler.repo = StubRepo(active_profile=active_profile)
    compiler.llm = StubLLM()

    result = compiler.compile(task)

    assert result.reused_existing is False
    assert compiler.repo.saved is result.profile
    assert compiler.llm.complete_json_calls
    assert compiler.llm.complete_text_calls
    assert result.profile.compile_task_name == task.task_name
    assert result.profile.compile_task_hash == ToolProfileCompiler._compile_task_hash(task)
    assert result.profile.compile_task_summary == ToolProfileCompiler._compile_task_summary(task)


def test_compile_recompiles_when_prompt_version_differs() -> None:
    task = _task()
    active_profile = _profile(
        "existing-version",
        inventory_hash="hash-1",
        compile_task_hash=ToolProfileCompiler._compile_task_hash(task),
        prompt_version="older-version",
    )
    compiler = ToolProfileCompiler.__new__(ToolProfileCompiler)
    compiler.settings = _settings()
    compiler.provider = StubProvider([_tool("alpha"), _tool("beta")], inventory_hash="hash-1")
    compiler.repo = StubRepo(active_profile=active_profile)
    compiler.llm = StubLLM()

    result = compiler.compile(task)

    assert result.reused_existing is False
    assert compiler.repo.saved is result.profile
