from types import SimpleNamespace

from databricks_mcp_agent_hello_world.evals.harness import evaluate_record, run_eval_scenarios
from databricks_mcp_agent_hello_world.models import EvalScenario


class StubRunner:
    def __init__(self, record):
        self.record = record

    def run(self, request):
        return self.record


def _record(status: str = "success", final_response: str = "hello world"):
    return SimpleNamespace(
        run_id="run-1",
        status=status,
        tools_called=[{"tool_name": "search_incident_kb"}],
        blocked_calls=[],
        result={"final_response": final_response},
    )


def test_evaluate_record_passes_matching_expectations() -> None:
    scenario = EvalScenario(
        scenario_id="s1",
        task_name="demo",
        instructions="run",
        expected_selected_tools=["search_incident_kb"],
        expected_output_contains=["hello"],
    )

    result = evaluate_record(scenario, _record(), ["search_incident_kb"])

    assert result.status == "pass"


def test_run_eval_scenarios_collects_summary() -> None:
    scenario = EvalScenario(
        scenario_id="s1",
        task_name="demo",
        instructions="run",
        expected_selected_tools=["search_incident_kb"],
    )

    summary = run_eval_scenarios([scenario], StubRunner(_record()))

    assert summary.total_scenarios == 1
    assert summary.passed == 1
