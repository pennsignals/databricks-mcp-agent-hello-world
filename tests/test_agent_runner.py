import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world.models import (
    AgentRunRecord,
    AgentTaskRequest,
    ToolProfile,
    ToolResult,
    ToolSpec,
)
from databricks_mcp_agent_hello_world.runner.agent_runner import AgentRunner


class StubProfileRepo:
    def __init__(self, profile: ToolProfile | None):
        self.profile = profile

    def load_active(self, profile_name: str):
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
            metadata={"request_id": tool_call.request_id},
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
        self.call_args = []

    def tool_step(self, messages, tools, tool_choice=None):
        self.call_args.append(
            {
                "messages": messages,
                "tools": tools,
                "tool_choice": tool_choice,
            }
        )
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
        llm_endpoint_name="endpoint-a",
        prompt_version="v1",
        compile_task_name="generic_task",
        compile_task_hash="compile-task-hash",
        compile_task_summary="generic_task: Write the report.",
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


def _runner(
    tmp_path: Path,
    llm,
    *,
    profile: ToolProfile | None = None,
    max_agent_steps: int = 2,
) -> AgentRunner:
    runner = AgentRunner.__new__(AgentRunner)
    runner.settings = SimpleNamespace(
        prompts=SimpleNamespace(agent_system_prompt="system"),
        max_agent_steps=max_agent_steps,
        active_profile_name="default",
        storage=SimpleNamespace(local_data_dir=str(tmp_path)),
    )
    runner.profile_repo = StubProfileRepo(profile)
    runner.executor = StubExecutor()
    runner.result_writer = StubWriter()
    runner.llm = llm
    return runner


def test_agent_runner_returns_generic_result_contract(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(
                    tool_calls=[
                        _tool_call("greet_user", '{"value":"Ada"}', call_id="call-1"),
                    ]
                ),
                _response(content="Hello Ada, this report is ready."),
            ]
        ),
        profile=_profile(),
    )

    record = runner.run(
        AgentTaskRequest(
            task_name="generic_task",
            instructions="Write the report.",
            payload={
                "name": "Ada",
                "handbook_query": "local setup tip",
                "setting_key": "runtime_target",
            },
        )
    )

    assert isinstance(record, AgentRunRecord)
    assert runner.llm.call_args[0]["tool_choice"] is None
    assert record.result == {
        "final_response": "Hello Ada, this report is ready.",
        "task_payload": {
            "name": "Ada",
            "handbook_query": "local setup tip",
            "setting_key": "runtime_target",
        },
        "available_tools": [
            "greet_user",
            "search_demo_handbook",
            "get_demo_setting",
            "tell_demo_joke",
        ],
        "allowed_tools": [
            "greet_user",
            "search_demo_handbook",
            "get_demo_setting",
        ],
        "tool_trace": [
            {
                "tool_name": "greet_user",
                "arguments": {"value": "Ada"},
                "status": "ok",
                "error": None,
            }
        ],
    }
    assert [item.tool_name for item in runner.executor.calls] == ["greet_user"]
    assert runner.result_writer.run_records[0].result == record.result
    assert runner.result_writer.output_records[0].output_payload == record.result


def test_agent_runner_marks_max_steps_exceeded_with_generic_result_payload(
    tmp_path: Path,
) -> None:
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(
                    tool_calls=[
                        _tool_call("greet_user", '{"value":"Ada"}', call_id="call-1"),
                    ]
                ),
            ]
        ),
        profile=_profile(),
        max_agent_steps=1,
    )

    record = runner.run(
        AgentTaskRequest(
            task_name="generic_task",
            instructions="Write the report.",
            payload={"name": "Ada"},
        )
    )

    assert record.status == "max_steps_exceeded"
    assert record.error_message == "Maximum agent steps exceeded."
    assert record.result == {
        "final_response": "",
        "task_payload": {"name": "Ada"},
        "available_tools": [
            "greet_user",
            "search_demo_handbook",
            "get_demo_setting",
            "tell_demo_joke",
        ],
        "allowed_tools": [
            "greet_user",
            "search_demo_handbook",
            "get_demo_setting",
        ],
        "tool_trace": [
            {
                "tool_name": "greet_user",
                "arguments": {"value": "Ada"},
                "status": "ok",
                "error": None,
            }
        ],
    }
    assert runner.result_writer.run_records[0].result == record.result
    assert runner.result_writer.output_records[0].output_payload == record.result


