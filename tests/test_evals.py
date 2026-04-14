from types import SimpleNamespace

from databricks_mcp_agent_hello_world.evals.harness import (
    EvalSetupError,
    evaluate_record,
    run_eval_scenarios,
)
from databricks_mcp_agent_hello_world.models import EvalScenario


class StubRunner:
    def __init__(self, record):
        self.record = record
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return self.record


class SequencedRunner:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _record(tool_calls=None, blocked_calls=None, final_answer: str = "Hello Ada.") -> dict:
    tool_calls = tool_calls or [
        {"tool_name": "greet_user", "arguments": {"value": "Ada"}, "status": "ok"},
    ]
    return {
        "task_name": "hello_world_demo",
        "available_tools_count": 4,
        "available_tools": [
            "greet_user",
            "search_demo_handbook",
            "get_demo_setting",
            "tell_demo_joke",
        ],
        "allowed_tools": ["greet_user", "search_demo_handbook", "get_demo_setting"],
        "tool_calls": tool_calls,
        "blocked_calls": blocked_calls or [],
        "final_answer": final_answer,
    }


def test_evaluate_record_passes_happy_path_expectations() -> None:
    scenario = EvalScenario(
        scenario_id="hello_world_happy_path",
        task_name="hello_world_demo",
        task_input={"name": "Ada"},
        expected_tool_calls_min=1,
        expected_allowed_tools_subset=[
            "greet_user",
            "search_demo_handbook",
            "get_demo_setting",
        ],
        expected_status="success",
    )

    result = evaluate_record(scenario, _record())

    assert result.status == "pass"


def test_evaluate_record_passes_when_excluded_tool_stays_discovered_but_unused() -> None:
    scenario = EvalScenario(
        scenario_id="allowlist_enforced",
        task_name="hello_world_demo",
        task_input={"name": "Ada"},
        expected_tool_calls_min=1,
        expected_allowed_tools_subset=[
            "greet_user",
            "search_demo_handbook",
            "get_demo_setting",
        ],
        expected_excluded_tools=["tell_demo_joke"],
        expected_status="success",
    )

    result = evaluate_record(scenario, _record(final_answer="Hello Ada, I stayed within the allowlist."))

    assert result.status == "pass"


def test_evaluate_record_fails_when_excluded_tool_appears_in_allowed_tools() -> None:
    scenario = EvalScenario(
        scenario_id="allowlist_enforced",
        task_name="hello_world_demo",
        task_input={"name": "Ada"},
        expected_tool_calls_min=1,
        expected_allowed_tools_subset=["greet_user", "search_demo_handbook", "get_demo_setting"],
        expected_excluded_tools=["tell_demo_joke"],
        expected_status="success",
    )

    result = evaluate_record(
        scenario,
        {
            **_record(),
            "allowed_tools": [
                "greet_user",
                "search_demo_handbook",
                "get_demo_setting",
                "tell_demo_joke",
            ],
        },
    )

    assert result.status == "fail"
    assert "excluded tools must not appear in allowed_tools" in (result.failure_reason or "")


def test_evaluate_record_fails_when_excluded_tool_is_executed() -> None:
    scenario = EvalScenario(
        scenario_id="allowlist_enforced",
        task_name="hello_world_demo",
        task_input={"name": "Ada"},
        expected_tool_calls_min=1,
        expected_allowed_tools_subset=["greet_user", "search_demo_handbook", "get_demo_setting"],
        expected_excluded_tools=["tell_demo_joke"],
        expected_status="success",
    )

    result = evaluate_record(
        scenario,
        _record(
            tool_calls=[
                {"tool_name": "tell_demo_joke", "arguments": {"topic": "Ada"}, "status": "ok"}
            ]
        ),
    )

    assert result.status == "fail"
    assert "excluded tools must not be executed" in (result.failure_reason or "")


def test_evaluate_record_fails_when_excluded_tool_is_attempted_in_blocked_calls() -> None:
    scenario = EvalScenario(
        scenario_id="allowlist_enforced",
        task_name="hello_world_demo",
        task_input={"name": "Ada"},
        expected_tool_calls_min=1,
        expected_allowed_tools_subset=["greet_user", "search_demo_handbook", "get_demo_setting"],
        expected_excluded_tools=["tell_demo_joke"],
        expected_status="success",
    )

    result = evaluate_record(
        scenario,
        _record(
            blocked_calls=[
                {"tool_name": "tell_demo_joke", "arguments": {"topic": "Ada"}, "status": "blocked"}
            ]
        ),
    )

    assert result.status == "fail"
    assert "excluded tools must not be attempted during live evals" in (
        result.failure_reason or ""
    )


