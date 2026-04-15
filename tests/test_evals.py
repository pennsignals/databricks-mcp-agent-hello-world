import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world.evals.harness import EvalSetupError, load_eval_scenarios, run_evals
from databricks_mcp_agent_hello_world.models import AgentRunRecord, EvalRunReport


class StubCompiler:
    instances: list["StubCompiler"] = []

    def __init__(self, settings):
        self.settings = settings
        self.compile_calls: list[tuple[object, bool]] = []
        StubCompiler.instances.append(self)

    def compile(self, task, force_refresh=False):
        self.compile_calls.append((task, force_refresh))
        return SimpleNamespace(
            profile=SimpleNamespace(
                profile_name="default",
                profile_version="profile-v1",
                allowed_tools=["stubbed_tool"],
            )
        )


class StubRunner:
    instances: list["StubRunner"] = []
    queued_records: list[AgentRunRecord] = []

    def __init__(self, settings):
        self.settings = settings
        self.run_calls: list[object] = []
        StubRunner.instances.append(self)

    def run(self, task):
        self.run_calls.append(task)
        return self.queued_records.pop(0)


def _settings(tmp_path: Path):
    return SimpleNamespace(storage=SimpleNamespace(local_data_dir=str(tmp_path)))


def _scenario(
    scenario_id: str = "scenario-1",
    **overrides,
):
    payload = {
        "scenario_id": scenario_id,
        "description": "Demo scenario",
        "compile_task_input": {
            "task_name": "compile-task",
            "instructions": "Compile the profile.",
            "payload": {"user_id": "usr_ada_01"},
        },
    }
    payload.update(overrides)
    return payload


def _record(
    *,
    status: str = "success",
    final_response: str = "Ada Lovelace uses uv sync on Databricks Serverless Jobs.",
    allowed_tools: list[str] | None = None,
    tool_trace: list[dict] | None = None,
    run_id: str = "run-123",
    profile_version: str = "profile-v1",
) -> AgentRunRecord:
    allowed_tools = allowed_tools or ["get_user_profile", "search_onboarding_docs"]
    tool_trace = tool_trace or [
        {
            "tool_name": "get_user_profile",
            "arguments": {"user_id": "usr_ada_01"},
            "status": "ok",
            "error": None,
        }
    ]
    return AgentRunRecord(
        run_id=run_id,
        profile_name="default",
        profile_version=profile_version,
        task_name="run-task",
        status=status,
        result={
            "final_response": final_response,
            "allowed_tools": allowed_tools,
            "tool_trace": tool_trace,
        },
    )


def _write_scenarios(tmp_path: Path, scenarios: list[dict]) -> str:
    path = tmp_path / "scenarios.json"
    path.write_text(json.dumps(scenarios, indent=2), encoding="utf-8")
    return str(path)


def _run_report(tmp_path: Path, monkeypatch, scenarios: list[dict], records: list[AgentRunRecord]) -> EvalRunReport:
    StubCompiler.instances.clear()
    StubRunner.instances.clear()
    StubRunner.queued_records = list(records)
    monkeypatch.setattr("databricks_mcp_agent_hello_world.evals.harness.ToolProfileCompiler", StubCompiler)
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


def test_run_evals_compiles_each_scenario_with_force_refresh_true(tmp_path: Path, monkeypatch) -> None:
    report = _run_report(
        tmp_path,
        monkeypatch,
        [
            _scenario("scenario-1"),
            _scenario(
                "scenario-2",
                compile_task_input={
                    "task_name": "compile-task-2",
                    "instructions": "Compile the second profile.",
                    "payload": {"user_id": "usr_grace_01"},
                },
                run_task_input={
                    "task_name": "run-task-2",
                    "instructions": "Run the second task.",
                    "payload": {"user_id": "usr_grace_01"},
                },
            ),
        ],
        [_record(), _record(run_id="run-456")],
    )

    assert report.total_scenarios == 2
    compiler = StubCompiler.instances[0]
    runner = StubRunner.instances[0]
    assert [(call.task_name, force_refresh) for call, force_refresh in compiler.compile_calls] == [
        ("compile-task", True),
        ("compile-task-2", True),
    ]
    assert [call.task_name for call in runner.run_calls] == ["compile-task", "run-task-2"]


def test_run_evals_uses_compiler_output_as_observed_by_runner(tmp_path: Path, monkeypatch) -> None:
    report = _run_report(
        tmp_path,
        monkeypatch,
        [_scenario(required_allowed_tools=["alpha", "beta"])],
        [_record(allowed_tools=["alpha", "beta"])],
    )

    assert report.results[0].allowed_tools == ["alpha", "beta"]


def test_run_evals_never_performs_its_own_tool_selection(tmp_path: Path, monkeypatch) -> None:
    report = _run_report(
        tmp_path,
        monkeypatch,
        [_scenario(required_allowed_tools=["expected_tool"])],
        [_record(allowed_tools=["wrong_tool"])],
    )

    assert report.results[0].passed is False
    assert report.results[0].failed_checks == ["missing_required_allowed_tools"]
    assert report.results[0].allowed_tools == ["wrong_tool"]