def test_agent_runner_does_not_force_first_turn_tool_use(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        StubLLM([_response(content="Hello Ada, this report is ready.")]),
        profile=_profile(),
    )

    runner.run(
        AgentTaskRequest(
            task_name="generic_task",
            instructions="Write the report.",
            payload={"name": "Ada"},
        )
    )

    assert runner.llm.call_args[0]["tool_choice"] is None


def test_agent_runner_records_blocked_tool_attempt_and_persists_result(
    tmp_path: Path,
) -> None:
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(tool_calls=[_tool_call("tell_demo_joke", '{"value":"Ada"}')]),
                _response(content="Hello Ada, I stayed within the allowlist."),
            ]
        ),
        profile=_profile(),
    )

    record = runner.run(
        AgentTaskRequest(
            task_name="generic_task",
            instructions="Write the report.",
            payload={"name": "Ada"},
        )
    )

    assert record.result["tool_trace"][0]["status"] == "blocked"
    assert record.result["tool_trace"][0]["error"]
    assert runner.executor.calls == []
    assert runner.result_writer.run_records[0].blocked_calls[0]["tool_name"] == "tell_demo_joke"
    assert runner.result_writer.output_records[0].output_payload == record.result


def test_agent_runner_logs_expected_blocked_call_at_info(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(tool_calls=[_tool_call("tell_demo_joke", '{"value":"Ada"}')]),
                _response(content="Hello Ada, I stayed within the allowlist."),
            ]
        ),
        profile=_profile(),
    )

    caplog.set_level(logging.INFO, logger="databricks_mcp_agent_hello_world.runner.agent_runner")

    runner.run(
        AgentTaskRequest(
            task_name="generic_task",
            instructions="Write the report.",
            payload={"name": "Ada"},
            expected_blocked_calls=True,
        )
    )

    messages = [record.message for record in caplog.records]
    assert "Blocked disallowed tool call (expected): tell_demo_joke" in messages
    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]


def test_agent_runner_logs_unexpected_blocked_call_at_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(tool_calls=[_tool_call("tell_demo_joke", '{"value":"Ada"}')]),
                _response(content="Hello Ada, I stayed within the allowlist."),
            ]
        ),
        profile=_profile(),
    )

    caplog.set_level(logging.INFO, logger="databricks_mcp_agent_hello_world.runner.agent_runner")

    runner.run(
        AgentTaskRequest(
            task_name="generic_task",
            instructions="Write the report.",
            payload={"name": "Ada"},
        )
    )

    warning_messages = [record.message for record in caplog.records if record.levelno == logging.WARNING]
    assert warning_messages == ["Blocked disallowed tool call: tell_demo_joke"]


def test_agent_runner_fails_when_no_active_profile_exists(tmp_path: Path) -> None:
    runner = _runner(tmp_path, StubLLM([_response(content="unused")]), profile=None)

    with pytest.raises(RuntimeError, match="No active tool profile found"):
        runner.run(
            AgentTaskRequest(
                task_name="generic_task",
                instructions="Write the report.",
                payload={"name": "Ada"},
            )
        )


def test_agent_runner_fails_clearly_when_delta_profile_table_is_unreadable(
    tmp_path: Path,
) -> None:
    runner = _runner(tmp_path, StubLLM([_response(content="unused")]), profile=None)

    class SparkBackedProfileRepo(StubProfileRepo):
        spark = object()

        def is_table_reachable(self):
            raise RuntimeError("Table or view not found: main.agent.tool_profiles")

    runner.profile_repo = SparkBackedProfileRepo(None)

    with pytest.raises(RuntimeError, match="compile_tool_profile_job first"):
        runner.run(
            AgentTaskRequest(
                task_name="generic_task",
                instructions="Write the report.",
                payload={"name": "Ada"},
            )
        )
