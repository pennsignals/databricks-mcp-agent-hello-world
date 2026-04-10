from __future__ import annotations

import json
import logging
from typing import Any

from ..config import Settings
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
from ..providers.local_python import LocalPythonToolExecutor
from ..storage.result_writer import ResultWriter
from ..tooling.runtime import set_runtime_settings

logger = logging.getLogger(__name__)


class AgentRunner:
    def __init__(self, settings: Settings):
        self.settings = settings
        set_runtime_settings(settings)
        self.llm = DatabricksLLM(settings)
        self.profile_repo = ToolProfileRepository(settings)
        self.executor = LocalPythonToolExecutor(settings)
        self.result_writer = ResultWriter(settings)

    def run(self, task: AgentTaskRequest) -> AgentRunRecord:
        profile = self.profile_repo.load_active()
        if not profile:
            raise ValueError("No active tool profile found. Run compile_tool_profile first.")

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
                    result={
                        "final_response": message.content or "",
                        "task_payload": task.payload,
                    },
                    inventory_hash=profile.inventory_hash,
                )
                self._persist(record)
                return record

            for call in message.tool_calls:
                tool_name = call.function.name
                tool_args = json.loads(call.function.arguments or "{}")
                tool_result = self._execute_with_allowlist(
                    profile, task.run_id, tool_name, tool_args
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
            result={},
            error_message="Maximum agent steps exceeded.",
            inventory_hash=profile.inventory_hash,
        )
        self._persist(record)
        return record

    def _build_allowed_openai_tools(self, profile: ToolProfile) -> list[dict[str, Any]]:
        allowed = set(profile.allowed_tools)
        return [
            tool.to_openai_tool() for tool in profile.discovered_tools if tool.tool_name in allowed
        ]

    def _execute_with_allowlist(
        self,
        profile: ToolProfile,
        run_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        if tool_name not in set(profile.allowed_tools):
            logger.warning("Blocked disallowed tool call: %s", tool_name)
            return ToolResult(
                tool_name=tool_name,
                status="blocked",
                content={},
                metadata={"profile_version": profile.profile_version, "run_id": run_id},
                error=(
                    f"Tool '{tool_name}' is not allowlisted in profile "
                    f"{profile.profile_version}."
                ),
            )
        tool_call = ToolCall(
            tool_name=tool_name,
            arguments=arguments,
            profile_version=profile.profile_version,
            run_id=run_id,
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
