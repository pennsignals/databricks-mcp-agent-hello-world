from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from databricks_tool_agent_template.llm_client import LLMToolCall, LLMTurnResult
from databricks_tool_agent_template.runner.agent_runner import AgentRunner
from databricks_tool_agent_template.tools.runtime import RuntimeTool, ToolSource


class StubProvider:
    def __init__(self, tools: list[RuntimeTool]) -> None:
        self.tools = tools
        self.calls = []

    def list_tools(self) -> list[RuntimeTool]:
        return list(self.tools)


class RaisingProvider(StubProvider):
    pass


class StubLLM:
    def __init__(self, responses) -> None:
        self.responses = responses
        self.calls = 0
        self.call_args = []

    def chat(self, *, messages, tools):
        self.call_args.append({"messages": messages, "tools": tools})
        response = self.responses[self.calls]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return response


def runtime_tool(name: str, calls: list | None = None, *, raises: bool = False) -> RuntimeTool:
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
        source=ToolSource(type="local_python", id="local_python"),
    )


def discovered_tools(calls: list | None = None) -> list[RuntimeTool]:
    return [
        runtime_tool("lookup_customer", calls),
        runtime_tool("create_support_ticket", calls),
    ]


def llm_response(content: str | None = None, tool_calls=None):
    return LLMTurnResult(content=content, tool_calls=tool_calls or [])


def tool_call(name: str, arguments: str, call_id: str = "call-1"):
    return LLMToolCall(id=call_id, name=name, arguments=arguments)


def runner(
    tmp_path: Path,
    llm,
    *,
    tools: list[RuntimeTool] | None = None,
    max_agent_steps: int = 2,
    provider=None,
) -> AgentRunner:
    agent_runner = AgentRunner.__new__(AgentRunner)
    agent_runner.settings = SimpleNamespace(
        prompts=SimpleNamespace(agent_system_prompt="system"),
        max_agent_steps=max_agent_steps,
        llm_endpoint_name="databricks-meta-llama",
        storage=SimpleNamespace(local_data_dir=str(tmp_path)),
    )
    agent_runner.provider = provider or StubProvider(tools or discovered_tools())
    agent_runner.persisted_event_rows = []
    agent_runner.llm = llm
    return agent_runner


def capture_event_rows(agent_runner: AgentRunner, monkeypatch) -> None:
    def _stub_write_event_rows(settings, rows) -> None:
        del settings
        agent_runner.persisted_event_rows.extend(dict(row) for row in rows)

    monkeypatch.setattr(
        "databricks_tool_agent_template.runner.agent_runner.write_event_rows",
        _stub_write_event_rows,
    )


def event_payload(row: dict) -> dict:
    return json.loads(row["payload_json"])