def test_evaluate_record_passes_synthetic_guardrail_expectations() -> None:
    scenario = EvalScenario(
        scenario_id="synthetic_guardrail",
        task_name="hello_world_demo",
        task_input={"name": "Ada"},
        expected_tool_calls_min=1,
        expected_allowed_tools_subset=[
            "greet_user",
            "search_demo_handbook",
            "get_demo_setting",
        ],
        expect_blocked_tool=True,
        expected_status="success",
    )

    result = evaluate_record(
        scenario,
        {
            **_record(
                tool_calls=[
                    {"tool_name": "greet_user", "arguments": {"value": "Ada"}, "status": "ok"},
                ],
                final_answer="Hello Ada, I stayed within the allowlist.",
            ),
            "blocked_calls": [
                {"tool_name": "tell_demo_joke", "arguments": {"topic": "Ada"}, "status": "blocked"}
            ],
        },
    )

    assert result.status == "pass"
    assert result.blocked_tools == ["tell_demo_joke"]


def test_evaluate_record_fails_when_tool_calls_fall_outside_allowed_subset() -> None:
    scenario = EvalScenario(
        scenario_id="hello_world_happy_path",
        task_name="hello_world_demo",
        task_input={"name": "Ada"},
        expected_tool_calls_min=1,
        expected_allowed_tools_subset=["greet_user"],
        expected_status="success",
    )

    result = evaluate_record(
        scenario,
        _record(
            tool_calls=[
                {"tool_name": "tell_demo_joke", "arguments": {"topic": "Ada"}, "status": "ok"}
            ]
        ),
    )

    assert result.status == "fail"
    assert "tool calls must stay inside the expected allowed tool subset" in (
        result.failure_reason or ""
    )


def test_run_eval_scenarios_filters_by_scenario_id() -> None:
    scenario = EvalScenario(
        scenario_id="hello_world_happy_path",
        task_name="hello_world_demo",
        task_input={"name": "Ada"},
        expected_tool_calls_min=1,
        expected_allowed_tools_subset=["greet_user"],
        expected_status="success",
    )

    summary = run_eval_scenarios(
        [scenario],
        StubRunner(_record()),
        scenario_id="hello_world_happy_path",
    )

    assert summary.total_scenarios == 1
    assert summary.passed == 1


def test_run_eval_scenarios_rejects_unknown_scenario_id() -> None:
    scenario = EvalScenario(
        scenario_id="hello_world_happy_path",
        task_name="hello_world_demo",
        task_input={"name": "Ada"},
        expected_tool_calls_min=1,
        expected_allowed_tools_subset=["greet_user"],
        expected_status="success",
    )

    try:
        run_eval_scenarios([scenario], StubRunner(_record()), scenario_id="missing")
    except EvalSetupError as exc:
        assert "Scenario not found: missing" in str(exc)
    else:
        raise AssertionError("Expected EvalSetupError for an unknown scenario id")


def test_run_eval_scenarios_tracks_pass_fail_and_error_counts() -> None:
    pass_scenario = EvalScenario(
        scenario_id="happy_path",
        task_name="hello_world_demo",
        task_input={"name": "Ada"},
        expected_tool_calls_min=1,
        expected_allowed_tools_subset=["greet_user", "search_demo_handbook"],
        expected_status="success",
    )
    fail_scenario = EvalScenario(
        scenario_id="tool_minimum",
        task_name="hello_world_demo",
        task_input={"name": "Ada"},
        expected_tool_calls_min=2,
        expected_allowed_tools_subset=["greet_user", "search_demo_handbook"],
        expected_status="success",
    )
    error_scenario = EvalScenario(
        scenario_id="runtime_error",
        task_name="hello_world_demo",
        task_input={"name": "Ada"},
        expected_tool_calls_min=1,
        expected_allowed_tools_subset=["greet_user", "search_demo_handbook"],
        expected_status="success",
    )

    runner = SequencedRunner([_record(), _record(), RuntimeError("boom")])
    summary = run_eval_scenarios([pass_scenario, fail_scenario, error_scenario], runner)

    assert summary.total_scenarios == 3
    assert summary.passed == 1
    assert summary.failed == 1
    assert summary.errored == 1


def test_run_eval_scenarios_passes_task_input_through_to_runner() -> None:
    scenario = EvalScenario(
        scenario_id="allowlist_enforced",
        task_name="hello_world_demo",
        task_input={"name": "Ada", "setting_key": "runtime_target"},
        expected_tool_calls_min=1,
        expected_allowed_tools_subset=["greet_user", "search_demo_handbook"],
        expected_excluded_tools=["tell_demo_joke"],
        expected_status="success",
    )

    runner = StubRunner(
        _record(
            tool_calls=[
                {"tool_name": "greet_user", "arguments": {"value": "Ada"}, "status": "ok"},
            ],
            final_answer="Hello Ada, I stayed within the allowlist.",
        )
    )

    summary = run_eval_scenarios([scenario], runner)

    assert summary.total_scenarios == 1
    assert runner.requests[0].payload["name"] == "Ada"
    assert runner.requests[0].payload["setting_key"] == "runtime_target"
    assert runner.requests[0].task_name == "hello_world_demo"
    assert runner.requests[0].expected_blocked_calls is False
