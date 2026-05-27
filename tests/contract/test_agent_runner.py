from __future__ import annotations

from pathlib import Path

from databricks_mcp_agent_hello_world.models import (
    AgentRunRecord,
    AgentTaskRequest,
)
from databricks_mcp_agent_hello_world.tools.runtime import RuntimeTool, ToolSource
from tests.contract.agent_runner_helpers import (
    RaisingProvider,
    StubLLM,
    capture_event_rows,
    discovered_tools,
    event_payload,
    llm_response,
    runtime_tool,
    tool_call,
)
from tests.contract.agent_runner_helpers import (
    runner as make_runner,
)


def test_agent_runner_persists_run_contract_for_success(tmp_path: Path, monkeypatch) -> None:
    calls = []
    tools = discovered_tools(calls)
    runner = make_runner(
        tmp_path,
        StubLLM(
            [
                llm_response(
                    tool_calls=[tool_call("get_user_profile", '{"user_id":"usr_ada_01"}')]
                ),
                llm_response(content="## Onboarding Brief\nAda Lovelace"),
            ]
        ),
        tools=tools,
    )
    capture_event_rows(runner, monkeypatch)

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            payload={"user_id": "usr_ada_01"},
            run_id="run-123",
        )
    )

    assert isinstance(record, AgentRunRecord)
    assert record.status == "success"
    assert record.result["final_response"] == "## Onboarding Brief\nAda Lovelace"
    assert record.result["available_tools"] == [tool.name for tool in tools]
    assert record.result["tool_calls"][0]["tool_name"] == "get_user_profile"
    assert record.result["tool_calls"][0]["status"] == "ok"
    assert calls == [{"tool_name": "get_user_profile", "arguments": {"user_id": "usr_ada_01"}}]
    assert runner.llm.call_args[0]["tools"] == [tool.spec for tool in tools]
    assert runner.llm.call_args[0]["tool_choice"] == "auto"
    assert any(
        message["role"] == "tool" and message["tool_call_id"] == "call-1"
        for message in runner.llm.call_args[1]["messages"]
    )

    events = runner.persisted_event_rows
    assert [row["event_type"] for row in events] == [
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
    assert {row["run_key"] for row in events} == {"run-123"}
    assert all("conversation_id" not in row for row in events)
    assert all("event_id" not in row for row in events)
    assert event_payload(events[0])["available_tools_count"] == len(tools)
    assert events[-1]["status"] == "success"


def test_agent_runner_rejects_unknown_tool_calls_without_executing_provider(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = make_runner(
        tmp_path,
        StubLLM(
            [
                llm_response(tool_calls=[tool_call("create_support_ticket", '{"summary":"help"}')]),
                llm_response(content="Finished after the error."),
            ]
        ),
        tools=discovered_tools()[:-1],
    )
    capture_event_rows(runner, monkeypatch)

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            run_id="run-unknown",
        )
    )

    assert runner.provider.calls == []
    assert record.result["tool_calls"][0]["status"] == "error"
    assert record.result["tool_calls"][0]["error"] == "Unknown tool call: create_support_ticket"


def test_agent_runner_works_with_tools_from_multiple_sources(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = []
    local_tool = runtime_tool("get_user_profile", calls)
    remote_tool = RuntimeTool(
        name="lookup_remote_user",
        spec={
            "type": "function",
            "function": {
                "name": "lookup_remote_user",
                "description": "Lookup a remote user.",
                "parameters": {
                    "type": "object",
                    "required": ["user_id"],
                    "properties": {"user_id": {"type": "string"}},
                    "additionalProperties": False,
                },
            },
        },
        execute=lambda **kwargs: (
            calls.append({"tool_name": "lookup_remote_user", "arguments": kwargs}) or {"ok": True}
        ),
        source=ToolSource(type="databricks_mcp", id="uc_functions"),
    )
    runner = make_runner(
        tmp_path,
        StubLLM(
            [
                llm_response(tool_calls=[tool_call("lookup_remote_user", '{"user_id":"usr_1"}')]),
                llm_response(content="Finished with both inventories available."),
            ]
        ),
        tools=[local_tool, remote_tool],
    )
    capture_event_rows(runner, monkeypatch)

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            run_id="run-multi-source",
        )
    )

    assert record.status == "success"
    assert record.result["available_tools"] == ["get_user_profile", "lookup_remote_user"]
    assert calls == [{"tool_name": "lookup_remote_user", "arguments": {"user_id": "usr_1"}}]
    assert runner.llm.call_args[0]["tools"] == [local_tool.spec, remote_tool.spec]
    tool_result_event = next(
        row for row in runner.persisted_event_rows if row["event_type"] == "tool_result"
    )
    payload = event_payload(tool_result_event)
    assert payload["metadata"]["source_type"] == "databricks_mcp"


