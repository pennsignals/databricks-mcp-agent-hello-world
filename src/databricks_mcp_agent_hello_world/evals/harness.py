from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import Settings
from ..models import AgentTaskRequest, EvalScenario, EvalScenarioResult, EvalSummary, HelloWorldDemoResult
from ..providers.factory import get_tool_provider
from ..profiles.compiler import build_hello_world_demo_task
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
    record: Any,
    active_profile: Any | None = None,
) -> EvalScenarioResult:
    structured = _structured_result(record)
    tool_calls = _tool_names(_tool_calls(record, structured))
    blocked_tools = _tool_names(_blocked_calls(record))
    available_tools = _available_tools(record, structured, active_profile)
    allowed_tools = _allowed_tools(record, structured, active_profile)
    final_answer = _final_answer(record, structured)
    actual_status = _record_status(record, structured)
    expected_allowed_tools = set(scenario.expected_allowed_tools_subset)
    expected_excluded_tools = set(scenario.expected_excluded_tools)

    failures: list[str] = []
    if structured is not None:
        if structured.task_name != scenario.task_name:
            failures.append(
                f"expected task_name {scenario.task_name!r}, got {structured.task_name!r}"
            )
        if structured.available_tools_count != len(structured.available_tools):
            failures.append("available_tools_count must match available_tools length")
        if scenario.expected_status == "success" and not structured.final_answer.strip():
            failures.append("final_answer must not be empty")
    elif scenario.expected_status == "success":
        failures.append("missing structured hello-world result")

    if actual_status != scenario.expected_status:
        failures.append(
            f"expected status {scenario.expected_status!r}, got {actual_status!r}"
        )

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
        failures.append(
            "tool calls must stay inside the expected allowed tool subset"
        )

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
        output_excerpt=final_answer[:500] if final_answer else None,
        failure_reason="; ".join(failures) if failures else None,
    )


def _build_task_request(scenario: EvalScenario) -> AgentTaskRequest:
    task_input = dict(scenario.task_input)
    instructions = _build_task_instructions(
        scenario.task_name,
        task_input,
        expect_blocked_tool=scenario.expect_blocked_tool,
    )
    payload = task_input
    if scenario.task_name == "hello_world_demo":
        demo_task = build_hello_world_demo_task()
        payload = {**demo_task.payload, **task_input}

    return AgentTaskRequest(
        task_name=scenario.task_name,
        instructions=instructions,
        payload=payload,
        expected_blocked_calls=scenario.expect_blocked_tool,
    )


def _build_task_instructions(
    task_name: str,
    task_input: dict[str, Any],
    *,
    expect_blocked_tool: bool,
) -> str:
    if task_name == "hello_world_demo":
        demo_task = build_hello_world_demo_task()
        if expect_blocked_tool:
            return (
                "Write the hello-world demo using the provided task input. "
                "Try the joke tool if you think it helps, even if the allowlist blocks it."
            )
        return demo_task.instructions

    payload_json = json.dumps(task_input, indent=2, sort_keys=True)
    return (
        f"Execute the {task_name} task using the supplied task input.\n"
        f"Task input:\n{payload_json}"
    )


def _structured_result(record: Any) -> HelloWorldDemoResult | None:
    candidates: list[Any] = []
    if isinstance(record, HelloWorldDemoResult):
        candidates.append(record)
    elif isinstance(record, dict):
        candidates.append(record)
        result = record.get("result")
        if result is not None:
            candidates.append(result)
    else:
        candidates.append(_record_value(record, "result"))
        if hasattr(record, "model_dump"):
            candidates.append(record.model_dump())

    for candidate in candidates:
        if candidate is None:
            continue
        if hasattr(candidate, "model_dump"):
            candidate = candidate.model_dump()
        if isinstance(candidate, dict):
            try:
                return HelloWorldDemoResult.model_validate(candidate)
            except Exception:  # noqa: BLE001
                continue
    return None


def _record_status(record: Any, structured: HelloWorldDemoResult | None = None) -> str:
    value = _record_value(record, "status")
    if value is not None:
        return str(value)

    result = _record_value(record, "result")
    if isinstance(result, dict):
        nested_status = result.get("status")
        if nested_status is not None:
            return str(nested_status)

    if structured is not None:
        return "success"
    return "unknown"


def _record_value(record: Any, name: str, default=None):
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


def _tool_calls(record: Any, structured: HelloWorldDemoResult | None = None) -> list[dict[str, Any]]:
    if structured is not None:
        return [_normalize_tool_entry(item) for item in structured.tool_calls]

    tool_calls = _record_value(record, "tool_calls")
    if tool_calls is not None:
        return [_normalize_tool_entry(item) for item in tool_calls]

    tools_called = _record_value(record, "tools_called")
    if tools_called is not None:
        return [_normalize_tool_entry(item) for item in tools_called]

    return []


def _blocked_calls(record: Any) -> list[dict[str, Any]]:
    blocked_calls = _record_value(record, "blocked_calls") or []
    if blocked_calls:
        return [_normalize_tool_entry(item) for item in blocked_calls]
    return [tool for tool in _tool_calls(record) if tool.get("status") == "blocked"]


def _tool_names(entries: list[dict[str, Any]]) -> list[str]:
    return [tool["tool_name"] for tool in entries if tool.get("tool_name")]


def _available_tools(
    record: Any,
    structured: HelloWorldDemoResult | None,
    active_profile: Any | None,
) -> list[str]:
    if structured is not None:
        return list(structured.available_tools)

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
    record: Any,
    structured: HelloWorldDemoResult | None,
    active_profile: Any | None,
) -> list[str]:
    if structured is not None:
        return list(structured.allowed_tools)

    tools = _record_value(record, "allowed_tools")
    if tools is not None:
        return list(tools)

    if active_profile is not None:
        allowed = _record_value(active_profile, "allowed_tools") or []
        return list(allowed)

    return []


def _final_answer(record: Any, structured: HelloWorldDemoResult | None) -> str:
    if structured is not None:
        return structured.final_answer

    value = _record_value(record, "final_answer")
    if value:
        return str(value)

    result = _record_value(record, "result") or {}
    if isinstance(result, dict):
        return str(result.get("final_answer") or result.get("final_response") or "")
    if hasattr(result, "get"):
        return str(result.get("final_answer") or result.get("final_response") or "")
    return ""
