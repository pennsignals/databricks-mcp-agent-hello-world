from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from ..config import Settings
from ..models import (
    AgentRunRecord,
    AgentTaskRequest,
    EvalRunReport,
    EvalScenario,
    EvalScenarioResult,
)
from ..runner.agent_runner import AgentRunner


class EvalSetupError(RuntimeError):
    pass


def load_eval_scenarios(path: str) -> list[EvalScenario]:
    scenario_path = Path(path)
    try:
        raw = json.loads(scenario_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EvalSetupError(f"Scenario file not found: {scenario_path}") from exc
    except json.JSONDecodeError as exc:
        raise EvalSetupError(f"Invalid scenario JSON: {scenario_path}") from exc

    if not isinstance(raw, list):
        raise EvalSetupError("Scenario file must contain a top-level JSON list.")

    if not raw:
        raise EvalSetupError("Scenario file must contain at least one scenario.")

    try:
        scenarios = [_load_scenario(item, scenario_path.parent) for item in raw]
    except ValidationError as exc:
        errors = "; ".join(error["msg"] for error in exc.errors())
        raise EvalSetupError(f"Invalid scenario file: {scenario_path}: {errors}") from exc
    except FileNotFoundError as exc:
        raise EvalSetupError(f"Task input file not found: {exc.filename}") from exc
    except json.JSONDecodeError as exc:
        raise EvalSetupError(f"Invalid task input JSON in scenario file: {scenario_path}") from exc
    _ensure_unique_scenario_ids(scenarios)
    return scenarios


def run_evals(settings: Settings, scenario_file: str) -> EvalRunReport:
    scenarios = load_eval_scenarios(scenario_file)
    runner = AgentRunner(settings)
    results: list[EvalScenarioResult] = []

    for scenario in scenarios:
        try:
            run_record = runner.run(_require_task_input(scenario))
            results.append(_score_scenario(scenario, run_record))
        except Exception as exc:
            results.append(_execution_error_result(scenario, exc))

    report = EvalRunReport(
        scenario_file=scenario_file,
        total_scenarios=len(results),
        passed_scenarios=sum(1 for result in results if result.passed),
        failed_scenarios=sum(1 for result in results if not result.passed),
        all_passed=all(result.passed for result in results),
        results=results,
    )
    _write_latest_eval_report(settings, report)
    return report


def _ensure_unique_scenario_ids(scenarios: list[EvalScenario]) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for scenario in scenarios:
        if scenario.scenario_id in seen and scenario.scenario_id not in duplicates:
            duplicates.append(scenario.scenario_id)
        seen.add(scenario.scenario_id)
    if duplicates:
        duplicate_list = ", ".join(duplicates)
        raise EvalSetupError(
            f"Scenario file contains duplicate scenario_id values: {duplicate_list}"
        )


def _load_scenario(raw_scenario: object, scenario_dir: Path) -> EvalScenario:
    scenario = EvalScenario.model_validate(raw_scenario)
    if scenario.task_input_file is None:
        return scenario

    task_input_path = scenario_dir / scenario.task_input_file
    task_input = AgentTaskRequest.model_validate(
        json.loads(task_input_path.read_text(encoding="utf-8"))
    )
    return scenario.model_copy(update={"task_input": task_input, "task_input_file": None})


def _score_scenario(scenario: EvalScenario, run_record: AgentRunRecord) -> EvalScenarioResult:
    task = _require_task_input(scenario)
    result = dict(run_record.result)
    final_response = _as_string(result.get("final_response"))
    available_tools = _as_string_list(result.get("available_tools"))
    tool_calls = _as_trace_list(result.get("tool_calls"))
    executed_tools = _ordered_unique_tools(tool_calls, statuses={"ok", "error"})
    missing_required_executed_tools = [
        tool_name
        for tool_name in scenario.required_executed_tools
        if tool_name not in executed_tools
    ]
    forbidden_executed_tools = [
        tool_name for tool_name in scenario.forbidden_executed_tools if tool_name in executed_tools
    ]
    missing_required_output_substrings = [
        substring
        for substring in scenario.required_output_substrings
        if substring not in final_response
    ]

    failed_checks: list[str] = []
    if run_record.status != scenario.expected_status:
        failed_checks.append("status_mismatch")
    if missing_required_executed_tools:
        failed_checks.append("missing_required_executed_tools")
    if forbidden_executed_tools:
        failed_checks.append("forbidden_executed_tools")
    if missing_required_output_substrings:
        failed_checks.append("missing_required_output_substrings")

    return EvalScenarioResult(
        scenario_id=scenario.scenario_id,
        passed=len(failed_checks) == 0,
        failed_checks=failed_checks,
        expected_status=scenario.expected_status,
        actual_status=run_record.status,
        task_name=task.task_name,
        run_record_id=run_record.run_id,
        available_tools=available_tools,
        executed_tools=executed_tools,
        final_response_excerpt=final_response[:300] if final_response else "",
        missing_required_executed_tools=missing_required_executed_tools,
        forbidden_executed_tools=forbidden_executed_tools,
        missing_required_output_substrings=missing_required_output_substrings,
    )


def _execution_error_result(scenario: EvalScenario, exc: Exception) -> EvalScenarioResult:
    task = _require_task_input(scenario)
    return EvalScenarioResult(
        scenario_id=scenario.scenario_id,
        passed=False,
        failed_checks=["scenario_execution_error"],
        expected_status=scenario.expected_status,
        actual_status=None,
        task_name=task.task_name,
        run_record_id=None,
        available_tools=[],
        executed_tools=[],
        final_response_excerpt="",
        scenario_execution_error_message=str(exc) or None,
    )


def _require_task_input(scenario: EvalScenario) -> AgentTaskRequest:
    if scenario.task_input is None:
        raise EvalSetupError(
            f"Scenario {scenario.scenario_id} is missing task_input after scenario loading."
        )
    return scenario.task_input


def _as_string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _as_trace_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _ordered_unique_tools(
    tool_calls: list[dict[str, object]],
    *,
    statuses: set[str],
) -> list[str]:
    seen: set[str] = set()
    tools: list[str] = []
    for entry in tool_calls:
        tool_name = entry.get("tool_name")
        status = entry.get("status")
        if not isinstance(tool_name, str) or status not in statuses or tool_name in seen:
            continue
        seen.add(tool_name)
        tools.append(tool_name)
    return tools


def _write_latest_eval_report(settings: Settings, report: EvalRunReport) -> None:
    report_path = Path(settings.storage.local_data_dir) / "evals" / "latest_eval_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report.model_dump(), indent=2), encoding="utf-8")