def test_agent_runner_marks_malformed_tool_arguments_as_error_without_crashing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = make_runner(
        tmp_path,
        StubLLM(
            [
                llm_response(tool_calls=[tool_call("get_user_profile", '{"user_id":')]),
                llm_response(content="Finished after malformed tool args."),
            ]
        ),
    )
    capture_event_rows(runner, monkeypatch)

    record = runner.run(
        AgentTaskRequest(task_name="workspace_onboarding_brief", instructions="Write the report.")
    )

    assert record.status == "success"
    assert record.result["tool_calls"][0]["status"] == "error"
    tool_result_event = next(
        row for row in runner.persisted_event_rows if row["event_type"] == "tool_result"
    )
    assert tool_result_event["status"] == "error"


def test_agent_runner_rejects_invalid_tool_arguments_before_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = []
    runtime_tool = RuntimeTool(
        name="lookup_remote_user",
        spec={
            "type": "function",
            "function": {
                "name": "lookup_remote_user",
                "description": "Lookup a remote user.",
                "parameters": {
                    "type": "object",
                    "required": ["user_id"],
                    "properties": {"user_id": {"type": "string"}},
                    "additionalProperties": False,
                },
            },
        },
        execute=lambda **kwargs: calls.append(kwargs) or {"ok": True},
        source=ToolSource(type="databricks_mcp", id="uc_functions"),
    )
    runner = make_runner(
        tmp_path,
        StubLLM(
            [
                llm_response(tool_calls=[tool_call("lookup_remote_user", "{}")]),
                llm_response(content="Finished after validation error."),
            ]
        ),
        tools=[runtime_tool],
    )
    capture_event_rows(runner, monkeypatch)

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            run_id="run-invalid-args",
        )
    )

    assert calls == []
    assert record.status == "success"
    assert record.result["tool_calls"][0]["status"] == "error"
    assert (
        "Invalid arguments for tool `lookup_remote_user`" in record.result["tool_calls"][0]["error"]
    )
    tool_result_event = next(
        row for row in runner.persisted_event_rows if row["event_type"] == "tool_result"
    )
    payload = event_payload(tool_result_event)
    assert payload["content"]["error_type"] == "invalid_tool_arguments"
    assert payload["metadata"]["error_type"] == "invalid_tool_arguments"
    assert payload["metadata"]["source_type"] == "databricks_mcp"


def test_agent_runner_reports_invalid_remote_tool_schema_separately(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = []
    runtime_tool = RuntimeTool(
        name="bad_remote_tool",
        spec={
            "type": "function",
            "function": {
                "name": "bad_remote_tool",
                "description": "Remote tool with bad schema.",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "not-a-json-schema-type"}},
                },
            },
        },
        execute=lambda **kwargs: calls.append(kwargs) or {"ok": True},
        source=ToolSource(type="databricks_mcp", id="uc_functions"),
    )
    runner = make_runner(
        tmp_path,
        StubLLM(
            [
                llm_response(tool_calls=[tool_call("bad_remote_tool", '{"value":"x"}')]),
                llm_response(content="Finished after schema error."),
            ]
        ),
        tools=[runtime_tool],
    )
    capture_event_rows(runner, monkeypatch)

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            run_id="run-invalid-schema",
        )
    )

    assert calls == []
    assert record.result["tool_calls"][0]["status"] == "error"
    assert "Invalid schema for tool `bad_remote_tool`" in record.result["tool_calls"][0]["error"]
    tool_result_event = next(
        row for row in runner.persisted_event_rows if row["event_type"] == "tool_result"
    )
    payload = event_payload(tool_result_event)
    assert payload["content"]["error_type"] == "invalid_tool_schema"
    assert payload["metadata"]["error_type"] == "invalid_tool_schema"
    assert payload["metadata"]["source_type"] == "databricks_mcp"


def test_agent_runner_returns_max_steps_exceeded_when_llm_never_finishes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = make_runner(
        tmp_path,
        StubLLM(
            [
                llm_response(
                    tool_calls=[tool_call("get_user_profile", '{"user_id":"usr_ada_01"}')]
                ),
                llm_response(content="Finished after tool error."),
            ]
        ),
        max_agent_steps=1,
    )
    capture_event_rows(runner, monkeypatch)

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            run_id="run-max",
        )
    )

    assert record.status == "max_steps_exceeded"
    assert runner.persisted_event_rows[-1]["event_type"] == "run_max_steps_exceeded"
    assert runner.persisted_event_rows[-1]["status"] == "max_steps_exceeded"


def test_agent_runner_emits_error_event_when_tool_execution_raises(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = make_runner(
        tmp_path,
        StubLLM(
            [
                llm_response(
                    tool_calls=[tool_call("get_user_profile", '{"user_id":"usr_ada_01"}')]
                ),
                llm_response(content="Finished after tool error."),
            ]
        ),
        provider=RaisingProvider([runtime_tool("get_user_profile", raises=True)]),
    )
    capture_event_rows(runner, monkeypatch)

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
        )
    )

    assert record.result["tool_calls"][0]["status"] == "error"
    assert record.result["tool_calls"][0]["error"] == "tool boom: get_user_profile"