@pytest.mark.parametrize(
    ("expect_blocked_tool_calls", "tool_trace", "expected_passed"),
    [
        (
            True,
            [{"tool_name": "create_support_ticket", "arguments": {}, "status": "blocked", "error": "blocked"}],
            True,
        ),
        (
            False,
            [{"tool_name": "create_support_ticket", "arguments": {}, "status": "blocked", "error": "blocked"}],
            False,
        ),
        (
            None,
            [{"tool_name": "create_support_ticket", "arguments": {}, "status": "blocked", "error": "blocked"}],
            True,
        ),
    ],
)
def test_run_evals_scores_blocked_tools_exactly_as_specified(
    tmp_path: Path,
    monkeypatch,
    expect_blocked_tool_calls,
    tool_trace,
    expected_passed: bool,
) -> None:
    report = _run_report(
        tmp_path,
        monkeypatch,
        [_scenario(expect_blocked_tool_calls=expect_blocked_tool_calls)],
        [_record(tool_trace=tool_trace)],
    )

    assert report.results[0].passed is expected_passed


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

    report_path = tmp_path / "evals" / "latest_eval_report.json"
    assert report_path.exists()
    assert json.loads(report_path.read_text(encoding="utf-8")) == report.model_dump()


@pytest.mark.parametrize(
    ("scenario_payload", "record", "expected_failed_checks"),
    [
        (
            json.loads(Path("tests/fixtures/evals/status_mismatch.json").read_text(encoding="utf-8"))[0],
            _record(status="success"),
            ["status_mismatch"],
        ),
        (
            {},
            AgentRunRecord(
                run_id="run-missing-keys",
                profile_name="default",
                profile_version="profile-v1",
                task_name="run-task",
                status="success",
                result={"final_response": "Ada", "allowed_tools": ["get_user_profile"]},
            ),
            ["missing_required_result_keys"],
        ),
        (
            json.loads(Path("tests/fixtures/evals/missing_required_allowed_tool.json").read_text(encoding="utf-8"))[0],
            _record(allowed_tools=["get_user_profile"]),
            ["missing_required_allowed_tools"],
        ),
        (
            json.loads(Path("tests/fixtures/evals/forbidden_allowed_tool_present.json").read_text(encoding="utf-8"))[0],
            _record(allowed_tools=["get_user_profile", "create_support_ticket"]),
            ["forbidden_allowed_tools_present"],
        ),
        (
            {"required_executed_tools": ["search_onboarding_docs"]},
            _record(tool_trace=[{"tool_name": "get_user_profile", "arguments": {}, "status": "ok", "error": None}]),
            ["missing_required_executed_tools"],
        ),
        (
            json.loads(Path("tests/fixtures/evals/forbidden_executed_tool_present.json").read_text(encoding="utf-8"))[0],
            _record(tool_trace=[{"tool_name": "create_support_ticket", "arguments": {}, "status": "ok", "error": None}]),
            ["forbidden_executed_tools_present"],
        ),
        (
            {"min_tool_calls": 2},
            _record(tool_trace=[{"tool_name": "get_user_profile", "arguments": {}, "status": "ok", "error": None}]),
            ["below_min_tool_calls"],
        ),
        (
            {"max_tool_calls": 0},
            _record(tool_trace=[{"tool_name": "get_user_profile", "arguments": {}, "status": "ok", "error": None}]),
            ["above_max_tool_calls"],
        ),
        (
            json.loads(Path("tests/fixtures/evals/blocked_tool_expected_but_missing.json").read_text(encoding="utf-8"))[0],
            _record(tool_trace=[{"tool_name": "get_user_profile", "arguments": {}, "status": "ok", "error": None}]),
            ["blocked_tool_expectation_failed"],
        ),
        (
            json.loads(Path("tests/fixtures/evals/blocked_tool_unexpected.json").read_text(encoding="utf-8"))[0],
            _record(tool_trace=[{"tool_name": "create_support_ticket", "arguments": {}, "status": "blocked", "error": "blocked"}]),
            ["blocked_tool_expectation_failed"],
        ),
        (
            json.loads(Path("tests/fixtures/evals/missing_required_output_substring.json").read_text(encoding="utf-8"))[0],
            _record(final_response="Ada Lovelace"),
            ["missing_required_output_substrings"],
        ),
        (
            {"forbidden_output_substrings": ["Ada"]},
            _record(final_response="Ada Lovelace"),
            ["forbidden_output_substrings_present"],
        ),
    ],
)
def test_run_evals_uses_exact_failed_check_codes(
    tmp_path: Path,
    monkeypatch,
    scenario_payload: dict,
    record: AgentRunRecord,
    expected_failed_checks: list[str],
) -> None:
    report = _run_report(
        tmp_path,
        monkeypatch,
        [_scenario(**scenario_payload)],
        [record],
    )

    assert report.results[0].failed_checks == expected_failed_checks
