from types import SimpleNamespace

from databricks_mcp_agent_hello_world.evals.harness import evaluate_record, run_eval_scenarios
from databricks_mcp_agent_hello_world.models import EvalScenario


class StubRunner:
    def __init__(self, record):
        self.record = record
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return self.record


def _record(tool_calls=None, final_answer: str = "Hello Ada.") -> dict:
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
        "disallowed_tools": ["tell_demo_joke"],
        "tool_calls": tool_calls,
        "final_answer": final_answer,
    }


def test_evaluate_record_passes_matching_expectations() -> None:
    scenario = EvalScenario(
        scenario_id="hello_world_happy_path",
        task_name="hello_world_demo",
        instructions="Write the hello-world report.",
        expected_available_tool_count=4,
        expected_allowed_tools=["greet_user", "search_demo_handbook", "get_demo_setting"],
        expected_tool_calls=["greet_user"],
        require_final_answer=True,
    )

    result = evaluate_record(scenario, _record(), SimpleNamespace())

    assert result.status == "pass"


def test_evaluate_record_flags_blocked_attempt() -> None:
    scenario = EvalScenario(
        scenario_id="allowlist_enforced",
        task_name="hello_world_demo",
        instructions="Try to use the joke tool.",
        expected_allowed_tools=["greet_user", "search_demo_handbook", "get_demo_setting"],
        expected_disallowed_tools=["tell_demo_joke"],
        expected_tool_calls=["greet_user"],
        expected_blocked_tools=["tell_demo_joke"],
        require_final_answer=True,
    )

    blocked_record = _record(
        tool_calls=[
            {"tool_name": "greet_user", "arguments": {"value": "Ada"}, "status": "ok"},
        ],
        final_answer="Hello Ada, I stayed within the allowlist.",
    )

    result = evaluate_record(
        scenario,
        {
            **blocked_record,
            "blocked_calls": [
                {"tool_name": "tell_demo_joke", "arguments": {"value": "Ada"}, "status": "blocked"}
            ],
        },
        SimpleNamespace(),
    )

    assert result.status == "pass"
    assert result.blocked_tools == ["tell_demo_joke"]


def test_evaluate_record_fails_when_hello_world_has_zero_tool_calls() -> None:
    scenario = EvalScenario(
        scenario_id="hello_world_happy_path",
        task_name="hello_world_demo",
        instructions="Write the hello-world report.",
        expected_available_tool_count=4,
        expected_allowed_tools=["greet_user", "search_demo_handbook", "get_demo_setting"],
        require_final_answer=True,
    )

    result = evaluate_record(
        scenario,
        {
            "task_name": "hello_world_demo",
            "available_tools_count": 4,
            "available_tools": [
                "greet_user",
                "search_demo_handbook",
                "get_demo_setting",
                "tell_demo_joke",
            ],
            "allowed_tools": ["greet_user", "search_demo_handbook", "get_demo_setting"],
            "tool_calls": [],
            "final_answer": "Hello Ada.",
        },
        SimpleNamespace(),
    )

    assert result.status == "fail"
    assert "hello-world demo must call at least one tool" in (result.failure_reason or "")


def test_run_eval_scenarios_filters_by_scenario_id() -> None:
    scenario = EvalScenario(
        scenario_id="hello_world_happy_path",
        task_name="hello_world_demo",
        instructions="Write the hello-world report.",
        expected_available_tool_count=4,
        expected_allowed_tools=["greet_user", "search_demo_handbook", "get_demo_setting"],
        require_final_answer=True,
    )

    summary = run_eval_scenarios([scenario], StubRunner(_record()), scenario_id="hello_world_happy_path")

    assert summary.total_scenarios == 1
    assert summary.passed == 1


def test_run_eval_scenarios_marks_blocking_eval_requests() -> None:
    scenario = EvalScenario(
        scenario_id="allowlist_enforced",
        task_name="hello_world_demo",
        instructions="Try to use the joke tool.",
        expected_allowed_tools=["greet_user", "search_demo_handbook", "get_demo_setting"],
        expected_disallowed_tools=["tell_demo_joke"],
        expected_tool_calls=["greet_user"],
        expected_blocked_tools=["tell_demo_joke"],
        require_final_answer=True,
    )

    runner = StubRunner(
        {
            **_record(
                tool_calls=[
                    {"tool_name": "greet_user", "arguments": {"value": "Ada"}, "status": "ok"},
                ],
                final_answer="Hello Ada, I stayed within the allowlist.",
            ),
            "blocked_calls": [
                {"tool_name": "tell_demo_joke", "arguments": {"value": "Ada"}, "status": "blocked"}
            ],
        }
    )

    summary = run_eval_scenarios([scenario], runner)

    assert summary.total_scenarios == 1
    assert runner.requests[0].expected_blocked_calls is True


def test_run_eval_scenarios_leaves_happy_path_requests_unflagged() -> None:
    scenario = EvalScenario(
        scenario_id="hello_world_happy_path",
        task_name="hello_world_demo",
        instructions="Write the hello-world report.",
        expected_available_tool_count=4,
        expected_allowed_tools=["greet_user", "search_demo_handbook", "get_demo_setting"],
        expected_tool_calls=["greet_user"],
        require_final_answer=True,
    )

    runner = StubRunner(_record())

    summary = run_eval_scenarios([scenario], runner)

    assert summary.total_scenarios == 1
    assert runner.requests[0].expected_blocked_calls is False
