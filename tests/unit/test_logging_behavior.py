from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from databricks_mcp_agent_hello_world.llm_client import LLMToolCall, LLMTurnResult
from databricks_mcp_agent_hello_world.models import AgentTaskRequest
from databricks_mcp_agent_hello_world.runner.agent_runner import AgentRunner
from databricks_mcp_agent_hello_world.tools.runtime import RuntimeTool, ToolSource


class StubProvider:
    def __init__(self, tools: list[RuntimeTool]) -> None:
        self.tools = tools

    def list_tools(self) -> list[RuntimeTool]:
        return list(self.tools)


class StubLLM:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    def chat(self, *, messages, tools):
        del messages, tools
        response = self.responses[self.calls]
        self.calls += 1
        return response


def _tool(name: str) -> RuntimeTool:
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
        execute=lambda **kwargs: {"echo": kwargs},
        source=ToolSource(type="local_python", id="local_python"),
    )


def _response(content: str | None = None, tool_calls=None):
    return LLMTurnResult(content=content, tool_calls=tool_calls or [])


def _tool_call(name: str, arguments: str, call_id: str = "call-1"):
    return LLMToolCall(id=call_id, name=name, arguments=arguments)


def _runner(tmp_path: Path, llm, *, tools: list[RuntimeTool] | None = None) -> AgentRunner:
    runner = AgentRunner.__new__(AgentRunner)
    runner.settings = SimpleNamespace(
        prompts=SimpleNamespace(agent_system_prompt="system"),
        max_agent_steps=2,
        llm_endpoint_name="databricks-meta-llama",
        storage=SimpleNamespace(local_data_dir=str(tmp_path)),
    )
    runner.provider = StubProvider(tools or [_tool("get_user_profile")])
    runner.llm = llm
    return runner


def test_unknown_tool_call_logs_warning_without_old_blocked_language(
    tmp_path: Path,
    caplog,
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
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.runner.agent_runner.write_event_rows",
        lambda settings, rows: None,
    )

    caplog.set_level(logging.INFO, logger="databricks_mcp_agent_hello_world.runner.agent_runner")

    record = runner.run(
        AgentTaskRequest(
            task_name="customer_account_brief",
            instructions="Try the unknown tool.",
        )
    )

    assert record.tools_called[0]["status"] == "error"
    assert any(
        logged.levelno == logging.WARNING
        and logged.message == "Unknown tool call: create_support_ticket"
        for logged in caplog.records
    )
    assert not any("Blocked disallowed tool call" in logged.message for logged in caplog.records)
