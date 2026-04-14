from __future__ import annotations

import logging
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world.models import (
    AgentTaskRequest,
    ToolProfile,
    ToolResult,
    ToolSpec,
)
from databricks_mcp_agent_hello_world.runner.agent_runner import AgentRunner
from databricks_mcp_agent_hello_world.storage import spark_utils

EXPECTED_SPARK_FALLBACK_MESSAGE = (
    "Local mode: no active Spark session detected; using local fallback persistence."
)
EXPECTED_BLOCKED_INFO_MESSAGE = "Blocked disallowed tool call (expected): tell_demo_joke"
EXPECTED_BLOCKED_WARNING_MESSAGE = "Blocked disallowed tool call: tell_demo_joke"


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
    def write_run_record(self, record) -> None:
        return None

    def write_output_record(self, record) -> None:
        return None


class StubLLM:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    def tool_step(self, messages, tools, tool_choice=None):
        response = self.responses[self.calls]
        self.calls += 1
        return response


def _response(content: str | None = None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _tool_call(name: str, arguments: str, call_id: str = "call-1"):
    function = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(id=call_id, function=function)


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
    )


def _profile() -> ToolProfile:
    return ToolProfile(
        profile_name="default",
        profile_version="v1",
        inventory_hash="abc123",
        provider_type="local_python",
        llm_endpoint_name="endpoint-a",
        prompt_version="v1",
        discovered_tools=[
            _tool("greet_user"),
            _tool("search_demo_handbook"),
            _tool("get_demo_setting"),
            _tool("tell_demo_joke"),
        ],
        allowed_tools=["greet_user", "search_demo_handbook", "get_demo_setting"],
        disallowed_tools=["tell_demo_joke"],
        justifications={
            "greet_user": "needed",
            "search_demo_handbook": "needed",
            "get_demo_setting": "needed",
            "tell_demo_joke": "not needed",
        },
        audit_report_text="audit",
        selection_policy="small allowlist",
    )


def _runner(tmp_path: Path, llm, *, profile: ToolProfile | None = None) -> AgentRunner:
    runner = AgentRunner.__new__(AgentRunner)
    runner.settings = SimpleNamespace(
        prompts=SimpleNamespace(agent_system_prompt="system"),
        max_agent_steps=2,
        active_profile_name="default",
        storage=SimpleNamespace(local_data_dir=str(tmp_path)),
    )
    runner.profile_repo = StubProfileRepo(profile)
    runner.executor = StubExecutor()
    runner.result_writer = StubWriter()
    runner.llm = llm
    return runner


def test_get_spark_session_logs_local_fallback_once(caplog, monkeypatch) -> None:
    monkeypatch.setattr(spark_utils, "_logged_local_fallback", False)
    monkeypatch.delenv("DATABRICKS_RUNTIME_VERSION", raising=False)

    fake_sql = types.ModuleType("pyspark.sql")

    class FakeSparkSession:
        @classmethod
        def getActiveSession(cls):
            return None

    fake_sql.SparkSession = FakeSparkSession
    fake_pyspark = types.ModuleType("pyspark")
    fake_pyspark.__path__ = []  # mark as package for the import machinery
    fake_pyspark.sql = fake_sql
    monkeypatch.setitem(sys.modules, "pyspark", fake_pyspark)
    monkeypatch.setitem(sys.modules, "pyspark.sql", fake_sql)

    caplog.set_level(logging.INFO, logger=spark_utils.logger.name)

    assert spark_utils.get_spark_session() is None
    assert spark_utils.get_spark_session() is None
    assert [record.message for record in caplog.records].count(EXPECTED_SPARK_FALLBACK_MESSAGE) == 1


def test_expected_blocked_call_logs_at_info(tmp_path: Path, caplog) -> None:
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(tool_calls=[_tool_call("tell_demo_joke", '{"value":"Ada"}')]),
                _response(content="Hello Ada, I stayed within the allowlist."),
            ]
        ),
        profile=_profile(),
    )

    caplog.set_level(logging.INFO, logger="databricks_mcp_agent_hello_world.runner.agent_runner")

    runner.run(
        AgentTaskRequest(
            task_name="generic_task",
            instructions="Try to use the joke tool.",
            expected_blocked_calls=True,
        )
    )

    assert any(record.levelno == logging.INFO and record.message == EXPECTED_BLOCKED_INFO_MESSAGE for record in caplog.records)
    assert not any(record.levelno == logging.WARNING and record.message == EXPECTED_BLOCKED_WARNING_MESSAGE for record in caplog.records)


def test_unexpected_blocked_call_logs_at_warning(tmp_path: Path, caplog) -> None:
    runner = _runner(
        tmp_path,
        StubLLM(
            [
                _response(tool_calls=[_tool_call("tell_demo_joke", '{"value":"Ada"}')]),
                _response(content="Hello Ada, I stayed within the allowlist."),
            ]
        ),
        profile=_profile(),
    )

    caplog.set_level(logging.INFO, logger="databricks_mcp_agent_hello_world.runner.agent_runner")

    runner.run(
        AgentTaskRequest(
            task_name="generic_task",
            instructions="Try to use the joke tool.",
        )
    )

    assert any(record.levelno == logging.WARNING and record.message == EXPECTED_BLOCKED_WARNING_MESSAGE for record in caplog.records)
    assert not any(record.levelno == logging.INFO and record.message == EXPECTED_BLOCKED_INFO_MESSAGE for record in caplog.records)
