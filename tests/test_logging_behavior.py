from __future__ import annotations

import logging
import sys
import types
from pathlib import Path
from types import SimpleNamespace

from databricks_mcp_agent_hello_world.models import AgentTaskRequest, ToolResult, ToolSpec
from databricks_mcp_agent_hello_world.runner.agent_runner import AgentRunner
from databricks_mcp_agent_hello_world.storage import spark

EXPECTED_SPARK_FALLBACK_MESSAGE = (
    "Local mode: no active Spark session detected; using local fallback persistence."
)


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


class StubLLM:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    def tool_step(self, messages, tools, tool_choice=None):
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


def _response(content: str | None = None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _tool_call(name: str, arguments: str, call_id: str = "call-1"):
    function = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(id=call_id, function=function)


def _runner(tmp_path: Path, llm, *, tools: list[ToolSpec] | None = None) -> AgentRunner:
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


def test_unknown_tool_call_does_not_emit_blocked_logs(tmp_path: Path, caplog, monkeypatch) -> None:
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
        record.levelno == logging.WARNING
        and record.message == "Unknown tool call: create_support_ticket"
        for record in caplog.records
    )
    assert not any("Blocked disallowed tool call" in record.message for record in caplog.records)
