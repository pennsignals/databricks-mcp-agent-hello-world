from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from types import SimpleNamespace

from ..models import AgentTaskRequest, EvalScenario, EvalScenarioResult, EvalSummary
from ..runner.agent_runner import AgentRunner


def load_eval_scenarios(path: str) -> list[EvalScenario]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [EvalScenario.model_validate(item) for item in data]


def run_eval_scenarios(
    scenarios: list[EvalScenario],
    runner: AgentRunner,
    scenario_id: str | None = None,
) -> EvalSummary:
    if scenario_id is not None:
        scenarios = [scenario for scenario in scenarios if scenario.scenario_id == scenario_id]
    results: list[EvalScenarioResult] = []
    passed = failed = errored = 0
    profile_repo = runner.profile_repo if hasattr(runner, "profile_repo") else None
    active_profile = profile_repo.load_active() if profile_repo is not None else None

    for scenario in scenarios:
        try:
            if scenario.controlled_tool_calls is not None:
                original_llm = runner.llm
                runner.llm = _ScenarioLLM(
                    scenario.controlled_tool_calls,
                    scenario.controlled_final_answer or "Hello Ada, I stayed within the allowlist.",
                )
                try:
                    record = runner.run(
                        AgentTaskRequest(
                            task_name=scenario.task_name,
                            instructions=scenario.instructions,
                            payload=scenario.payload,
                        )
                    )
                finally:
                    runner.llm = original_llm
            else:
                record = runner.run(
                    AgentTaskRequest(
                        task_name=scenario.task_name,
                        instructions=scenario.instructions,
                        payload=scenario.payload,
                    )
                )
            active_profile = profile_repo.load_active() if profile_repo is not None else active_profile
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
    record,
    active_profile=None,
) -> EvalScenarioResult:
    available_tools = _available_tools(record, active_profile)
    allowed_tools = _allowed_tools(record, active_profile)
    disallowed_tools = _disallowed_tools(record, active_profile)
    tool_calls = _tool_calls(record)
    blocked_call_entries = _blocked_calls(record)
    tools_called = [tool["tool_name"] for tool in tool_calls]
    blocked_tools = [tool["tool_name"] for tool in blocked_call_entries]
    final_answer = _final_answer(record)

    failures: list[str] = []
    if scenario.task_name == "hello_world_demo":
        failures.extend(_hello_world_contract_failures(record, available_tools, allowed_tools, tool_calls, final_answer))
    if scenario.expected_available_tool_count is not None:
        if len(available_tools) != scenario.expected_available_tool_count:
            failures.append(
                "expected available tool count "
                f"{scenario.expected_available_tool_count}, got {len(available_tools)}"
            )
    if scenario.expected_allowed_tools is not None:
        if allowed_tools != scenario.expected_allowed_tools:
            failures.append(
                "expected allowed tools "
                f"{scenario.expected_allowed_tools}, got {allowed_tools}"
            )
    if scenario.expected_disallowed_tools is not None:
        if disallowed_tools != scenario.expected_disallowed_tools:
            failures.append(
                "expected disallowed tools "
                f"{scenario.expected_disallowed_tools}, got {disallowed_tools}"
            )
    if scenario.expected_selected_tools is not None:
        if tools_called != scenario.expected_selected_tools:
            failures.append(
                f"expected selected tools {scenario.expected_selected_tools}, got {tools_called}"
            )
    if scenario.expected_tool_calls is not None:
        if tools_called != scenario.expected_tool_calls:
            failures.append(
                f"expected tool calls {scenario.expected_tool_calls}, got {tools_called}"
            )
    if scenario.expected_blocked_tools is not None:
        if blocked_tools != scenario.expected_blocked_tools:
            failures.append(
                f"expected blocked tools {scenario.expected_blocked_tools}, got {blocked_tools}"
            )
    if scenario.expected_failure_mode is not None:
        record_status = _record_value(record, "status")
        if record_status != scenario.expected_failure_mode:
            failures.append(
                f"expected failure mode {scenario.expected_failure_mode}, got {record_status}"
            )
    else:
        record_status = _record_value(record, "status")
        if record_status is not None and record_status not in {"success", "max_steps_exceeded"}:
            failures.append(f"unexpected record status {record_status}")

    if scenario.expected_output_contains:
        for fragment in scenario.expected_output_contains:
            if fragment not in final_answer:
                failures.append(f"missing expected output fragment: {fragment}")
    if scenario.require_final_answer and not final_answer.strip():
        failures.append("expected a non-empty final answer")

    return EvalScenarioResult(
        scenario_id=scenario.scenario_id,
        status="fail" if failures else "pass",
        run_id=_record_value(record, "run_id"),
        tools_called=tools_called,
        blocked_tools=blocked_tools,
        output_excerpt=final_answer[:500] if final_answer else None,
        failure_reason="; ".join(failures) if failures else None,
    )


