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

    try:
        scenarios = [_load_scenario(item, scenario_path.parent) for item in raw]
    except ValidationError as exc:
        errors = "; ".join(error["msg"] for error in exc.errors())
        raise EvalSetupError(f"Invalid scenario file: {scenario_path}: {errors}") from exc
    except FileNotFoundError as exc:
        raise EvalSetupError(f"Task input file not found: {exc.filename}") from exc
    except json.JSONDecodeError as exc:
        raise EvalSetupError(f"Invalid task input JSON in scenario file: {scenario_path}") from exc
    _ensure_unique_scenario_ids(scenarios, scenario_path)
    return scenarios


def run_evals(settings: Settings, scenario_file: str) -> EvalRunReport:
    scenarios = load_eval_scenarios(scenario_file)
    runner = AgentRunner(settings)
    results: list[EvalScenarioResult] = []

    for scenario in scenarios:
        try:
            run_record = runner.run(scenario.task_input)
            results.append(_score_scenario(scenario, run_record))
        except Exception:  # noqa: BLE001
            results.append(_execution_error_result(scenario))

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


def _ensure_unique_scenario_ids(scenarios: list[EvalScenario], scenario_path: Path) -> None:
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
    result = dict(run_record.result)
    final_response = _as_string(result.get("final_response"))
    available_tools = _as_string_list(result.get("available_tools"))
    tool_calls = _as_trace_list(result.get("tool_calls"))
    # The eval harness validates runtime behavior only. The model chooses tools
    # from the discovered inventory during each run.
    tool_call_count = len(tool_calls)
    executed_tools = _ordered_unique_tools(tool_calls, statuses={"ok", "error"})
    missing_result_keys = [key for key in scenario.required_result_keys if key not in result]

    failed_checks: list[str] = []
    if run_record.status != scenario.expected_status:
        failed_checks.append("status_mismatch")
    if missing_result_keys:
        failed_checks.append("missing_required_result_keys")
    if not all(tool_name in available_tools for tool_name in scenario.required_available_tools):
        failed_checks.append("missing_required_available_tools")
    if any(tool_name in available_tools for tool_name in scenario.forbidden_available_tools):
        failed_checks.append("forbidden_available_tools_present")
    if not all(tool_name in executed_tools for tool_name in scenario.required_executed_tools):
        failed_checks.append("missing_required_executed_tools")
    if any(tool_name in executed_tools for tool_name in scenario.forbidden_executed_tools):
        failed_checks.append("forbidden_executed_tools_present")
    if scenario.min_tool_calls is not None and tool_call_count < scenario.min_tool_calls:
        failed_checks.append("below_min_tool_calls")
    if scenario.max_tool_calls is not None and tool_call_count > scenario.max_tool_calls:
        failed_checks.append("above_max_tool_calls")
    if not all(substring in final_response for substring in scenario.required_output_substrings):
        failed_checks.append("missing_required_output_substrings")
    if any(substring in final_response for substring in scenario.forbidden_output_substrings):
        failed_checks.append("forbidden_output_substrings_present")

    return EvalScenarioResult(
        scenario_id=scenario.scenario_id,
        passed=len(failed_checks) == 0,
        failed_checks=failed_checks,
        expected_status=scenario.expected_status,
        actual_status=run_record.status,
        available_tools=available_tools,
        executed_tools=executed_tools,
        tool_call_count=tool_call_count,
        final_response_excerpt=final_response[:300] if final_response else "",
        task_name=scenario.task_input.task_name,
        run_record_id=run_record.run_id,
    )


def _execution_error_result(scenario: EvalScenario) -> EvalScenarioResult:
    return EvalScenarioResult(
        scenario_id=scenario.scenario_id,
        passed=False,
        failed_checks=["scenario_execution_error"],
        expected_status=scenario.expected_status,
        actual_status=None,
        available_tools=[],
        executed_tools=[],
        tool_call_count=0,
        final_response_excerpt="",
        task_name=scenario.task_input.task_name,
        run_record_id=None,
    )


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
