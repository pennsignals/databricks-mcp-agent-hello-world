from __future__ import annotations

from pathlib import Path

import pytest

from databricks_mcp_agent_hello_world.evals import harness
from databricks_mcp_agent_hello_world.evals.harness import EvalSetupError
from databricks_mcp_agent_hello_world.models import EvalRunReport
from tests.helpers import make_settings


@pytest.mark.parametrize(
    ("file_name", "content", "message"),
    [
        pytest.param("invalid.json", "{", "Invalid scenario JSON", id="invalid-json"),
        pytest.param("not-list.json", "{}", "top-level JSON list", id="not-list"),
        pytest.param(
            "invalid-scenario.json",
            '[{"scenario_id":"a","description":"x"}]',
            "Invalid scenario file",
            id="invalid-scenario",
        ),
    ],
)
def test_load_eval_scenarios_rejects_invalid_scenario_files(
    tmp_path: Path,
    file_name: str,
    content: str,
    message: str,
) -> None:
    scenario_file = tmp_path / file_name
    scenario_file.write_text(content, encoding="utf-8")

    with pytest.raises(EvalSetupError, match=message):
        harness.load_eval_scenarios(str(scenario_file))


def test_load_eval_scenarios_rejects_missing_scenario_file(tmp_path: Path) -> None:
    with pytest.raises(EvalSetupError, match="Scenario file not found"):
        harness.load_eval_scenarios(str(tmp_path / "missing.json"))


@pytest.mark.parametrize(
    ("file_name", "task_reference", "message"),
    [
        pytest.param("bad-task.json", "../task.json", "Invalid task input JSON", id="bad-task"),
        pytest.param(
            "missing-task.json",
            "../missing-task-input.json",
            "Task input file not found",
            id="missing-task",
        ),
    ],
)
def test_load_eval_scenarios_rejects_invalid_task_file_references(
    tmp_path: Path,
    file_name: str,
    task_reference: str,
    message: str,
) -> None:
    scenario_dir = tmp_path / "evals"
    scenario_dir.mkdir()
    (tmp_path / "task.json").write_text("{", encoding="utf-8")
    scenario_file = scenario_dir / file_name
    scenario_file.write_text(
        f'[{{"scenario_id":"a","description":"x","task_input_file":"{task_reference}"}}]',
        encoding="utf-8",
    )

    with pytest.raises(EvalSetupError, match=message):
        harness.load_eval_scenarios(str(scenario_file))


def test_score_scenario_records_missing_required_output_substrings() -> None:
    scenario = harness.EvalScenario(
        scenario_id="score",
        description="x",
        task_input=harness.AgentTaskRequest(task_name="demo", instructions="hi"),
        required_output_substrings=["required"],
    )
    run_record = harness.AgentRunRecord(
        run_id="run-1",
        task_name="demo",
        status="success",
        result={
            "final_response": "forbidden output",
            "available_tools": ["tool-a"],
            "tool_calls": [{"tool_name": "tool-a", "status": "ok"}],
        },
    )

    scored = harness._score_scenario(scenario, run_record)

    assert scored.failed_checks == ["missing_required_output_substrings"]
    assert scored.missing_required_output_substrings == ["required"]


def test_eval_harness_coerces_malformed_trace_helpers_to_empty_lists() -> None:
    assert harness._as_trace_list("not-a-list") == []


def test_ordered_unique_tools_keeps_first_successful_tool_name_only() -> None:
    assert harness._ordered_unique_tools(
        [
            {"tool_name": "a", "status": "ok"},
            {"tool_name": "a", "status": "ok"},
            {"tool_name": "b", "status": "skipped"},
            {"tool_name": 5, "status": "ok"},
        ],
        statuses={"ok"},
    ) == ["a"]


def test_require_task_input_rejects_scenario_without_embedded_or_file_task() -> None:
    scenario = harness.EvalScenario(
        scenario_id="missing-task",
        description="x",
        task_input=harness.AgentTaskRequest(task_name="demo", instructions="hi"),
    )
    scenario = scenario.model_copy(update={"task_input": None, "task_input_file": None})

    with pytest.raises(EvalSetupError, match="missing task_input"):
        harness._require_task_input(scenario)


def test_write_latest_eval_report_persists_report_under_local_state(tmp_path: Path) -> None:
    report = EvalRunReport(
        scenario_file="scenario.json",
        total_scenarios=0,
        passed_scenarios=0,
        failed_scenarios=0,
        all_passed=True,
        results=[],
    )

    harness._write_latest_eval_report(
        make_settings(storage={"local_data_dir": str(tmp_path)}),
        report,
    )

    assert (tmp_path / "evals" / "latest_eval_report.json").exists()
