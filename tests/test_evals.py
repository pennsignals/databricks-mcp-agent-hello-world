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


def _record(
    tool_trace=None,
    blocked_calls=None,
    final_response: str = "## Onboarding Brief\nAda Lovelace",
    task_payload: dict | None = None,
) -> dict:
    tool_trace = tool_trace or [
        {
            "tool_name": "get_user_profile",
            "arguments": {"user_id": "usr_ada_01"},
            "status": "ok",
            "error": None,
        },
        {
            "tool_name": "search_onboarding_docs",
            "arguments": {"query": "local development"},
            "status": "ok",
            "error": None,
        },
        {
            "tool_name": "get_workspace_setting",
            "arguments": {"key": "runtime_target"},
            "status": "ok",
            "error": None,
        },
    ]
    task_payload = task_payload or {"user_id": "usr_ada_01"}
    return {
        "task_name": "workspace_onboarding_brief",
        "status": "success",
        "blocked_calls": blocked_calls or [],
        "result": {
            "final_response": final_response,
            "task_payload": task_payload,
            "available_tools": [
                "get_user_profile",
                "search_onboarding_docs",
                "get_workspace_setting",
                "list_recent_job_runs",
                "create_support_ticket",
            ],
            "allowed_tools": [
                "get_user_profile",
                "search_onboarding_docs",
                "get_workspace_setting",
                "list_recent_job_runs",
            ],
            "tool_trace": tool_trace,
        },
    }


def test_evaluate_record_passes_happy_path_expectations() -> None:
    scenario = EvalScenario(
        scenario_id="happy_path",
        task_name="workspace_onboarding_brief",
        task_input={"user_id": "usr_ada_01"},
        expected_tool_calls_min=3,
        expected_allowed_tools_subset=[
            "get_user_profile",
            "search_onboarding_docs",
            "get_workspace_setting",
        ],
        expected_status="success",
    )

    result = evaluate_record(scenario, _record())

    assert result.status == "pass"


def test_evaluate_record_fails_when_excluded_tool_appears_in_allowed_tools() -> None:
    scenario = EvalScenario(
        scenario_id="allowlist_enforced",
        task_name="workspace_onboarding_brief",
        task_input={"user_id": "usr_ada_01"},
        expected_tool_calls_min=3,
        expected_allowed_tools_subset=[
            "get_user_profile",
            "search_onboarding_docs",
            "get_workspace_setting",
            "list_recent_job_runs",
        ],
        expected_excluded_tools=["create_support_ticket"],
        expected_status="success",
    )

    result = evaluate_record(
        scenario,
        {
            **_record(),
            "result": {
                **_record()["result"],
                "allowed_tools": [
                    "get_user_profile",
                    "search_onboarding_docs",
                    "get_workspace_setting",
                    "list_recent_job_runs",
                    "create_support_ticket",
                ],
            },
        },
    )

    assert result.status == "fail"
    assert "excluded tools must not appear in allowed_tools" in (result.failure_reason or "")


def test_evaluate_record_fails_when_excluded_tool_is_executed() -> None:
    scenario = EvalScenario(
        scenario_id="allowlist_enforced",
        task_name="workspace_onboarding_brief",
        task_input={"user_id": "usr_ada_01"},
        expected_tool_calls_min=1,
        expected_allowed_tools_subset=["get_user_profile"],
        expected_excluded_tools=["create_support_ticket"],
        expected_status="success",
    )

    result = evaluate_record(
        scenario,
        _record(
            tool_trace=[
                {
                    "tool_name": "create_support_ticket",
                    "arguments": {"summary": "Need help"},
                    "status": "ok",
                    "error": None,
                }
            ]
        ),
    )

    assert result.status == "fail"
    assert "excluded tools must not be executed" in (result.failure_reason or "")


def test_evaluate_record_passes_synthetic_guardrail_expectations() -> None:
    scenario = EvalScenario(
        scenario_id="synthetic_guardrail",
        task_name="workspace_onboarding_brief",
        task_input={"user_id": "usr_ada_01"},
        expected_tool_calls_min=3,
        expected_allowed_tools_subset=[
            "get_user_profile",
            "search_onboarding_docs",
            "get_workspace_setting",
        ],
        expect_blocked_tool=True,
        expected_status="success",
    )

    result = evaluate_record(
        scenario,
        _record(
            blocked_calls=[
                {
                    "tool_name": "create_support_ticket",
                    "arguments": {"summary": "Need help"},
                    "status": "blocked",
                    "error": "blocked",
                }
            ]
        ),
    )

    assert result.status == "pass"
    assert result.blocked_tools == ["create_support_ticket"]


def test_run_eval_scenarios_filters_by_scenario_id() -> None:
    scenario = EvalScenario(
        scenario_id="happy_path",
        task_name="workspace_onboarding_brief",
        task_input={"user_id": "usr_ada_01"},
        expected_tool_calls_min=3,
        expected_allowed_tools_subset=[
            "get_user_profile",
            "search_onboarding_docs",
            "get_workspace_setting",
        ],
        expected_status="success",
    )

    summary = run_eval_scenarios([scenario], StubRunner(_record()), scenario_id="happy_path")

    assert summary.total_scenarios == 1
    assert summary.passed == 1


def test_run_eval_scenarios_rejects_unknown_scenario_id() -> None:
    scenario = EvalScenario(
        scenario_id="happy_path",
        task_name="workspace_onboarding_brief",
        task_input={"user_id": "usr_ada_01"},
        expected_tool_calls_min=1,
        expected_allowed_tools_subset=["get_user_profile"],
        expected_status="success",
    )

    try:
        run_eval_scenarios([scenario], StubRunner(_record()), scenario_id="missing")
    except EvalSetupError as exc:
        assert "Scenario not found" in str(exc)
    else:
        raise AssertionError("Expected EvalSetupError")


def test_run_eval_scenarios_handles_runner_exceptions() -> None:
    scenario = EvalScenario(
        scenario_id="happy_path",
        task_name="workspace_onboarding_brief",
        task_input={"user_id": "usr_ada_01"},
        expected_tool_calls_min=1,
        expected_allowed_tools_subset=["get_user_profile"],
        expected_status="success",
    )

    summary = run_eval_scenarios([scenario], SequencedRunner([RuntimeError("boom")]))

    assert summary.errored == 1
    assert summary.results[0].status == "error"
