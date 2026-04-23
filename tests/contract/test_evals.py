from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import pytest

from databricks_mcp_agent_hello_world.app.data import DEMO_USERS
from databricks_mcp_agent_hello_world.evals.harness import (
    EvalSetupError,
    load_eval_scenarios,
    run_evals,
)
from databricks_mcp_agent_hello_world.models import AgentRunRecord, EvalRunReport
from tests.helpers import make_settings


class StubRunner:
    instances: list["StubRunner"] = []
    queued_outcomes: list[AgentRunRecord | Exception] = []

    def __init__(self, settings):
        self.settings = settings
        self.run_calls: list[object] = []
        StubRunner.instances.append(self)

    def run(self, task):
        self.run_calls.append(task)
        outcome = self.queued_outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _settings(tmp_path: Path):
    return make_settings(storage={"local_data_dir": str(tmp_path)})


def _record(
    *,
    status: Literal["success", "error", "max_steps_exceeded"] = "success",
    final_response: str = (
        "Ada Lovelace uses python3.12 -m venv plus pip on Databricks Serverless Jobs."
    ),
    available_tools: list[str] | None = None,
    tool_calls: list[dict] | None = None,
    result_overrides: dict | None = None,
    run_id: str = "run-123",
) -> AgentRunRecord:
    available_tools = available_tools or ["get_user_profile", "search_onboarding_docs"]
    tool_calls = tool_calls or [
        {
            "tool_name": "get_user_profile",
            "arguments": {"user_id": "usr_ada_01"},
            "status": "ok",
            "error": None,
        }
    ]
    result = {
        "final_response": final_response,
        "available_tools": available_tools,
        "tool_calls": tool_calls,
    }
    if result_overrides:
        result.update(result_overrides)
    return AgentRunRecord(run_id=run_id, task_name="run-task", status=status, result=result)


def _write_scenarios(tmp_path: Path, scenarios: list[dict]) -> str:
    path = tmp_path / "scenarios.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scenarios, indent=2), encoding="utf-8")
    return str(path)


def _run_report(
    tmp_path: Path,
    monkeypatch,
    scenarios: list[dict],
    outcomes: list[AgentRunRecord | Exception],
    *,
    demo_task_input: dict[str, object] | None = None,
) -> EvalRunReport:
    StubRunner.instances.clear()
    StubRunner.queued_outcomes = list(outcomes)
    monkeypatch.setattr("databricks_mcp_agent_hello_world.evals.harness.AgentRunner", StubRunner)
    if demo_task_input is not None:
        examples_dir = tmp_path.parent / "examples"
        examples_dir.mkdir(parents=True, exist_ok=True)
        (examples_dir / "demo_run_task.json").write_text(
            json.dumps(demo_task_input, indent=2),
            encoding="utf-8",
        )
    scenario_file = _write_scenarios(tmp_path, scenarios)
    return run_evals(_settings(tmp_path), scenario_file)


def test_load_eval_scenarios_validates_authored_eval_fixtures(repo_root: Path) -> None:
    fixture_dir = repo_root / "tests" / "fixtures" / "evals"
    for fixture_path in sorted(fixture_dir.glob("*.json")):
        scenarios = load_eval_scenarios(str(fixture_path))
        assert len(scenarios) == 1


def test_load_eval_scenarios_uses_canonical_demo_task_file(repo_root: Path) -> None:
    scenarios = load_eval_scenarios(str(repo_root / "evals" / "sample_scenarios.json"))

    assert scenarios[0].task_input is not None
    assert scenarios[0].task_input_file is None
    assert scenarios[0].task_input.task_name == "workspace_onboarding_brief"
    assert scenarios[0].task_input.payload["required_fields"] == [
        "display_name",
        "setup_recommendation",
        "runtime_target",
        "recent_operational_note",
    ]


