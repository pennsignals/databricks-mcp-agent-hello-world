from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Literal

import pytest

from databricks_tool_agent_template.commands import (
    CommandResult,
    run_agent_task_command,
    run_evals_command,
)
from databricks_tool_agent_template.models import AgentRunRecord, EvalRunReport


def _record(status: Literal["success", "max_steps_exceeded"]) -> AgentRunRecord:
    return AgentRunRecord(
        run_id="run-123",
        task_name="customer_account_brief",
        status=status,
        result={
            "final_response": "",
        },
        started_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, 12, 1, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("status", "expected_exit_code"),
    [("success", 0), ("max_steps_exceeded", 1)],
)
def test_run_agent_task_command_maps_run_status_to_exit_code(
    monkeypatch,
    demo_task_input: dict[str, object],
    status: Literal["success", "max_steps_exceeded"],
    expected_exit_code: int,
) -> None:
    monkeypatch.setattr(
        "databricks_tool_agent_template.commands.load_settings",
        lambda config_path: SimpleNamespace(log_level="INFO"),
    )
    monkeypatch.setattr(
        "databricks_tool_agent_template.commands.configure_logging",
        lambda level=None: None,
    )

    class StubRunner:
        def __init__(self, settings) -> None:
            self.settings = settings

        def run(self, request):
            assert request.task_name == demo_task_input["task_name"]
            return _record(status)

    monkeypatch.setattr("databricks_tool_agent_template.commands.AgentRunner", StubRunner)

    result = run_agent_task_command(
        "workspace-config.yml",
        task_input_json=json.dumps(demo_task_input),
    )

    assert result.exit_code == expected_exit_code
    assert result.payload.status == status


def test_run_agent_task_command_requires_exactly_one_task_input_source() -> None:
    with pytest.raises(ValueError, match="exactly one of --task-input-json or --task-input-file"):
        run_agent_task_command(
            "workspace-config.yml",
            task_input_json="{}",
            task_input_file="examples/demo_run_task.json",
        )


def test_run_agent_task_command_requires_current_task_fields(monkeypatch) -> None:
    monkeypatch.setattr(
        "databricks_tool_agent_template.commands.load_settings",
        lambda config_path: SimpleNamespace(log_level="INFO"),
    )
    monkeypatch.setattr(
        "databricks_tool_agent_template.commands.configure_logging",
        lambda level=None: None,
    )

    with pytest.raises(RuntimeError, match="requires task fields: instructions, payload"):
        run_agent_task_command(
            "workspace-config.yml",
            task_input_json='{"task_name":"customer_account_brief"}',
        )


def test_run_evals_command_returns_nonzero_when_report_fails(monkeypatch) -> None:
    configured_levels: list[str | None] = []

    monkeypatch.setattr(
        "databricks_tool_agent_template.commands.load_settings",
        lambda config_path: SimpleNamespace(log_level="DEBUG"),
    )
    monkeypatch.setattr(
        "databricks_tool_agent_template.commands.configure_logging",
        configured_levels.append,
    )
    monkeypatch.setattr(
        "databricks_tool_agent_template.commands.run_evals",
        lambda settings, scenario_file: EvalRunReport(
            scenario_file=scenario_file,
            total_scenarios=1,
            passed_scenarios=0,
            failed_scenarios=1,
            all_passed=False,
            results=[],
        ),
    )

    result = run_evals_command("workspace-config.yml", scenario_file="evals/sample_scenarios.json")

    assert isinstance(result, CommandResult)
    assert result.exit_code == 1
    assert configured_levels == ["DEBUG"]
