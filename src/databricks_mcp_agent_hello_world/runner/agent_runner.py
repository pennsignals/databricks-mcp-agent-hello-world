from __future__ import annotations

import json
import logging
from typing import Any

from ..config import Settings
from ..executors import get_tool_executor
from ..llm_client import DatabricksLLM
from ..models import (
    AgentOutputRecord,
    AgentRunRecord,
    AgentTaskRequest,
    ToolCall,
    ToolProfile,
    ToolResult,
)
from ..profiles.repository import ToolProfileRepository
from ..storage.result_writer import ResultWriter
from ..tooling.runtime import set_runtime_settings

logger = logging.getLogger(__name__)


class AgentRunner:
    def __init__(self, settings: Settings):
        self.settings = settings
        set_runtime_settings(settings)
        self.llm = DatabricksLLM(settings)
        self.profile_repo = ToolProfileRepository(settings)
        self.executor = get_tool_executor(settings)
        self.result_writer = ResultWriter(settings)

    def run(self, task: AgentTaskRequest) -> AgentRunRecord:
        reachability_check = getattr(self.profile_repo, "is_table_reachable", None)
        if getattr(self.profile_repo, "spark", None) is not None and callable(reachability_check):
            try:
                reachability_check()
            except Exception as exc:  # noqa: BLE001
                storage = getattr(self.settings, "storage", None)
                table_name = (
                    getattr(storage, "tool_profile_table", "") if storage is not None else ""
                ).strip() or "<unset>"
                raise RuntimeError(
                    "Unable to read the Delta-backed tool profile table "
                    f"{table_name!r}. Run compile_tool_profile_job first, "
                    "or verify that the table exists and matches the expected schema."
                ) from exc
        try:
            profile = self.profile_repo.load_active(self.settings.active_profile_name)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Unable to load active tool profile for profile {self.settings.active_profile_name!r}: {exc}"
            ) from exc
        if not profile:
            raise RuntimeError(
                "No active tool profile found for profile "
                f"{self.settings.active_profile_name!r}. Run compile_tool_profile_job first."
            )
        return self._run_generic(task, profile)

    def _run_generic(self, task: AgentTaskRequest, profile: ToolProfile) -> AgentRunRecord:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.settings.prompts.agent_system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task_name": task.task_name,
                        "instructions": task.instructions,
                        "payload": task.payload,
                    },
                    indent=2,
                ),
            },
        ]
        tools = self._build_allowed_openai_tools(profile)
        trace: list[dict[str, Any]] = []
        blocked_calls: list[dict[str, Any]] = []
        llm_turn_count = 0

        for _ in range(self.settings.max_agent_steps):
            llm_turn_count += 1
            response = self.llm.tool_step(messages, tools)
            message = response.choices[0].message

            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": message.content or "",
            }
            if getattr(message, "tool_calls", None):
                assistant_message["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in message.tool_calls
                ]
            messages.append(assistant_message)

            if not getattr(message, "tool_calls", None):
                record = AgentRunRecord(
                    run_id=task.run_id,
                    profile_name=profile.profile_name,
                    profile_version=profile.profile_version,
                    task_name=task.task_name,
                    status="success",
                    tools_called=trace,
                    blocked_calls=blocked_calls,
                    llm_turn_count=llm_turn_count,
                    result=self._build_result_payload(
                        final_response=message.content or "",
                        task=task,
                        profile=profile,
                        tool_trace=trace,
                    ),
                    inventory_hash=profile.inventory_hash,
                )
                self._persist(record)
                return record

            for index, call in enumerate(message.tool_calls, start=1):
                tool_name = call.function.name
                tool_args = json.loads(call.function.arguments or "{}")
                tool_result = self._execute_with_allowlist(
                    profile,
                    request_id=f"{task.run_id}:{index}",
                    tool_name=tool_name,
                    arguments=tool_args,
                    expected_blocked_calls=task.expected_blocked_calls,
                )
                trace_entry = {
                    "tool_name": tool_name,
                    "arguments": tool_args,
                    "status": tool_result.status,
                    "error": tool_result.error,
                }
                trace.append(trace_entry)
                if tool_result.status == "blocked":
                    blocked_calls.append(trace_entry)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(tool_result.model_dump(), ensure_ascii=False),
                    }
                )

        record = AgentRunRecord(
            run_id=task.run_id,
            profile_name=profile.profile_name,
            profile_version=profile.profile_version,
            task_name=task.task_name,
            status="max_steps_exceeded",
            tools_called=trace,
            blocked_calls=blocked_calls,
            llm_turn_count=llm_turn_count,
            result=self._build_result_payload(
                final_response="",
                task=task,
                profile=profile,
                tool_trace=trace,
            ),
            error_message="Maximum agent steps exceeded.",
            inventory_hash=profile.inventory_hash,
        )
        self._persist(record)
        return record

    @staticmethod
    def _build_result_payload(
        *,
        final_response: str,
        task: AgentTaskRequest,
        profile: ToolProfile,
        tool_trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "final_response": final_response,
            "task_payload": task.payload,
            "available_tools": [tool.tool_name for tool in profile.discovered_tools],
            "allowed_tools": list(profile.allowed_tools),
            "tool_trace": tool_trace,
        }

    def _build_allowed_openai_tools(self, profile: ToolProfile) -> list[dict[str, Any]]:
        allowed = set(profile.allowed_tools)
        return [
            tool.to_openai_tool() for tool in profile.discovered_tools if tool.tool_name in allowed
        ]

    def _execute_with_allowlist(
        self,
        profile: ToolProfile,
        request_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        expected_blocked_calls: bool = False,
    ) -> ToolResult:
        if tool_name not in set(profile.allowed_tools):
            if expected_blocked_calls:
                logger.info("Blocked disallowed tool call (expected): %s", tool_name)
            else:
                logger.warning("Blocked disallowed tool call: %s", tool_name)
            return ToolResult(
                tool_name=tool_name,
                status="blocked",
                content={},
                metadata={
                    "profile_name": profile.profile_name,
                    "profile_version": profile.profile_version,
                    "request_id": request_id,
                },
                error=(
                    f"Tool '{tool_name}' is not allowlisted in profile "
                    f"{profile.profile_version}."
                ),
            )
        tool_call = ToolCall(
            tool_name=tool_name,
            arguments=arguments,
            profile_name=profile.profile_name,
            profile_version=profile.profile_version,
            request_id=request_id,
        )
        return self.executor.call_tool(tool_call)

    def _persist(self, record: AgentRunRecord) -> None:
        self.result_writer.write_run_record(record)
        self.result_writer.write_output_record(
            AgentOutputRecord(
                run_id=record.run_id,
                task_name=record.task_name,
                status=record.status,
                profile_name=record.profile_name,
                profile_version=record.profile_version,
                output_payload=record.result,
                error_message=record.error_message,
            )
        )
