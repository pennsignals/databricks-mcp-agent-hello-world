from __future__ import annotations

from pathlib import Path

import pytest

from databricks_mcp_agent_hello_world.models import AgentTaskRequest
from databricks_mcp_agent_hello_world.runner.agent_runner import AgentRunner
from tests.contract.test_agent_runner import StubLLM, _capture_event_rows, _response, _runner


def test_agent_runner_records_run_failed_event_when_llm_step_raises(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = _runner(
        tmp_path,
        StubLLM([RuntimeError("llm boom")]),
    )
    _capture_event_rows(runner, monkeypatch)

    with pytest.raises(RuntimeError, match="llm boom"):
        runner.run(
            AgentTaskRequest(
                task_name="workspace_onboarding_brief",
                instructions="Write the report.",
                run_id="run-error",
            )
        )

    failed_event = next(row for row in runner.persisted_event_rows if row["event_type"] == "run_failed")
    assert failed_event["status"] == "error"
    assert failed_event["error_message"] == "llm boom"


def test_agent_runner_init_builds_provider_and_llm(monkeypatch) -> None:
    created = {}
    settings = object()

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.runner.agent_runner.get_tool_provider",
        lambda actual_settings: created.setdefault("provider_settings", actual_settings) or "provider",
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.runner.agent_runner.DatabricksLLM",
        lambda actual_settings: created.setdefault("llm_settings", actual_settings) or "llm",
    )

    runner = AgentRunner(settings)

    assert runner.settings is settings
    assert created["provider_settings"] is settings
    assert created["llm_settings"] is settings


def test_agent_runner_success_without_tool_calls_truncates_terminal_excerpt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    long_response = "x" * 600
    runner = _runner(tmp_path, StubLLM([_response(content=long_response)]))
    _capture_event_rows(runner, monkeypatch)

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            run_id="run-terminal",
        )
    )

    assert record.status == "success"
    response_event = next(row for row in runner.persisted_event_rows if row["event_type"] == "llm_response")
    completed_event = next(row for row in runner.persisted_event_rows if row["event_type"] == "run_completed")
    assert len(response_event["final_response_excerpt"]) == 500
    assert len(completed_event["final_response_excerpt"]) == 500
