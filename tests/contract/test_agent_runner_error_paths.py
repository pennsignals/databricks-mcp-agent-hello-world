from __future__ import annotations

from pathlib import Path

import pytest

from databricks_mcp_agent_hello_world.models import AgentTaskRequest
from databricks_mcp_agent_hello_world.runner.agent_runner import AgentRunner
from tests.contract.agent_runner_helpers import (
    StubLLM,
    capture_event_rows,
    llm_response,
)
from tests.contract.agent_runner_helpers import (
    runner as make_runner,
)


def test_agent_runner_records_run_failed_event_when_llm_step_raises(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = make_runner(
        tmp_path,
        StubLLM([RuntimeError("llm boom")]),
    )
    capture_event_rows(runner, monkeypatch)

    with pytest.raises(RuntimeError, match="llm boom"):
        runner.run(
            AgentTaskRequest(
                task_name="workspace_onboarding_brief",
                instructions="Write the report.",
                run_id="run-error",
            )
        )

    failed_event = next(
        row for row in runner.persisted_event_rows if row["event_type"] == "run_failed"
    )
    assert failed_event["status"] == "error"
    assert failed_event["error_message"] == "llm boom"


def test_agent_runner_preserves_original_error_when_run_failed_persistence_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = make_runner(tmp_path, StubLLM([RuntimeError("llm boom")]))

    def _raise_on_run_failed(settings, rows) -> None:
        del settings
        if rows[0]["event_type"] == "run_failed":
            raise RuntimeError("persistence boom")
        runner.persisted_event_rows.extend(dict(row) for row in rows)

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.runner.agent_runner.write_event_rows",
        _raise_on_run_failed,
    )

    with pytest.raises(RuntimeError, match="llm boom"):
        runner.run(
            AgentTaskRequest(
                task_name="workspace_onboarding_brief",
                instructions="Write the report.",
                run_id="run-error",
            )
        )


def test_agent_runner_surfaces_normal_event_persistence_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = make_runner(tmp_path, StubLLM([llm_response(content="done")]))

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.runner.agent_runner.write_event_rows",
        lambda settings, rows: (_ for _ in ()).throw(RuntimeError("persistence boom")),
    )

    with pytest.raises(RuntimeError, match="persistence boom"):
        runner.run(
            AgentTaskRequest(
                task_name="workspace_onboarding_brief",
                instructions="Write the report.",
                run_id="run-error",
            )
        )


def test_agent_runner_init_builds_provider_and_llm(monkeypatch) -> None:
    created = {}
    settings = object()

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.runner.agent_runner.get_tool_provider",
        lambda actual_settings: (
            created.setdefault("provider_settings", actual_settings) or "provider"
        ),
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
    runner = make_runner(tmp_path, StubLLM([llm_response(content=long_response)]))
    capture_event_rows(runner, monkeypatch)

    record = runner.run(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            run_id="run-terminal",
        )
    )

    assert record.status == "success"
    response_event = next(
        row for row in runner.persisted_event_rows if row["event_type"] == "llm_response"
    )
    completed_event = next(
        row for row in runner.persisted_event_rows if row["event_type"] == "run_completed"
    )
    assert len(response_event["final_response_excerpt"]) == 500
    assert len(completed_event["final_response_excerpt"]) == 500
