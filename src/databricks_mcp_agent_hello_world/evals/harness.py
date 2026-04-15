from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import Settings
from ..models import AgentRunRecord, AgentTaskRequest, EvalScenario, EvalScenarioResult, EvalSummary
from ..providers.factory import get_tool_provider
from ..runner.agent_runner import AgentRunner
from ..tooling.runtime import set_runtime_settings


class EvalSetupError(RuntimeError):
    pass


def load_eval_scenarios(path: str) -> list[EvalScenario]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [EvalScenario.model_validate(item) for item in data]


def prepare_run_evals(settings: Settings) -> tuple[AgentRunner, Any]:
    set_runtime_settings(settings)

    if not settings.llm_endpoint_name.strip():
        raise EvalSetupError("llm_endpoint_name is required before running live integration evals.")

    try:
        provider = get_tool_provider(settings)
    except Exception as exc:  # noqa: BLE001
        raise EvalSetupError(f"Unable to resolve the configured tool provider: {exc}") from exc

    try:
        tools = provider.list_tools()
    except Exception as exc:  # noqa: BLE001
        raise EvalSetupError(f"Unable to list tools from the configured provider: {exc}") from exc

    if not tools:
        raise EvalSetupError("The configured tool provider returned no tools.")

    try:
        runner = AgentRunner(settings)
    except Exception as exc:  # noqa: BLE001
        raise EvalSetupError(f"Unable to initialize Databricks auth/client: {exc}") from exc

    try:
        active_profile = runner.profile_repo.load_active(settings.active_profile_name)
    except Exception as exc:  # noqa: BLE001
        raise EvalSetupError(
            f"Unable to load active tool profile for profile {settings.active_profile_name!r}: {exc}"
        ) from exc

    if not active_profile:
        raise EvalSetupError(
            "No active tool profile found for profile "
            f"{settings.active_profile_name!r}. Run compile_tool_profile_job first."
        )

    return runner, active_profile


def run_eval_scenarios(
    scenarios: list[EvalScenario],
    runner: AgentRunner,
    scenario_id: str | None = None,
    *,
    active_profile: Any | None = None,
) -> EvalSummary:
    if scenario_id is not None:
        scenarios = [scenario for scenario in scenarios if scenario.scenario_id == scenario_id]
        if not scenarios:
            raise EvalSetupError(f"Scenario not found: {scenario_id}")

    if active_profile is None:
        profile_repo = runner.profile_repo if hasattr(runner, "profile_repo") else None
        if profile_repo is not None:
            try:
                active_profile = profile_repo.load_active(
                    getattr(runner.settings, "active_profile_name", None)
                )
            except Exception:  # noqa: BLE001
                active_profile = None

    results: list[EvalScenarioResult] = []
    passed = failed = errored = 0

    for scenario in scenarios:
        try:
            record = runner.run(_build_task_request(scenario))
            result = evaluate_record(scenario, record, active_profile)
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
    record: AgentRunRecord | dict[str, Any] | Any,
    active_profile: Any | None = None,
) -> EvalScenarioResult:
    result_payload = _result_payload(record)
    tool_calls = _tool_names(_tool_calls(record, result_payload))
    blocked_tools = _tool_names(_blocked_calls(record, result_payload))
    available_tools = _available_tools(record, result_payload, active_profile)
    allowed_tools = _allowed_tools(record, result_payload, active_profile)
    final_response = _final_response(result_payload, record)
    actual_status = _record_status(record)
    expected_allowed_tools = set(scenario.expected_allowed_tools_subset)
    expected_excluded_tools = set(scenario.expected_excluded_tools)

    failures: list[str] = []

    actual_task_name = _record_value(record, "task_name")
    if actual_task_name != scenario.task_name:
        failures.append(f"expected task_name {scenario.task_name!r}, got {actual_task_name!r}")

    if scenario.expected_status == "success" and not final_response.strip():
        failures.append("final_response must not be empty")

    if actual_status != scenario.expected_status:
        failures.append(f"expected status {scenario.expected_status!r}, got {actual_status!r}")

    if len(tool_calls) < scenario.expected_tool_calls_min:
        failures.append(
            "expected at least "
            f"{scenario.expected_tool_calls_min} tool call(s), got {len(tool_calls)}"
        )

    if not expected_allowed_tools.issubset(set(allowed_tools)):
        failures.append(
            "expected allowed tool subset "
            f"{scenario.expected_allowed_tools_subset!r}, got {allowed_tools!r}"
        )

    if not set(tool_calls).issubset(expected_allowed_tools):
        failures.append("tool calls must stay inside the expected allowed tool subset")

    if available_tools and not set(allowed_tools).issubset(set(available_tools)):
        failures.append("allowed tools must be a subset of available tools")

    if expected_excluded_tools:
        excluded_in_allowed = sorted(expected_excluded_tools.intersection(allowed_tools))
        if excluded_in_allowed:
            failures.append(
                "excluded tools must not appear in allowed_tools: "
                f"{excluded_in_allowed!r}"
            )

        excluded_in_tool_calls = sorted(expected_excluded_tools.intersection(tool_calls))
        if excluded_in_tool_calls:
            failures.append(
                "excluded tools must not be executed: "
                f"{excluded_in_tool_calls!r}"
            )

        excluded_in_blocked = sorted(expected_excluded_tools.intersection(blocked_tools))
        if excluded_in_blocked:
            failures.append(
                "excluded tools must not be attempted during live evals: "
                f"{excluded_in_blocked!r}"
            )

    if scenario.expect_blocked_tool:
        if not blocked_tools and actual_status != "blocked":
            failures.append("expected a blocked tool call or blocked task status")
        if blocked_tools and set(blocked_tools).issubset(expected_allowed_tools):
            failures.append("blocked tool calls must fall outside the expected allowed subset")

    return EvalScenarioResult(
        scenario_id=scenario.scenario_id,
        status="fail" if failures else "pass",
        run_id=_record_value(record, "run_id"),
        tools_called=tool_calls,
        blocked_tools=blocked_tools,
        output_excerpt=final_response[:500] if final_response else None,
        failure_reason="; ".join(failures) if failures else None,
    )