def test_file_backed_sample_scenarios_expect_demo_task_display_name(repo_root: Path) -> None:
    scenarios = load_eval_scenarios(str(repo_root / "evals" / "sample_scenarios.json"))

    for scenario in scenarios:
        if scenario.task_input is None:
            continue

        user_id = scenario.task_input.payload.get("user_id")
        if not isinstance(user_id, str):
            continue

        expected_display_name = DEMO_USERS[user_id]["display_name"]
        if expected_display_name in scenario.required_output_substrings:
            continue

        pytest.fail(
            f"Scenario {scenario.scenario_id} must require display name "
            f"{expected_display_name!r} to match its resolved task input."
        )


def test_load_eval_scenarios_resolves_task_input_file_relative_to_scenario_file(
    tmp_path: Path,
    demo_task_input: dict[str, object],
) -> None:
    task_file = tmp_path / "examples" / "task.json"
    task_file.parent.mkdir(parents=True, exist_ok=True)
    task_file.write_text(json.dumps(demo_task_input), encoding="utf-8")
    scenario_file = _write_scenarios(
        tmp_path / "evals",
        [
            {
                "scenario_id": "file-backed",
                "description": "Loads task input from file",
                "task_input_file": "../examples/task.json",
            }
        ],
    )

    scenarios = load_eval_scenarios(scenario_file)

    assert scenarios[0].task_input is not None
    assert scenarios[0].task_input_file is None
    assert scenarios[0].task_input.task_name == demo_task_input["task_name"]


def test_load_eval_scenarios_keeps_inline_task_input_when_authored_inline(
    tmp_path: Path,
    demo_task_input: dict[str, object],
) -> None:
    scenario_file = _write_scenarios(
        tmp_path,
        [
            {
                "scenario_id": "inline",
                "description": "Loads inline task input",
                "task_input": demo_task_input,
            }
        ],
    )

    scenarios = load_eval_scenarios(scenario_file)

    assert scenarios[0].task_input is not None
    assert scenarios[0].task_input_file is None


def test_load_eval_scenarios_rejects_duplicate_scenario_ids(
    tmp_path: Path,
    demo_task_input,
) -> None:
    scenario_file = _write_scenarios(
        tmp_path,
        [
            {"scenario_id": "duplicate", "description": "one", "task_input": demo_task_input},
            {"scenario_id": "duplicate", "description": "two", "task_input": demo_task_input},
        ],
    )

    with pytest.raises(EvalSetupError, match="duplicate scenario_id"):
        load_eval_scenarios(scenario_file)


def test_run_evals_scores_required_and_forbidden_tool_semantics(
    tmp_path: Path,
    monkeypatch,
    demo_task_input: dict[str, object],
) -> None:
    report = _run_report(
        tmp_path,
        monkeypatch,
        [
            {
                "scenario_id": "tools",
                "description": "Checks tool semantics",
                "task_input_file": "../examples/demo_run_task.json",
                "required_available_tools": ["get_user_profile", "create_support_ticket"],
                "forbidden_executed_tools": ["create_support_ticket"],
            }
        ],
        [
            _record(
                available_tools=["get_user_profile", "create_support_ticket"],
                tool_calls=[
                    {
                        "tool_name": "get_user_profile",
                        "arguments": {"user_id": "usr_ada_01"},
                        "status": "ok",
                        "error": None,
                    }
                ],
            )
        ],
        demo_task_input=demo_task_input,
    )

    assert report.results[0].passed is True
    assert report.results[0].available_tools == ["get_user_profile", "create_support_ticket"]
    assert report.results[0].executed_tools == ["get_user_profile"]


