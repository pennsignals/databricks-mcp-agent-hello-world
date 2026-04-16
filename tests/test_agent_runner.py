import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world.models import (
    AgentRunRecord,
    AgentTaskRequest,
    ToolResult,
    ToolSpec,
)
from databricks_mcp_agent_hello_world.runner.agent_runner import AgentRunner


class StubProvider:
    def __init__(self, tools: list[ToolSpec], inventory_hash: str = "inventory-hash") -> None:
        self.tools = tools
        self._inventory_hash = inventory_hash

    def list_tools(self) -> list[ToolSpec]:
        return list(self.tools)

    def inventory_hash(self) -> str:
        return self._inventory_hash


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


class RaisingExecutor(StubExecutor):
    def call_tool(self, tool_call):
        self.calls.append(tool_call)
        raise RuntimeError(f"tool boom: {tool_call.tool_name}")


class StubWriter:
    def __init__(self) -> None:
        self.event_batches = []
        self.event_rows = []

    def write_event_rows(self, rows) -> None:
        batch = [dict(row) for row in rows]
        self.event_batches.append(batch)
        self.event_rows.extend(batch)


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
        if isinstance(response, Exception):
            raise response
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


def _discovered_tools() -> list[ToolSpec]:
    return [
        _tool("get_user_profile"),
        _tool("search_onboarding_docs"),
        _tool("get_workspace_setting"),
        _tool("list_recent_job_runs"),
        _tool("create_support_ticket"),
    ]


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
    tools: list[ToolSpec] | None = None,
    max_agent_steps: int = 2,
    executor=None,
) -> AgentRunner:
    runner = AgentRunner.__new__(AgentRunner)
    runner.settings = SimpleNamespace(
        prompts=SimpleNamespace(agent_system_prompt="system"),
        max_agent_steps=max_agent_steps,
        llm_endpoint_name="databricks-meta-llama",
        storage=SimpleNamespace(local_data_dir=str(tmp_path)),
    )
    runner.provider = StubProvider(tools or _discovered_tools())
    runner.executor = executor or StubExecutor()
    runner.result_writer = StubWriter()
    runner.llm = llm
    return runner


def _event_types(rows: list[dict]) -> list[str]:
    return [row["event_type"] for row in rows]


def _payload(row: dict) -> dict:
    return json.loads(row["payload_json"])


def test_agent_runner_returns_runtime_result_contract_and_event_log(tmp_path: Path) -> None:
    tools = _discovered_tools()
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(
                    tool_calls=[
                        _tool_call(
                            "get_user_profile",
                            '{"user_id":"usr_ada_01"}',
                            call_id="call-1",
                        ),
                    ]
                ),
                _response(content="## Onboarding Brief\nAda Lovelace"),
            ]
        ),
        tools=tools,
    )

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            payload={"user_id": "usr_ada_01"},
            run_id="run-123",
        )
    )

    assert isinstance(record, AgentRunRecord)
    assert runner.llm.call_args[0]["tool_choice"] == "auto"
    assert [tool["function"]["name"] for tool in runner.llm.call_args[0]["tools"]] == [
        tool.tool_name for tool in tools
    ]
    assert "create_support_ticket" in record.result["available_tools"]
    assert [item.tool_name for item in runner.executor.calls] == ["get_user_profile"]
    assert record.result == {
        "final_response": "## Onboarding Brief\nAda Lovelace",
        "available_tools": [tool.tool_name for tool in tools],
        "available_tools_count": len(tools),
        "tool_calls": [
            {
                "tool_name": "get_user_profile",
                "arguments": {"user_id": "usr_ada_01"},
                "status": "ok",
                "error": None,
            }
        ],
    }

    events = runner.result_writer.event_rows
    assert _event_types(events) == [
        "run_started",
        "llm_request",
        "llm_response",
        "tool_call",
        "tool_result",
        "llm_request",
        "llm_response",
        "run_completed",
    ]
    assert [row["event_index"] for row in events] == list(range(len(events)))
    assert [row["event_id"] for row in events] == [f"run-123:{index}" for index in range(8)]
    assert all(isinstance(row["payload_json"], str) for row in events)
    assert events[0]["conversation_id"] == "run-123"
    assert events[0]["run_key"] == "run-123"
    assert events[0]["status"] == "started"
    assert _payload(events[0])["available_tools_count"] == len(tools)
    assert events[1]["turn_index"] == 0
    assert _payload(events[1])["tool_choice"] == "auto"
    assert events[2]["turn_index"] == 0
    assert events[3]["tool_name"] == "get_user_profile"
    assert _payload(events[3]) == {
        "arguments_raw": '{"user_id":"usr_ada_01"}',
        "arguments_parsed": {"user_id": "usr_ada_01"},
        "parse_error": None,
    }
    assert events[4]["status"] == "ok"
    assert _payload(events[4])["content"] == {"echo": {"user_id": "usr_ada_01"}}
    assert events[6]["final_response_excerpt"] == "## Onboarding Brief\nAda Lovelace"
    assert events[7]["status"] == "success"
    assert events[7]["inventory_hash"] == "inventory-hash"
    assert _payload(events[7]) == record.result