def _build_task_request(scenario: EvalScenario) -> AgentTaskRequest:
    task_input = dict(scenario.task_input)
    return AgentTaskRequest(
        task_name=scenario.task_name,
        instructions=_build_task_instructions(
            scenario.task_name,
            task_input,
            expect_blocked_tool=scenario.expect_blocked_tool,
        ),
        payload=task_input,
        expected_blocked_calls=scenario.expect_blocked_tool,
    )


def _build_task_instructions(
    task_name: str,
    task_input: dict[str, Any],
    *,
    expect_blocked_tool: bool,
) -> str:
    payload_json = json.dumps(task_input, indent=2, sort_keys=True)
    blocked_call_hint = (
        "\nA blocked tool call is acceptable if the allowlist prevents it."
        if expect_blocked_tool
        else ""
    )
    return (
        f"Execute the {task_name} task using the supplied task input.\n"
        f"Task input:\n{payload_json}"
        f"{blocked_call_hint}"
    )


def _result_payload(record: AgentRunRecord | dict[str, Any] | Any) -> dict[str, Any]:
    if isinstance(record, AgentRunRecord):
        return dict(record.result)

    result = _record_value(record, "result", {})
    if hasattr(result, "model_dump"):
        return dict(result.model_dump())
    if isinstance(result, dict):
        return dict(result)

    fallback_keys = {"final_response", "task_payload", "available_tools", "allowed_tools", "tool_trace"}
    if isinstance(record, dict) and fallback_keys.intersection(record):
        return {key: record.get(key) for key in fallback_keys if key in record}
    return {}


def _record_status(record: AgentRunRecord | dict[str, Any] | Any) -> str:
    value = _record_value(record, "status")
    return str(value) if value is not None else "unknown"


def _record_value(record: AgentRunRecord | dict[str, Any] | Any, name: str, default=None):
    if hasattr(record, name):
        return getattr(record, name)
    if isinstance(record, dict):
        return record.get(name, default)
    return default


def _normalize_tool_entry(entry: Any) -> dict[str, Any]:
    if hasattr(entry, "model_dump"):
        return dict(entry.model_dump())
    if isinstance(entry, dict):
        return dict(entry)
    return dict(entry)


def _tool_calls(record: AgentRunRecord | dict[str, Any] | Any, result_payload: dict[str, Any]) -> list[dict[str, Any]]:
    tool_trace = result_payload.get("tool_trace")
    if tool_trace is not None:
        return [_normalize_tool_entry(item) for item in tool_trace]

    tools_called = _record_value(record, "tools_called")
    if tools_called is not None:
        return [_normalize_tool_entry(item) for item in tools_called]

    tool_calls = _record_value(record, "tool_calls")
    if tool_calls is not None:
        return [_normalize_tool_entry(item) for item in tool_calls]

    return []


def _blocked_calls(
    record: AgentRunRecord | dict[str, Any] | Any,
    result_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    blocked_calls = _record_value(record, "blocked_calls") or []
    if blocked_calls:
        return [_normalize_tool_entry(item) for item in blocked_calls]
    return [tool for tool in _tool_calls(record, result_payload) if tool.get("status") == "blocked"]


def _tool_names(entries: list[dict[str, Any]]) -> list[str]:
    return [tool["tool_name"] for tool in entries if tool.get("tool_name")]


def _available_tools(
    record: AgentRunRecord | dict[str, Any] | Any,
    result_payload: dict[str, Any],
    active_profile: Any | None,
) -> list[str]:
    tools = result_payload.get("available_tools")
    if tools is not None:
        return list(tools)

    tools = _record_value(record, "available_tools")
    if tools is not None:
        return list(tools)

    if active_profile is not None:
        discovered = _record_value(active_profile, "discovered_tools") or []
        return [
            tool.tool_name if hasattr(tool, "tool_name") else tool["tool_name"]
            for tool in discovered
        ]
    return []


def _allowed_tools(
    record: AgentRunRecord | dict[str, Any] | Any,
    result_payload: dict[str, Any],
    active_profile: Any | None,
) -> list[str]:
    tools = result_payload.get("allowed_tools")
    if tools is not None:
        return list(tools)

    tools = _record_value(record, "allowed_tools")
    if tools is not None:
        return list(tools)

    if active_profile is not None:
        allowed = _record_value(active_profile, "allowed_tools") or []
        return list(allowed)
    return []


def _final_response(
    result_payload: dict[str, Any],
    record: AgentRunRecord | dict[str, Any] | Any,
) -> str:
    value = result_payload.get("final_response")
    if value:
        return str(value)

    value = _record_value(record, "final_response")
    return str(value) if value else ""
