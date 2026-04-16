import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world.evals.harness import EvalSetupError, load_eval_scenarios, run_evals
from databricks_mcp_agent_hello_world.models import AgentRunRecord, EvalRunReport


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
    return SimpleNamespace(storage=SimpleNamespace(local_data_dir=str(tmp_path)))


def _scenario(
    scenario_id: str = "scenario-1",
    **overrides,
):
    payload = {
        "scenario_id": scenario_id,
        "description": "Demo scenario",
        "task_input": {
            "task_name": "run-task",
            "instructions": "Run the task.",
            "payload": {"user_id": "usr_ada_01"},
        },
    }
    payload.update(overrides)
    return payload


def _record(
    *,
    status: str = "success",
    final_response: str = "Ada Lovelace uses uv sync on Databricks Serverless Jobs.",
    available_tools: list[str] | None = None,
    tool_calls: list[dict] | None = None,
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
    return AgentRunRecord(
        run_id=run_id,
        task_name="run-task",
        status=status,
        result={
            "final_response": final_response,
            "available_tools": available_tools,
            "tool_calls": tool_calls,
        },
    )


def _write_scenarios(tmp_path: Path, scenarios: list[dict]) -> str:
    path = tmp_path / "scenarios.json"
    path.write_text(json.dumps(scenarios, indent=2), encoding="utf-8")
    return str(path)


def _run_report(tmp_path: Path, monkeypatch, scenarios: list[dict], records: list[AgentRunRecord]) -> EvalRunReport:
    StubRunner.instances.clear()
    StubRunner.queued_outcomes = list(records)
    monkeypatch.setattr("databricks_mcp_agent_hello_world.evals.harness.AgentRunner", StubRunner)
    scenario_file = _write_scenarios(tmp_path, scenarios)
    return run_evals(_settings(tmp_path), scenario_file)


def test_load_eval_scenarios_validates_all_eval_fixtures() -> None:
    fixture_dir = Path("tests/fixtures/evals")
    for fixture_path in sorted(fixture_dir.glob("*.json")):
        scenarios = load_eval_scenarios(str(fixture_path))
        assert len(scenarios) == 1


def test_load_eval_scenarios_rejects_duplicate_scenario_ids(tmp_path: Path) -> None:
    scenario_file = _write_scenarios(
        tmp_path,
        [
            _scenario("duplicate"),
            _scenario("duplicate"),
        ],
    )

    with pytest.raises(EvalSetupError, match="duplicate scenario_id"):
        load_eval_scenarios(scenario_file)


def test_run_evals_runs_each_scenario_directly(tmp_path: Path, monkeypatch) -> None:
    report = _run_report(
        tmp_path,
        monkeypatch,
        [
            _scenario("scenario-1"),
            _scenario(
                "scenario-2",
                task_input={
                    "task_name": "run-task-2",
                    "instructions": "Run the second task.",
                    "payload": {"user_id": "usr_grace_01"},
                },
            ),
        ],
        [_record(), _record(run_id="run-456")],
    )

    assert report.total_scenarios == 2
    runner = StubRunner.instances[0]
    assert [call.task_name for call in runner.run_calls] == ["run-task", "run-task-2"]


def test_run_evals_scores_available_tools_from_runner_output(tmp_path: Path, monkeypatch) -> None:
    report = _run_report(
        tmp_path,
        monkeypatch,
        [_scenario(required_available_tools=["alpha", "beta"])],
        [_record(available_tools=["alpha", "beta"])],
    )

    assert report.results[0].available_tools == ["alpha", "beta"]


def test_run_evals_never_performs_its_own_tool_selection(tmp_path: Path, monkeypatch) -> None:
    report = _run_report(
        tmp_path,
        monkeypatch,
        [_scenario(required_available_tools=["expected_tool"])],
        [_record(available_tools=["wrong_tool"])],
    )

    assert report.results[0].passed is False
    assert report.results[0].failed_checks == ["missing_required_available_tools"]
    assert report.results[0].available_tools == ["wrong_tool"]


def test_run_evals_scores_output_substrings_case_sensitively(tmp_path: Path, monkeypatch) -> None:
    report = _run_report(
        tmp_path,
        monkeypatch,
        [
            _scenario("required-pass", required_output_substrings=["Ada"]),
            _scenario("required-fail", required_output_substrings=["ada"]),
            _scenario("forbidden-fail", forbidden_output_substrings=["Ada"]),
        ],
        [
            _record(run_id="run-1"),
            _record(run_id="run-2"),
            _record(run_id="run-3"),
        ],
    )

    assert report.results[0].passed is True
    assert report.results[1].failed_checks == ["missing_required_output_substrings"]
    assert report.results[2].failed_checks == ["forbidden_output_substrings_present"]


def test_run_evals_writes_latest_eval_report_json(tmp_path: Path, monkeypatch) -> None:
    report = _run_report(
        tmp_path,
        monkeypatch,
        [_scenario()],
        [_record()],
    )

    latest_report_path = tmp_path / "evals" / "latest_eval_report.json"
    assert latest_report_path.exists()
    persisted = json.loads(latest_report_path.read_text(encoding="utf-8"))
    assert persisted["total_scenarios"] == 1
    assert persisted["results"][0]["scenario_id"] == report.results[0].scenario_id


def test_run_evals_reports_execution_errors(tmp_path: Path, monkeypatch) -> None:
    StubRunner.instances.clear()
    StubRunner.queued_outcomes = [RuntimeError("boom")]
    monkeypatch.setattr("databricks_mcp_agent_hello_world.evals.harness.AgentRunner", StubRunner)

    report = run_evals(_settings(tmp_path), _write_scenarios(tmp_path, [_scenario()]))

    assert report.results[0].failed_checks == ["scenario_execution_error"]


@pytest.mark.parametrize(
    ("scenario", "record", "expected_failures"),
    [
        (
            _scenario(required_available_tools=["get_user_profile"]),
            _record(available_tools=["get_user_profile"]),
            [],
        ),
        (
            _scenario(required_available_tools=["get_user_profile", "search_onboarding_docs"]),
            _record(available_tools=["get_user_profile"]),
            ["missing_required_available_tools"],
        ),
        (
            _scenario(forbidden_available_tools=["create_support_ticket"]),
            _record(available_tools=["get_user_profile", "create_support_ticket"]),
            ["forbidden_available_tools_present"],
        ),
        (
            _scenario(required_executed_tools=["get_user_profile"]),
            _record(),
            [],
        ),
        (
            _scenario(forbidden_executed_tools=["get_user_profile"]),
            _record(),
            ["forbidden_executed_tools_present"],
        ),
    ],
)
def test_run_evals_scores_tool_expectations(
    tmp_path: Path,
    monkeypatch,
    scenario: dict,
    record: AgentRunRecord,
    expected_failures: list[str],
) -> None:
    report = _run_report(tmp_path, monkeypatch, [scenario], [record])

    assert report.results[0].failed_checks == expected_failures