def test_agent_runner_marks_max_steps_exceeded_with_runtime_result_payload(
    tmp_path: Path,
) -> None:
    tools = _discovered_tools()
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(
                    tool_calls=[
                        _tool_call(
                            "get_user_profile",
                            '{"user_id":"usr_ada_01"}',
                            call_id="call-1",
                        ),
                    ]
                ),
            ]
        ),
        tools=tools,
        max_agent_steps=1,
    )

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            payload={"user_id": "usr_ada_01"},
            run_id="run-max",
        )
    )

    assert record.status == "max_steps_exceeded"
    assert record.error_message == "Maximum agent steps exceeded."
    assert record.result["available_tools"] == [tool.tool_name for tool in tools]
    assert record.result["available_tools_count"] == len(tools)
    assert record.result["tool_calls"] == [
        {
            "tool_name": "get_user_profile",
            "arguments": {"user_id": "usr_ada_01"},
            "status": "ok",
            "error": None,
        }
    ]
    assert _event_types(runner.result_writer.event_rows) == [
        "run_started",
        "llm_request",
        "llm_response",
        "tool_call",
        "tool_result",
        "run_max_steps_exceeded",
    ]
    assert runner.result_writer.event_rows[-1]["event_id"] == "run-max:5"
    assert runner.result_writer.event_rows[-1]["status"] == "max_steps_exceeded"
    assert runner.result_writer.event_rows[-1]["error_message"] == "Maximum agent steps exceeded."


def test_agent_runner_returns_error_for_unknown_tool_call(tmp_path: Path) -> None:
    tools = _discovered_tools()[:-1]
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(tool_calls=[_tool_call("create_support_ticket", '{"summary":"help"}')]),
                _response(content="Finished after the error."),
            ]
        ),
        tools=tools,
    )

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            run_id="run-unknown",
        )
    )

    assert runner.executor.calls == []
    assert record.result["tool_calls"][0] == {
        "tool_name": "create_support_ticket",
        "arguments": {"summary": "help"},
        "status": "error",
        "error": "Unknown tool call: create_support_ticket",
    }
    assert "blocked" not in {record.result["tool_calls"][0]["status"]}
    assert _event_types(runner.result_writer.event_rows) == [
        "run_started",
        "llm_request",
        "llm_response",
        "tool_call",
        "tool_result",
        "llm_request",
        "llm_response",
        "run_completed",
    ]
    assert runner.result_writer.event_rows[4]["error_message"] == (
        "Unknown tool call: create_support_ticket"
    )


def test_agent_runner_preserves_tool_call_order(tmp_path: Path) -> None:
    tools = _discovered_tools()
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(
                    tool_calls=[
                        _tool_call(
                            "get_user_profile",
                            '{"user_id":"usr_ada_01"}',
                            call_id="call-1",
                        ),
                        _tool_call(
                            "search_onboarding_docs",
                            '{"query":"local development"}',
                            call_id="call-2",
                        ),
                    ]
                ),
                _response(content="Ordered trace."),
            ]
        ),
        tools=tools,
    )

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            payload={"user_id": "usr_ada_01"},
            run_id="run-order",
        )
    )

    assert [entry["tool_name"] for entry in record.result["tool_calls"]] == [
        "get_user_profile",
        "search_onboarding_docs",
    ]
    tool_events = [row for row in runner.result_writer.event_rows if row["event_type"] == "tool_call"]
    assert [row["tool_name"] for row in tool_events] == [
        "get_user_profile",
        "search_onboarding_docs",
    ]


