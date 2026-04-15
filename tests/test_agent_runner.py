import logging
from pathlib import Path
from types import SimpleNamespace

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
        capability_tags=["demo"],
        data_domains=["demo"],
        example_uses=["Example"],
    )


def _profile() -> ToolProfile:
    return ToolProfile(
        profile_name="default",
        profile_version="v1",
        inventory_hash="abc123",
        provider_type="local_python",
        llm_endpoint_name="endpoint-a",
        prompt_version="v1",
        compile_task_name="workspace_onboarding_brief",
        compile_task_hash="compile-task-hash",
        compile_task_summary="workspace_onboarding_brief: Write the report.",
        discovered_tools=[
            _tool("get_user_profile"),
            _tool("search_onboarding_docs"),
            _tool("get_workspace_setting"),
            _tool("list_recent_job_runs"),
            _tool("create_support_ticket"),
        ],
        allowed_tools=[
            "get_user_profile",
            "search_onboarding_docs",
            "get_workspace_setting",
            "list_recent_job_runs",
        ],
        disallowed_tools=["create_support_ticket"],
        justifications={
            "get_user_profile": "needed",
            "search_onboarding_docs": "needed",
            "get_workspace_setting": "needed",
            "list_recent_job_runs": "needed",
            "create_support_ticket": "not needed",
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
                        _tool_call("get_user_profile", '{"user_id":"usr_ada_01"}', call_id="call-1"),
                    ]
                ),
                _response(content="## Onboarding Brief\nAda Lovelace"),
            ]
        ),
        profile=_profile(),
    )

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            payload={"user_id": "usr_ada_01"},
        )
    )

    assert isinstance(record, AgentRunRecord)
    assert runner.llm.call_args[0]["tool_choice"] is None
    assert set(record.result) == {"final_response", "task_payload", "available_tools", "allowed_tools", "tool_trace"}
    assert isinstance(record.result["final_response"], str)
    assert isinstance(record.result["allowed_tools"], list)
    assert isinstance(record.result["tool_trace"], list)
    assert record.result == {
        "final_response": "## Onboarding Brief\nAda Lovelace",
        "task_payload": {"user_id": "usr_ada_01"},
        "available_tools": [
            "get_user_profile",
            "search_onboarding_docs",
            "get_workspace_setting",
            "list_recent_job_runs",
            "create_support_ticket",
        ],
        "allowed_tools": [
            "get_user_profile",
            "search_onboarding_docs",
            "get_workspace_setting",
            "list_recent_job_runs",
        ],
        "tool_trace": [
            {
                "tool_name": "get_user_profile",
                "arguments": {"user_id": "usr_ada_01"},
                "status": "ok",
                "error": None,
            }
        ],
    }
    assert all(
        set(entry) == {"tool_name", "arguments", "status", "error"}
        and isinstance(entry["tool_name"], str)
        and isinstance(entry["arguments"], dict)
        and isinstance(entry["status"], str)
        for entry in record.result["tool_trace"]
    )
    assert [item.tool_name for item in runner.executor.calls] == ["get_user_profile"]
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
                        _tool_call("get_user_profile", '{"user_id":"usr_ada_01"}', call_id="call-1"),
                    ]
                ),
            ]
        ),
        profile=_profile(),
        max_agent_steps=1,
    )

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            payload={"user_id": "usr_ada_01"},
        )
    )

    assert record.status == "max_steps_exceeded"
    assert record.error_message == "Maximum agent steps exceeded."
    assert record.result["available_tools"] == [
        "get_user_profile",
        "search_onboarding_docs",
        "get_workspace_setting",
        "list_recent_job_runs",
        "create_support_ticket",
    ]


def test_agent_runner_blocks_disallowed_tool_and_records_it(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(tool_calls=[_tool_call("create_support_ticket", '{"summary":"help"}')]),
                _response(content="Stayed read only."),
            ]
        ),
        profile=_profile(),
    )

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Do not mutate state.",
        )
    )

    assert record.blocked_calls[0]["tool_name"] == "create_support_ticket"
    assert record.tools_called[0]["status"] == "blocked"
    assert record.result["tool_trace"][0] == {
        "tool_name": "create_support_ticket",
        "arguments": {"summary": "help"},
        "status": "blocked",
        "error": "Tool 'create_support_ticket' is not allowlisted in profile v1.",
    }


def test_agent_runner_preserves_tool_trace_order(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(
                    tool_calls=[
                        _tool_call("get_user_profile", '{"user_id":"usr_ada_01"}', call_id="call-1"),
                        _tool_call("search_onboarding_docs", '{"query":"local development"}', call_id="call-2"),
                    ]
                ),
                _response(content="Ordered trace."),
            ]
        ),
        profile=_profile(),
    )

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            payload={"user_id": "usr_ada_01"},
        )
    )

    assert [entry["tool_name"] for entry in record.result["tool_trace"]] == [
        "get_user_profile",
        "search_onboarding_docs",
    ]


def test_expected_blocked_call_logs_at_info(tmp_path: Path, caplog) -> None:
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(tool_calls=[_tool_call("create_support_ticket", '{"summary":"help"}')]),
                _response(content="Stayed read only."),
            ]
        ),
        profile=_profile(),
    )

    caplog.set_level(logging.INFO, logger="databricks_mcp_agent_hello_world.runner.agent_runner")

    runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Attempt a blocked write tool.",
            expected_blocked_calls=True,
        )
    )

    assert "Blocked disallowed tool call (expected): create_support_ticket" in [
        record.message for record in caplog.records
    ]


def test_unexpected_blocked_call_logs_at_warning(tmp_path: Path, caplog) -> None:
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(tool_calls=[_tool_call("create_support_ticket", '{"summary":"help"}')]),
                _response(content="Stayed read only."),
            ]
        ),
        profile=_profile(),
    )

    caplog.set_level(logging.INFO, logger="databricks_mcp_agent_hello_world.runner.agent_runner")

    runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Attempt a blocked write tool.",
        )
    )

    assert "Blocked disallowed tool call: create_support_ticket" in [
        record.message for record in caplog.records
    ]
