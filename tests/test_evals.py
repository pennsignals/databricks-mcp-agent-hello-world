from types import SimpleNamespace

from databricks_mcp_agent_hello_world.evals.harness import evaluate_record, run_eval_scenarios
from databricks_mcp_agent_hello_world.models import (
    EvalScenario,
    HelloWorldDemoResult,
    HelloWorldDisallowedTool,
    HelloWorldToolCall,
)


class StubRunner:
    def __init__(self, record):
        self.record = record
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return self.record


def _record(tool_calls=None, final_answer: str = "Hello Ada.") -> HelloWorldDemoResult:
    tool_calls = tool_calls or [
        HelloWorldToolCall(tool_name="greet_user", arguments={"value": "Ada"}, status="ok"),
        HelloWorldToolCall(
            tool_name="search_demo_handbook",
            arguments={"value": "local setup tip"},
            status="ok",
        ),
        HelloWorldToolCall(
            tool_name="get_demo_setting",
            arguments={"value": "runtime_target"},
            status="ok",
        ),
    ]
    return HelloWorldDemoResult(
        task_name="hello_world_demo",
        available_tools=[
            "greet_user",
            "search_demo_handbook",
            "get_demo_setting",
            "tell_demo_joke",
        ],
        allowed_tools=["greet_user", "search_demo_handbook", "get_demo_setting"],
        disallowed_tools=[
            HelloWorldDisallowedTool(
                tool_name="tell_demo_joke",
                reason="Intentional novelty tool that should stay out of the hello-world flow unless explicitly requested.",
            )
        ],
        tool_calls=tool_calls,
        final_answer=final_answer,
    )


def test_evaluate_record_passes_matching_expectations() -> None:
    scenario = EvalScenario(
        scenario_id="hello_world_happy_path",
        task_name="hello_world_demo",
        instructions="Write the hello-world report.",
        expected_available_tool_count=4,
        expected_allowed_tools=["greet_user", "search_demo_handbook", "get_demo_setting"],
        expected_disallowed_tools=["tell_demo_joke"],
        expected_tool_calls=["greet_user", "search_demo_handbook", "get_demo_setting"],
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
        expected_tool_calls=["tell_demo_joke"],
        expected_blocked_tools=["tell_demo_joke"],
        require_final_answer=True,
    )

    blocked_record = _record(
        tool_calls=[
            HelloWorldToolCall(
                tool_name="tell_demo_joke",
                arguments={"value": "Ada"},
                status="blocked",
            )
        ],
        final_answer="Hello Ada, I stayed within the allowlist.",
    )

    result = evaluate_record(scenario, blocked_record, SimpleNamespace())

    assert result.status == "pass"
    assert result.blocked_tools == ["tell_demo_joke"]


def test_run_eval_scenarios_filters_by_scenario_id() -> None:
    scenario = EvalScenario(
        scenario_id="hello_world_happy_path",
        task_name="hello_world_demo",
        instructions="Write the hello-world report.",
        expected_available_tool_count=4,
        expected_allowed_tools=["greet_user", "search_demo_handbook", "get_demo_setting"],
        expected_disallowed_tools=["tell_demo_joke"],
        require_final_answer=True,
    )

    summary = run_eval_scenarios([scenario], StubRunner(_record()), scenario_id="hello_world_happy_path")

    assert summary.total_scenarios == 1
    assert summary.passed == 1