def test_agent_runner_exposes_full_inventory_while_llm_selects_relevant_tools(
    tmp_path: Path,
) -> None:
    tools = _discovered_tools()
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(
                    tool_calls=[
                        _tool_call(
                            "get_user_profile",
                            '{"user_id":"usr_ada_01"}',
                            call_id="call-1",
                        ),
                        _tool_call(
                            "search_onboarding_docs",
                            '{"query":"uv sync"}',
                            call_id="call-2",
                        ),
                        _tool_call(
                            "get_workspace_setting",
                            '{"setting_name":"runtime_target"}',
                            call_id="call-3",
                        ),
                        _tool_call("list_recent_job_runs", '{"limit":1}', call_id="call-4"),
                    ]
                ),
                _response(
                    content=(
                        "Ada Lovelace should run uv sync locally and the runtime target is "
                        "Databricks Serverless Jobs."
                    )
                ),
            ]
        ),
        tools=tools,
    )

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            payload={"user_id": "usr_ada_01", "allow_mutations": False},
            run_id="run-inventory",
        )
    )

    assert record.status == "success"
    assert record.result["available_tools"] == [tool.tool_name for tool in tools]
    executed_tools = [entry["tool_name"] for entry in record.result["tool_calls"]]
    assert "create_support_ticket" not in executed_tools
    assert executed_tools == [
        "get_user_profile",
        "search_onboarding_docs",
        "get_workspace_setting",
        "list_recent_job_runs",
    ]
    assert "Ada Lovelace" in record.result["final_response"]
    assert "uv sync" in record.result["final_response"]
    assert "Databricks Serverless Jobs" in record.result["final_response"]


def test_agent_runner_persists_parse_failures_incrementally(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(tool_calls=[_tool_call("get_user_profile", '{"user_id":')]),
                _response(content="Handled parse failure."),
            ]
        ),
    )

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            run_id="run-parse-error",
        )
    )

    assert record.result["tool_calls"][0]["status"] == "error"
    assert "valid JSON" in record.result["tool_calls"][0]["error"]
    assert _event_types(runner.result_writer.event_rows) == [
        "run_started",
        "llm_request",
        "llm_response",
        "tool_call",
        "tool_result",
        "llm_request",
        "llm_response",
        "run_completed",
    ]
    assert _payload(runner.result_writer.event_rows[3])["parse_error"] is not None
    assert runner.result_writer.event_rows[4]["status"] == "error"


def test_agent_runner_leaves_partial_events_when_llm_raises_mid_run(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(
                    tool_calls=[
                        _tool_call("get_user_profile", '{"user_id":"usr_ada_01"}', call_id="call-1")
                    ]
                ),
                RuntimeError("llm boom"),
            ]
        ),
    )

    with pytest.raises(RuntimeError, match="llm boom"):
        runner.run(
            AgentTaskRequest(
                task_name="workspace_onboarding_brief",
                instructions="Write the report.",
                run_id="run-partial",
            )
        )

    assert _event_types(runner.result_writer.event_rows) == [
        "run_started",
        "llm_request",
        "llm_response",
        "tool_call",
        "tool_result",
        "llm_request",
        "run_failed",
    ]
    assert [row["event_id"] for row in runner.result_writer.event_rows] == [
        "run-partial:0",
        "run-partial:1",
        "run-partial:2",
        "run-partial:3",
        "run-partial:4",
        "run-partial:5",
        "run-partial:6",
    ]
    failed_event = runner.result_writer.event_rows[-1]
    assert failed_event["status"] == "error"
    assert failed_event["error_message"] == "llm boom"
    assert _payload(failed_event)["error_type"] == "RuntimeError"


def test_agent_runner_leaves_partial_events_when_tool_execution_raises(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        StubLLM([_response(tool_calls=[_tool_call("get_user_profile", '{"user_id":"usr_ada_01"}')])]),
        executor=RaisingExecutor(),
    )

    with pytest.raises(RuntimeError, match="tool boom: get_user_profile"):
        runner.run(
            AgentTaskRequest(
                task_name="workspace_onboarding_brief",
                instructions="Write the report.",
                run_id="run-tool-boom",
            )
        )

    assert _event_types(runner.result_writer.event_rows) == [
        "run_started",
        "llm_request",
        "llm_response",
        "tool_call",
        "run_failed",
    ]
    failed_event = runner.result_writer.event_rows[-1]
    assert failed_event["status"] == "error"
    assert failed_event["error_message"] == "tool boom: get_user_profile"
    assert _payload(failed_event)["result"]["tool_calls"] == []
