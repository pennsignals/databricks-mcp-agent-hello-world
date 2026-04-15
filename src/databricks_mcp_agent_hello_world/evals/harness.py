from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from ..config import Settings
from ..models import AgentRunRecord, EvalRunReport, EvalScenario, EvalScenarioResult
from ..profiles.compiler import ToolProfileCompiler
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
        scenarios = [EvalScenario.model_validate(item) for item in raw]
    except ValidationError as exc:
        raise EvalSetupError(f"Invalid scenario file: {scenario_path}") from exc
    _ensure_unique_scenario_ids(scenarios, scenario_path)
    return scenarios


def run_evals(settings: Settings, scenario_file: str) -> EvalRunReport:
    scenarios = load_eval_scenarios(scenario_file)
    compiler = ToolProfileCompiler(settings)
    runner = AgentRunner(settings)
    results: list[EvalScenarioResult] = []

    for scenario in scenarios:
        compiler.compile(task=scenario.compile_task_input, force_refresh=True)
        run_task = scenario.run_task_input or scenario.compile_task_input
        run_record = runner.run(run_task)
        results.append(_score_scenario(scenario, run_record))

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


def _score_scenario(scenario: EvalScenario, run_record: AgentRunRecord) -> EvalScenarioResult:
    result = dict(run_record.result)
    final_response = _as_string(result.get("final_response"))
    allowed_tools = _as_string_list(result.get("allowed_tools"))
    tool_trace = _as_trace_list(result.get("tool_trace"))
    tool_call_count = len(tool_trace)
    executed_tools = _ordered_unique_tools(tool_trace, statuses={"ok", "error"})
    blocked_tools = _ordered_unique_tools(tool_trace, statuses={"blocked"})
    missing_result_keys = [key for key in scenario.required_result_keys if key not in result]

    failed_checks: list[str] = []

    if run_record.status != scenario.expected_status:
        failed_checks.append("status_mismatch")
    if missing_result_keys:
        failed_checks.append("missing_required_result_keys")
    if not all(tool_name in allowed_tools for tool_name in scenario.required_allowed_tools):
        failed_checks.append("missing_required_allowed_tools")
    if any(tool_name in allowed_tools for tool_name in scenario.forbidden_allowed_tools):
        failed_checks.append("forbidden_allowed_tools_present")
    if not all(tool_name in executed_tools for tool_name in scenario.required_executed_tools):
        failed_checks.append("missing_required_executed_tools")
    if any(tool_name in executed_tools for tool_name in scenario.forbidden_executed_tools):
        failed_checks.append("forbidden_executed_tools_present")
    if scenario.min_tool_calls is not None and tool_call_count < scenario.min_tool_calls:
        failed_checks.append("below_min_tool_calls")
    if scenario.max_tool_calls is not None and tool_call_count > scenario.max_tool_calls:
        failed_checks.append("above_max_tool_calls")
    if (
        scenario.expect_blocked_tool_calls is True
        and not blocked_tools
        or scenario.expect_blocked_tool_calls is False
        and bool(blocked_tools)
    ):
        failed_checks.append("blocked_tool_expectation_failed")
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
        allowed_tools=allowed_tools,
        executed_tools=executed_tools,
        blocked_tools=blocked_tools,
        tool_call_count=tool_call_count,
        final_response_excerpt=final_response[:300] if final_response else "",
        compile_task_name=scenario.compile_task_input.task_name,
        run_task_name=(scenario.run_task_input or scenario.compile_task_input).task_name,
        run_record_id=run_record.run_id,
        profile_version=run_record.profile_version,
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
    tool_trace: list[dict[str, object]],
    *,
    statuses: set[str],
) -> list[str]:
    seen: set[str] = set()
    tools: list[str] = []
    for entry in tool_trace:
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
