from pathlib import Path
from types import SimpleNamespace

from databricks_mcp_agent_hello_world.models import (
    AgentTaskRequest,
    ToolProfile,
    ToolResult,
    ToolSpec,
)
from databricks_mcp_agent_hello_world.runner.agent_runner import AgentRunner


class StubProfileRepo:
    def __init__(self, profile: ToolProfile):
        self.profile = profile

    def load_active(self) -> ToolProfile:
        return self.profile


class StubExecutor:
    def __init__(self) -> None:
        self.calls = []

    def call_tool(self, tool_call):
        self.calls.append(tool_call)
        return ToolResult(
            tool_name=tool_call.tool_name,
            status="ok",
            content={"echo": tool_call.arguments},
            metadata={},
        )


class StubWriter:
    def __init__(self) -> None:
        self.run_records = []
        self.output_records = []

    def write_run_record(self, record) -> None:
        self.run_records.append(record)

    def write_output_record(self, record) -> None:
        self.output_records.append(record)


class StubLLM:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    def tool_step(self, messages, tools):
        response = self.responses[self.calls]
        self.calls += 1
        return response


def _tool(name: str) -> ToolSpec:
    return ToolSpec(
        tool_name=name,
        description=f"{name} description",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": [],
        },
        provider_type="local_python",
        provider_id="builtin_tools",
    )


def _profile() -> ToolProfile:
    return ToolProfile(
        profile_name="default",
        profile_version="v1",
        inventory_hash="abc123",
        provider_type="local_python",
        provider_id="builtin_tools",
        llm_endpoint_name="endpoint-a",
        prompt_version="v1",
        discovered_tools=[_tool("allowed_tool"), _tool("blocked_tool")],
        allowed_tools=["allowed_tool"],
        disallowed_tools=["blocked_tool"],
        justifications={"allowed_tool": "needed", "blocked_tool": "not needed"},
        audit_report_text="audit",
        selection_policy="small allowlist",
    )


def _response(content: str | None = None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _tool_call(name: str, arguments: str, call_id: str = "call-1"):
    function = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(id=call_id, function=function)


def test_agent_runner_blocks_disallowed_tool(tmp_path: Path) -> None:
    runner = AgentRunner.__new__(AgentRunner)
    runner.settings = SimpleNamespace(
        prompts=SimpleNamespace(agent_system_prompt="system"),
        max_agent_steps=2,
        storage=SimpleNamespace(local_data_dir=str(tmp_path)),
    )
    runner.profile_repo = StubProfileRepo(_profile())
    runner.executor = StubExecutor()
    runner.result_writer = StubWriter()
    runner.llm = StubLLM(
        [
            _response(tool_calls=[_tool_call("blocked_tool", '{"value":"x"}')]),
            _response(content="done"),
        ]
    )

    record = runner.run(AgentTaskRequest(task_name="demo", instructions="run"))

    assert record.status == "success"
    assert record.blocked_calls
    assert record.tools_called[0]["status"] == "blocked"
    assert runner.executor.calls == []


def test_agent_runner_executes_allowlisted_tool(tmp_path: Path) -> None:
    runner = AgentRunner.__new__(AgentRunner)
    runner.settings = SimpleNamespace(
        prompts=SimpleNamespace(agent_system_prompt="system"),
        max_agent_steps=2,
        storage=SimpleNamespace(local_data_dir=str(tmp_path)),
    )
    runner.profile_repo = StubProfileRepo(_profile())
    runner.executor = StubExecutor()
    runner.result_writer = StubWriter()
    runner.llm = StubLLM(
        [
            _response(tool_calls=[_tool_call("allowed_tool", '{"value":"ok"}')]),
            _response(content="final"),
        ]
    )

    record = runner.run(AgentTaskRequest(task_name="demo", instructions="run"))

    assert record.status == "success"
    assert runner.executor.calls
    assert record.tools_called[0]["tool_name"] == "allowed_tool"
