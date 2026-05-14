from __future__ import annotations

import logging
import sys
import types
from pathlib import Path
from types import SimpleNamespace

from databricks_mcp_agent_hello_world.models import AgentTaskRequest
from databricks_mcp_agent_hello_world.runner.agent_runner import AgentRunner
from databricks_mcp_agent_hello_world.storage import spark
from databricks_mcp_agent_hello_world.tools.runtime import RuntimeTool, ToolSource

EXPECTED_SPARK_FALLBACK_MESSAGE = (
    "Local mode: no active Spark session detected; using local fallback persistence."
)


class StubProvider:
    def __init__(self, tools: list[RuntimeTool]) -> None:
        self.tools = tools

    def list_tools(self) -> list[RuntimeTool]:
        return list(self.tools)


class StubLLM:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    def tool_step(self, messages, tools, tool_choice=None):
        del messages, tools, tool_choice
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
        source=ToolSource(type="local_python", id="builtin_tools"),
    )


def _response(content: str | None = None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _tool_call(name: str, arguments: str, call_id: str = "call-1"):
    function = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(id=call_id, function=function)


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


def test_get_spark_session_logs_local_fallback_once(caplog, monkeypatch) -> None:
    monkeypatch.setattr(spark, "_logged_local_fallback", False)
    monkeypatch.delenv("DATABRICKS_RUNTIME_VERSION", raising=False)

    fake_sql = types.ModuleType("pyspark.sql")

    class FakeSparkSession:
        @classmethod
        def getActiveSession(cls):
            return None

    fake_sql.SparkSession = FakeSparkSession
    fake_pyspark = types.ModuleType("pyspark")
    fake_pyspark.__path__ = []
    fake_pyspark.sql = fake_sql
    monkeypatch.setitem(sys.modules, "pyspark", fake_pyspark)
    monkeypatch.setitem(sys.modules, "pyspark.sql", fake_sql)

    caplog.set_level(logging.INFO, logger=spark.logger.name)

    assert spark.get_spark_session() is None
    assert spark.get_spark_session() is None
    assert [record.message for record in caplog.records].count(EXPECTED_SPARK_FALLBACK_MESSAGE) == 1


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
            task_name="workspace_onboarding_brief",
            instructions="Try the unknown tool.",
        )
    )

    assert record.result["tool_calls"][0]["status"] == "error"
    assert any(
        logged.levelno == logging.WARNING
        and logged.message == "Unknown tool call: create_support_ticket"
        for logged in caplog.records
    )
    assert not any("Blocked disallowed tool call" in logged.message for logged in caplog.records)
