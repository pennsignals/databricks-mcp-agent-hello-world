from __future__ import annotations

import json
from pathlib import Path

from ..models import AgentTaskRequest, EvalScenario, EvalScenarioResult, EvalSummary
from ..runner.agent_runner import AgentRunner


def load_eval_scenarios(path: str) -> list[EvalScenario]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [EvalScenario.model_validate(item) for item in data]


def run_eval_scenarios(scenarios: list[EvalScenario], runner: AgentRunner) -> EvalSummary:
    results: list[EvalScenarioResult] = []
    passed = failed = errored = 0
    profile_repo = runner.profile_repo if hasattr(runner, "profile_repo") else None
    active_profile = profile_repo.load_active() if profile_repo is not None else None

    for scenario in scenarios:
        try:
            record = runner.run(
                AgentTaskRequest(
                    task_name=scenario.task_name,
                    instructions=scenario.instructions,
                    payload=scenario.payload,
                )
            )
            result = evaluate_record(
                scenario,
                record,
                active_profile.allowed_tools if active_profile else None,
            )
        except Exception as exc:  # noqa: BLE001
            result = EvalScenarioResult(
                scenario_id=scenario.scenario_id,
                status="error",
                failure_reason=str(exc),
            )

        results.append(result)
        if result.status == "pass":
            passed += 1
        elif result.status == "fail":
            failed += 1
        else:
            errored += 1

    return EvalSummary(
        total_scenarios=len(scenarios),
        passed=passed,
        failed=failed,
        errored=errored,
        results=results,
    )


def evaluate_record(
    scenario: EvalScenario,
    record,
    active_allowed_tools: list[str] | None = None,
) -> EvalScenarioResult:
    tools_called = [tool["tool_name"] for tool in record.tools_called]
    blocked_tools = [tool["tool_name"] for tool in record.blocked_calls]
    final_response = record.result.get("final_response", "")

    failures: list[str] = []
    if scenario.expected_allowed_tools is not None:
        if active_allowed_tools != scenario.expected_allowed_tools:
            failures.append(
                "expected allowed tools "
                f"{scenario.expected_allowed_tools}, got {active_allowed_tools}"
            )
    if scenario.expected_selected_tools is not None:
        if tools_called != scenario.expected_selected_tools:
            failures.append(
                f"expected selected tools {scenario.expected_selected_tools}, got {tools_called}"
            )
    if scenario.expected_failure_mode is not None:
        if record.status != scenario.expected_failure_mode:
            failures.append(
                f"expected failure mode {scenario.expected_failure_mode}, got {record.status}"
            )
    elif record.status not in {"success", "max_steps_exceeded"}:
        failures.append(f"unexpected record status {record.status}")

    if scenario.expected_output_contains:
        for fragment in scenario.expected_output_contains:
            if fragment not in final_response:
                failures.append(f"missing expected output fragment: {fragment}")

    return EvalScenarioResult(
        scenario_id=scenario.scenario_id,
        status="fail" if failures else "pass",
        run_id=record.run_id,
        tools_called=tools_called,
        blocked_tools=blocked_tools,
        output_excerpt=final_response[:500] if final_response else None,
        failure_reason="; ".join(failures) if failures else None,
    )
