from __future__ import annotations

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
        self.calls = []

    def list_tools(self) -> list[ToolSpec]:
        return list(self.tools)

    def inventory_hash(self) -> str:
        return self._inventory_hash

    def call_tool(self, tool_call):
        self.calls.append(tool_call)
        return ToolResult(
            tool_name=tool_call.tool_name,
            status="ok",
            content={"echo": tool_call.arguments},
            metadata={"request_id": tool_call.request_id},
        )


class RaisingProvider(StubProvider):
    def call_tool(self, tool_call):
        self.calls.append(tool_call)
        raise RuntimeError(f"tool boom: {tool_call.tool_name}")


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
    tools = _discovered_tools()
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
    assert record.result["available_tools"] == [tool.tool_name for tool in tools]
    assert [item.tool_name for item in runner.provider.calls] == ["get_user_profile"]

    events = runner.persisted_event_rows
    assert {
        "run_started",
        "llm_request",
        "llm_response",
        "tool_call",
        "tool_result",
        "run_completed",
    } <= {
        row["event_type"] for row in events
    }
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


def test_agent_runner_returns_max_steps_exceeded_when_llm_never_finishes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(
                    tool_calls=[
                        _tool_call("get_user_profile", '{"user_id":"usr_ada_01"}')
                    ]
                )
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
                _response(
                    tool_calls=[
                        _tool_call("get_user_profile", '{"user_id":"usr_ada_01"}')
                    ]
                )
            ]
        ),
        provider=RaisingProvider([_tool("get_user_profile")]),
    )
    _capture_event_rows(runner, monkeypatch)

    with pytest.raises(RuntimeError, match="tool boom: get_user_profile"):
        runner.run(
            AgentTaskRequest(
                task_name="workspace_onboarding_brief",
                instructions="Write the report.",
            )
        )

    assert runner.persisted_event_rows[-1]["event_type"] == "run_failed"
    assert runner.persisted_event_rows[-1]["status"] == "error"