def test_run_evals_marks_status_mismatch_and_missing_output_substrings(
    tmp_path: Path,
    monkeypatch,
    demo_task_input: dict[str, object],
) -> None:
    report = _run_report(
        tmp_path,
        monkeypatch,
        [
            {
                "scenario_id": "status-mismatch",
                "description": "Requires success with specific output",
                "task_input_file": "../examples/demo_run_task.json",
                "required_output_substrings": ["Databricks Serverless Jobs"],
            }
        ],
        [_record(status="error", final_response="short")],
        demo_task_input=demo_task_input,
    )

    assert report.results[0].passed is False
    assert set(report.results[0].failed_checks) == {
        "status_mismatch",
        "missing_required_output_substrings",
    }
    assert report.results[0].missing_required_output_substrings == ["Databricks Serverless Jobs"]
    assert report.results[0].final_response_excerpt == "short"
    assert report.results[0].actual_result_keys == [
        "available_tools",
        "final_response",
        "tool_calls",
    ]


def test_run_evals_records_detailed_failure_diagnostics(
    tmp_path: Path,
    monkeypatch,
    demo_task_input: dict[str, object],
) -> None:
    report = _run_report(
        tmp_path,
        monkeypatch,
        [
            {
                "scenario_id": "diagnostics",
                "description": "Captures detailed scoring diagnostics",
                "task_input_file": "../examples/demo_run_task.json",
                "required_available_tools": ["get_user_profile", "list_recent_job_runs"],
                "forbidden_available_tools": ["create_support_ticket"],
                "required_executed_tools": ["list_recent_job_runs"],
                "forbidden_executed_tools": ["create_support_ticket"],
                "required_result_keys": [
                    "final_response",
                    "available_tools",
                    "tool_calls",
                    "summary_markdown",
                ],
                "required_output_substrings": ["Grace Hopper"],
                "forbidden_output_substrings": ["Ada Lovelace"],
                "min_tool_calls": 2,
                "max_tool_calls": 2,
            }
        ],
        [
            _record(
                final_response="Ada Lovelace uses python3.12 -m venv plus pip.",
                available_tools=["get_user_profile", "create_support_ticket"],
                tool_calls=[
                    {
                        "tool_name": "create_support_ticket",
                        "arguments": {"summary": "bad"},
                        "status": "ok",
                        "error": None,
                    }
                ],
            )
        ],
        demo_task_input=demo_task_input,
    )

    result = report.results[0]

    assert result.passed is False
    assert set(result.failed_checks) == {
        "missing_required_result_keys",
        "missing_required_available_tools",
        "forbidden_available_tools_present",
        "missing_required_executed_tools",
        "forbidden_executed_tools_present",
        "below_min_tool_calls",
        "missing_required_output_substrings",
        "forbidden_output_substrings_present",
    }
    assert result.missing_required_result_keys == ["summary_markdown"]
    assert result.actual_result_keys == ["available_tools", "final_response", "tool_calls"]
    assert result.missing_required_available_tools == ["list_recent_job_runs"]
    assert result.present_forbidden_available_tools == ["create_support_ticket"]
    assert result.missing_required_executed_tools == ["list_recent_job_runs"]
    assert result.present_forbidden_executed_tools == ["create_support_ticket"]
    assert result.missing_required_output_substrings == ["Grace Hopper"]
    assert result.found_forbidden_output_substrings == ["Ada Lovelace"]
    assert result.expected_min_tool_calls == 2
    assert result.expected_max_tool_calls == 2
    assert result.tool_call_count == 1


def test_run_evals_records_execution_error_message(
    tmp_path: Path,
    monkeypatch,
    demo_task_input: dict[str, object],
) -> None:
    report = _run_report(
        tmp_path,
        monkeypatch,
        [
            {
                "scenario_id": "execution-error",
                "description": "Execution error is surfaced in diagnostics",
                "task_input_file": "../examples/demo_run_task.json",
            }
        ],
        [RuntimeError("LLM unavailable")],
        demo_task_input=demo_task_input,
    )

    result = report.results[0]

    assert result.passed is False
    assert result.failed_checks == ["scenario_execution_error"]
    assert result.scenario_execution_error_message == "LLM unavailable"
