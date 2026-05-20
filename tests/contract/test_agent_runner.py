from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from databricks_mcp_agent_hello_world.models import (
    AgentRunRecord,
    AgentTaskRequest,
)
from databricks_mcp_agent_hello_world.runner.agent_runner import AgentRunner
from databricks_mcp_agent_hello_world.tools.runtime import RuntimeTool, ToolSource


class StubProvider:
    def __init__(self, tools: list[RuntimeTool]) -> None:
        self.tools = tools
        self.calls = []

    def list_tools(self) -> list[RuntimeTool]:
        return list(self.tools)


class RaisingProvider(StubProvider):
    pass


class StubLLM:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0
        self.call_args = []

    def tool_step(self, messages, tools, tool_choice=None):
        self.call_args.append({"messages": messages, "tools": tools, "tool_choice": tool_choice})
        response = self.responses[self.calls]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return response


def _tool(name: str, calls: list | None = None, *, raises: bool = False) -> RuntimeTool:
    def _execute(**kwargs):
        if calls is not None:
            calls.append({"tool_name": name, "arguments": kwargs})
        if raises:
            raise RuntimeError(f"tool boom: {name}")
        return {"echo": kwargs}

    return RuntimeTool(
        name=name,
        spec={
            "type": "function",
            "function": {
                "name": name,
                "description": f"{name} description",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": [],
                },
            },
        },
        execute=_execute,
        source=ToolSource(type="local_python", id="builtin_tools"),
    )


def _discovered_tools(calls: list | None = None) -> list[RuntimeTool]:
    return [
        _tool("get_user_profile", calls),
        _tool("search_onboarding_docs", calls),
        _tool("get_workspace_setting", calls),
        _tool("list_recent_job_runs", calls),
        _tool("create_support_ticket", calls),
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
    tools: list[RuntimeTool] | None = None,
    max_agent_steps: int = 2,
    provider=None,
) -> AgentRunner:
    runner = AgentRunner.__new__(AgentRunner)
    runner.settings = SimpleNamespace(
        prompts=SimpleNamespace(agent_system_prompt="system"),
        max_agent_steps=max_agent_steps,
        llm_endpoint_name="databricks-meta-llama",
        storage=SimpleNamespace(local_data_dir=str(tmp_path)),
    )
    runner.provider = provider or StubProvider(tools or _discovered_tools())
    runner.persisted_event_rows = []
    runner.llm = llm
    return runner


def _capture_event_rows(runner: AgentRunner, monkeypatch) -> None:
    def _stub_write_event_rows(settings, rows) -> None:
        del settings
        runner.persisted_event_rows.extend(dict(row) for row in rows)

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.runner.agent_runner.write_event_rows",
        _stub_write_event_rows,
    )


def _payload(row: dict) -> dict:
    return json.loads(row["payload_json"])


def test_agent_runner_persists_run_contract_for_success(tmp_path: Path, monkeypatch) -> None:
    calls = []
    tools = _discovered_tools(calls)
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(tool_calls=[_tool_call("get_user_profile", '{"user_id":"usr_ada_01"}')]),
                _response(content="## Onboarding Brief\nAda Lovelace"),
            ]
        ),
        tools=tools,
    )
    _capture_event_rows(runner, monkeypatch)

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
    assert record.result["available_tools"] == [tool.name for tool in tools]
    assert calls == [{"tool_name": "get_user_profile", "arguments": {"user_id": "usr_ada_01"}}]

    events = runner.persisted_event_rows
    assert {
        "run_started",
        "llm_request",
        "llm_response",
        "tool_call",
        "tool_result",
        "run_completed",
    } <= {row["event_type"] for row in events}
    assert [row["event_index"] for row in events] == list(range(len(events)))
    assert {row["run_key"] for row in events} == {"run-123"}
    assert all("conversation_id" not in row for row in events)
    assert all("event_id" not in row for row in events)
    assert _payload(events[0])["available_tools_count"] == len(tools)
    assert events[-1]["status"] == "success"


def test_agent_runner_rejects_unknown_tool_calls_without_executing_provider(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(tool_calls=[_tool_call("create_support_ticket", '{"summary":"help"}')]),
                _response(content="Finished after the error."),
            ]
        ),
        tools=_discovered_tools()[:-1],
    )
    _capture_event_rows(runner, monkeypatch)

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


def test_agent_runner_marks_malformed_tool_arguments_as_error_without_crashing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(tool_calls=[_tool_call("get_user_profile", '{"user_id":')]),
                _response(content="Finished after malformed tool args."),
            ]
        ),
    )
    _capture_event_rows(runner, monkeypatch)

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
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(tool_calls=[_tool_call("lookup_remote_user", "{}")]),
                _response(content="Finished after validation error."),
            ]
        ),
        tools=[runtime_tool],
    )
    _capture_event_rows(runner, monkeypatch)

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
    payload = _payload(tool_result_event)
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
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(tool_calls=[_tool_call("bad_remote_tool", '{"value":"x"}')]),
                _response(content="Finished after schema error."),
            ]
        ),
        tools=[runtime_tool],
    )
    _capture_event_rows(runner, monkeypatch)

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
    payload = _payload(tool_result_event)
    assert payload["content"]["error_type"] == "invalid_tool_schema"
    assert payload["metadata"]["error_type"] == "invalid_tool_schema"
    assert payload["metadata"]["source_type"] == "databricks_mcp"


def test_agent_runner_returns_max_steps_exceeded_when_llm_never_finishes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(tool_calls=[_tool_call("get_user_profile", '{"user_id":"usr_ada_01"}')]),
                _response(content="Finished after tool error."),
            ]
        ),
        max_agent_steps=1,
    )
    _capture_event_rows(runner, monkeypatch)

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
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(tool_calls=[_tool_call("get_user_profile", '{"user_id":"usr_ada_01"}')]),
                _response(content="Finished after tool error."),
            ]
        ),
        provider=RaisingProvider([_tool("get_user_profile", raises=True)]),
    )
    _capture_event_rows(runner, monkeypatch)

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
        )
    )

    assert record.result["tool_calls"][0]["status"] == "error"
    assert record.result["tool_calls"][0]["error"] == "tool boom: get_user_profile"
