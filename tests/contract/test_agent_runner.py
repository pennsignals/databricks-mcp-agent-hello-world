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


def test_customer_brief_uses_lookup_customer_tool_and_persists_success_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = []
    tools = discovered_tools(calls)
    runner = make_runner(
        tmp_path,
        StubLLM(
            [
                llm_response(
                    tool_calls=[tool_call("lookup_customer", '{"customer_id":"cust_acme"}')]
                ),
                llm_response(content="## Customer Brief\nAcme Co"),
            ]
        ),
        tools=tools,
    )
    capture_event_rows(runner, monkeypatch)

    record = runner.run(
        AgentTaskRequest(
            task_name="customer_account_brief",
            instructions="Write the report.",
            payload={"customer_id": "cust_acme"},
            run_id="run-123",
        )
    )

    assert isinstance(record, AgentRunRecord)
    assert record.status == "success"
    assert record.result["final_response"] == "## Customer Brief\nAcme Co"
    assert "tool_calls" not in record.result
    assert "available_tools" not in record.result
    assert record.tools_called[0]["tool_name"] == "lookup_customer"
    assert record.tools_called[0]["status"] == "ok"
    assert calls == [{"tool_name": "lookup_customer", "arguments": {"customer_id": "cust_acme"}}]
    assert runner.llm.call_args[0]["tools"] == [tool.spec for tool in tools]
    assert any(
        message["role"] == "tool" and message["tool_call_id"] == "call-1"
        for message in runner.llm.call_args[1]["messages"]
    )

    events = runner.persisted_event_rows
    event_types = [row["event_type"] for row in events]
    for expected_event in [
        "run_started",
        "llm_request",
        "llm_response",
        "tool_call",
        "tool_result",
        "run_completed",
    ]:
        assert expected_event in event_types
    assert event_types.index("run_started") < event_types.index("run_completed")
    assert event_types.index("tool_call") < event_types.index("tool_result")
    assert [row["event_index"] for row in events] == list(range(len(events)))
    assert {row["run_key"] for row in events} == {"run-123"}
    assert all("conversation_id" not in row for row in events)
    assert all("event_id" not in row for row in events)
    assert event_payload(events[0])["available_tools_count"] == len(tools)
    llm_response_event = next(row for row in events if row["event_type"] == "llm_response")
    llm_response_payload = event_payload(llm_response_event)
    assert llm_response_payload == {
        "content": None,
        "tool_calls": [
            {
                "id": "call-1",
                "name": "lookup_customer",
                "arguments": '{"customer_id":"cust_acme"}',
            }
        ],
    }
    assert not {"choices", "created", "model", "usage"} & set(llm_response_payload)
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
            task_name="customer_account_brief",
            instructions="Write the report.",
            run_id="run-unknown",
        )
    )

    assert runner.provider.calls == []
    assert record.tools_called[0]["status"] == "error"
    assert record.tools_called[0]["error"] == "Unknown tool call: create_support_ticket"


def test_agent_runner_works_with_tools_from_multiple_sources(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = []
    local_tool = runtime_tool("lookup_customer", calls)
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
            task_name="customer_account_brief",
            instructions="Write the report.",
            run_id="run-multi-source",
        )
    )

    assert record.status == "success"
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
                llm_response(tool_calls=[tool_call("lookup_customer", '{"customer_id":')]),
                llm_response(content="Finished after malformed tool args."),
            ]
        ),
    )
    capture_event_rows(runner, monkeypatch)

    record = runner.run(
        AgentTaskRequest(task_name="customer_account_brief", instructions="Write the report.")
    )

    assert record.status == "success"
    assert record.tools_called[0]["status"] == "error"
    tool_result_event = next(
        row for row in runner.persisted_event_rows if row["event_type"] == "tool_result"
    )
    assert tool_result_event["status"] == "error"


def test_agent_runner_marks_non_string_tool_arguments_as_error_without_crashing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = []
    runner = make_runner(
        tmp_path,
        StubLLM(
            [
                llm_response(
                    tool_calls=[
                        tool_call(
                            "lookup_customer",
                            {"customer_id": "cust_acme"},  # type: ignore[arg-type]
                        )
                    ]
                ),
                llm_response(content="Finished after non-string tool args."),
            ]
        ),
        tools=discovered_tools(calls),
    )
    capture_event_rows(runner, monkeypatch)

    record = runner.run(
        AgentTaskRequest(task_name="customer_account_brief", instructions="Write the report.")
    )

    assert calls == []
    assert record.status == "success"
    assert record.tools_called[0]["status"] == "error"
    assert record.tools_called[0]["error"].startswith("Tool call arguments must be JSON text")
    tool_call_event = next(
        row for row in runner.persisted_event_rows if row["event_type"] == "tool_call"
    )
    assert event_payload(tool_call_event)["parse_error"].startswith(
        "Tool call arguments must be JSON text"
    )


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
            task_name="customer_account_brief",
            instructions="Write the report.",
            run_id="run-invalid-args",
        )
    )

    assert calls == []
    assert record.status == "success"
    assert record.tools_called[0]["status"] == "error"
    assert "Invalid arguments for tool `lookup_remote_user`" in record.tools_called[0]["error"]
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
            task_name="customer_account_brief",
            instructions="Write the report.",
            run_id="run-invalid-schema",
        )
    )

    assert calls == []
    assert record.tools_called[0]["status"] == "error"
    assert "Invalid schema for tool `bad_remote_tool`" in record.tools_called[0]["error"]
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
                    tool_calls=[tool_call("lookup_customer", '{"customer_id":"cust_acme"}')]
                ),
                llm_response(content="Finished after tool error."),
            ]
        ),
        max_agent_steps=1,
    )
    capture_event_rows(runner, monkeypatch)

    record = runner.run(
        AgentTaskRequest(
            task_name="customer_account_brief",
            instructions="Write the report.",
            run_id="run-max",
        )
    )

    assert record.status == "max_steps_exceeded"
    assert record.result == {"reason": "max_steps_exceeded"}
    assert record.tools_called[0]["tool_name"] == "lookup_customer"
    max_steps_events = [
        row for row in runner.persisted_event_rows if row["event_type"] == "run_max_steps_exceeded"
    ]
    assert max_steps_events
    assert max_steps_events[0]["status"] == "max_steps_exceeded"


def test_agent_runner_emits_error_event_when_tool_execution_raises(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = make_runner(
        tmp_path,
        StubLLM(
            [
                llm_response(
                    tool_calls=[tool_call("lookup_customer", '{"customer_id":"cust_acme"}')]
                ),
                llm_response(content="Finished after tool error."),
            ]
        ),
        provider=RaisingProvider([runtime_tool("lookup_customer", raises=True)]),
    )
    capture_event_rows(runner, monkeypatch)

    record = runner.run(
        AgentTaskRequest(
            task_name="customer_account_brief",
            instructions="Write the report.",
        )
    )

    assert record.tools_called[0]["status"] == "error"
    assert record.tools_called[0]["error"] == "tool boom: lookup_customer"