def _record_value(record: Any, name: str, default=None):
    if hasattr(record, name):
        return getattr(record, name)
    if isinstance(record, dict):
        return record.get(name, default)
    return default


def _record_list(record: Any, *names: str) -> list[Any] | None:
    for name in names:
        value = _record_value(record, name)
        if value is not None:
            return list(value)
    return None


def _normalize_tool_entry(entry: Any) -> dict[str, Any]:
    if hasattr(entry, "model_dump"):
        return dict(entry.model_dump())
    if isinstance(entry, dict):
        return dict(entry)
    return dict(entry)


def _tool_calls(record: Any) -> list[dict[str, Any]]:
    tool_calls = _record_list(record, "tool_calls", "tools_called")
    if tool_calls is not None:
        return [_normalize_tool_entry(item) for item in tool_calls]
    return []


def _blocked_calls(record: Any) -> list[dict[str, Any]]:
    blocked_calls = _record_list(record, "blocked_calls") or []
    if blocked_calls:
        return [_normalize_tool_entry(item) for item in blocked_calls]
    return [
        tool for tool in _tool_calls(record) if tool.get("status") == "blocked"
    ]


def _available_tools(record: Any, active_profile: Any) -> list[str]:
    tools = _record_value(record, "available_tools")
    if tools is not None:
        return list(tools)
    if isinstance(active_profile, list):
        return []
    if active_profile is not None:
        discovered = _record_value(active_profile, "discovered_tools") or []
        return [tool.tool_name for tool in discovered]
    return []


def _allowed_tools(record: Any, active_profile: Any) -> list[str]:
    tools = _record_value(record, "allowed_tools")
    if tools is not None:
        return list(tools)
    if isinstance(active_profile, list):
        return list(active_profile)
    if active_profile is not None:
        return list(_record_value(active_profile, "allowed_tools") or [])
    return []


def _disallowed_tools(record: Any, active_profile: Any) -> list[str]:
    tools = _record_value(record, "disallowed_tools")
    if tools is not None:
        return [
            item["tool_name"] if isinstance(item, dict) else getattr(item, "tool_name", item)
            for item in tools
        ]
    if isinstance(active_profile, list):
        return []
    if active_profile is not None:
        return list(_record_value(active_profile, "disallowed_tools") or [])
    return []


def _final_answer(record: Any) -> str:
    value = _record_value(record, "final_answer")
    if value:
        return str(value)
    result = _record_value(record, "result") or {}
    if isinstance(result, dict):
        return str(result.get("final_answer") or result.get("final_response") or "")
    if hasattr(result, "get"):
        return str(result.get("final_answer") or result.get("final_response") or "")
    return ""


def _hello_world_contract_failures(
    record: Any,
    available_tools: list[str],
    allowed_tools: list[str],
    tool_calls: list[dict[str, Any]],
    final_answer: str,
) -> list[str]:
    failures: list[str] = []
    required_fields = (
        "task_name",
        "available_tools_count",
        "available_tools",
        "allowed_tools",
        "tool_calls",
        "final_answer",
    )
    for field in required_fields:
        if _record_value(record, field) is None:
            failures.append(f"missing required hello-world field: {field}")

    available_tools_count = _record_value(record, "available_tools_count")
    if isinstance(available_tools_count, int):
        if available_tools_count != len(available_tools):
            failures.append(
                "expected available_tools_count to match available_tools length, "
                f"got {available_tools_count} and {len(available_tools)}"
            )
    elif available_tools_count is not None:
        failures.append("available_tools_count must be an integer")

    if not tool_calls:
        failures.append("hello-world demo must call at least one tool")

    if allowed_tools and not set(allowed_tools).issubset(set(available_tools)):
        failures.append("allowed_tools must be a subset of available_tools")

    if tool_calls and allowed_tools:
        disallowed_used = [
            tool["tool_name"] for tool in tool_calls if tool["tool_name"] not in set(allowed_tools)
        ]
        if disallowed_used:
            failures.append(
                "hello-world happy path used disallowed tools: " + ", ".join(disallowed_used)
            )

    if not final_answer.strip():
        failures.append("expected a non-empty final answer")

    return failures


class _ScenarioLLM:
    def __init__(self, controlled_tool_calls: list[dict[str, Any]], final_answer: str):
        self._calls = controlled_tool_calls
        self._final_answer = final_answer
        self._step = 0

    def tool_step(self, messages, tools, tool_choice=None):
        if self._step == 0:
            tool_calls = []
            for index, call in enumerate(self._calls, start=1):
                tool_calls.append(
                    SimpleNamespace(
                        id=f"scenario-call-{index}",
                        function=SimpleNamespace(
                            name=call["tool_name"],
                            arguments=json.dumps(call.get("arguments", {})),
                        ),
                    )
                )
            self._step += 1
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=tool_calls))]
            )
        self._step += 1
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self._final_answer, tool_calls=None)
                )
            ]
        )
