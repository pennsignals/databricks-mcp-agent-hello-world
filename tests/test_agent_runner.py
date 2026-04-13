from pathlib import Path
from types import SimpleNamespace

from databricks_mcp_agent_hello_world.models import (
    AgentTaskRequest,
    HelloWorldDemoResult,
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


def _response(content: str | None = None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _tool_call(name: str, arguments: str, call_id: str = "call-1"):
    function = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(id=call_id, function=function)


def _runner(tmp_path: Path, llm) -> AgentRunner:
    runner = AgentRunner.__new__(AgentRunner)
    runner.settings = SimpleNamespace(
        prompts=SimpleNamespace(agent_system_prompt="system"),
        max_agent_steps=2,
        storage=SimpleNamespace(local_data_dir=str(tmp_path)),
    )
    runner.profile_repo = StubProfileRepo(_profile())
    runner.executor = StubExecutor()
    runner.result_writer = StubWriter()
    runner.llm = llm
    return runner


def test_agent_runner_returns_hello_world_contract(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(
                    tool_calls=[
                        _tool_call("greet_user", '{"value":"Ada"}', call_id="call-1"),
                        _tool_call(
                            "search_demo_handbook",
                            '{"value":"local setup tip"}',
                            call_id="call-2",
                        ),
                        _tool_call(
                            "get_demo_setting",
                            '{"value":"runtime_target"}',
                            call_id="call-3",
                        ),
                    ]
                ),
                _response(content="Hello Ada, this report is ready."),
            ]
        ),
    )

    record = runner.run(
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

    assert isinstance(record, HelloWorldDemoResult)
    assert record.task_name == "hello_world_demo"
    assert record.available_tools == [
        "greet_user",
        "search_demo_handbook",
        "get_demo_setting",
        "tell_demo_joke",
    ]
    assert record.allowed_tools == [
        "greet_user",
        "search_demo_handbook",
        "get_demo_setting",
    ]
    assert [item.tool_name for item in record.disallowed_tools] == ["tell_demo_joke"]
    assert [item.status for item in record.tool_calls] == ["ok", "ok", "ok"]
    assert [item.tool_name for item in record.tool_calls] == [
        "greet_user",
        "search_demo_handbook",
        "get_demo_setting",
    ]
    assert record.final_answer == "Hello Ada, this report is ready."


def test_agent_runner_records_blocked_hello_world_tool_attempt(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(tool_calls=[_tool_call("tell_demo_joke", '{"value":"Ada"}')]),
                _response(content="Hello Ada, I stayed within the allowlist."),
            ]
        ),
    )

    record = runner.run(
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

    assert record.tool_calls[0].status == "blocked"
    assert [item.tool_name for item in record.disallowed_tools] == ["tell_demo_joke"]
    assert runner.executor.calls == []
    assert runner.result_writer.run_records[0].blocked_calls[0]["tool_name"] == "tell_demo_joke"
