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
    ToolResult,
    ToolSpec,
)
from ..providers.factory import get_tool_provider
from ..storage.result_writer import ResultWriter
from ..tooling.runtime import set_runtime_settings

logger = logging.getLogger(__name__)


class AgentRunner:
    def __init__(self, settings: Settings):
        self.settings = settings
        set_runtime_settings(settings)
        self.provider = get_tool_provider(settings)
        self.llm = DatabricksLLM(settings)
        self.executor = get_tool_executor(settings)
        self.result_writer = ResultWriter(settings)

    def run(self, task: AgentTaskRequest) -> AgentRunRecord:
        discovered_tools = self.provider.list_tools()
        inventory_hash = self.provider.inventory_hash()
        return self._run_generic(
            task=task,
            discovered_tools=discovered_tools,
            inventory_hash=inventory_hash,
        )

    def _run_generic(
        self,
        *,
        task: AgentTaskRequest,
        discovered_tools: list[ToolSpec],
        inventory_hash: str | None,
    ) -> AgentRunRecord:
        discovered_tools_by_name = {tool.tool_name: tool for tool in discovered_tools}
        # The runtime exposes the full discovered inventory to the model. Tool
        # selection is performed by the LLM at runtime; Python does not
        # pre-filter or manually route tools.
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
        openai_tools = self._build_openai_tools(discovered_tools)
        tool_call_trace: list[dict[str, Any]] = []
        llm_turn_count = 0

        for _ in range(self.settings.max_agent_steps):
            llm_turn_count += 1
            response = self.llm.tool_step(messages, openai_tools, tool_choice="auto")
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
                    task_name=task.task_name,
                    status="success",
                    tools_called=tool_call_trace,
                    llm_turn_count=llm_turn_count,
                    result=self._build_result_payload(
                        final_response=message.content or "",
                        discovered_tools=discovered_tools,
                        tool_calls=tool_call_trace,
                    ),
                    inventory_hash=inventory_hash,
                )
                self._persist(record)
                return record

            for index, call in enumerate(message.tool_calls, start=1):
                tool_args, parse_error = self._parse_tool_arguments(call.function.arguments)
                if parse_error is not None:
                    tool_result = ToolResult(
                        tool_name=call.function.name,
                        status="error",
                        content={},
                        error=parse_error,
                    )
                else:
                    tool_result = self._execute_tool_call(
                        discovered_tools_by_name=discovered_tools_by_name,
                        request_id=f"{task.run_id}:{llm_turn_count}:{index}",
                        tool_name=call.function.name,
                        arguments=tool_args,
                    )
                tool_call_trace.append(
                    {
                        "tool_name": call.function.name,
                        "arguments": tool_args if parse_error is None else {},
                        "status": tool_result.status,
                        "error": tool_result.error,
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(tool_result.model_dump(), ensure_ascii=False),
                    }
                )

        record = AgentRunRecord(
            run_id=task.run_id,
            task_name=task.task_name,
            status="max_steps_exceeded",
            tools_called=tool_call_trace,
            llm_turn_count=llm_turn_count,
            result=self._build_result_payload(
                final_response="",
                discovered_tools=discovered_tools,
                tool_calls=tool_call_trace,
            ),
            error_message="Maximum agent steps exceeded.",
            inventory_hash=inventory_hash,
        )
        self._persist(record)
        return record

    @staticmethod
    def _build_openai_tools(discovered_tools: list[ToolSpec]) -> list[dict[str, Any]]:
        return [tool.to_openai_tool() for tool in discovered_tools]

    def _execute_tool_call(
        self,
        *,
        discovered_tools_by_name: dict[str, ToolSpec],
        request_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        if tool_name not in discovered_tools_by_name:
            logger.warning("Unknown tool call: %s", tool_name)
            return ToolResult(
                tool_name=tool_name,
                status="error",
                content={},
                metadata={"request_id": request_id},
                error=f"Unknown tool call: {tool_name}",
            )
        tool_call = ToolCall(
            tool_name=tool_name,
            arguments=arguments,
            request_id=request_id,
        )
        return self.executor.call_tool(tool_call)

    @staticmethod
    def _parse_tool_arguments(raw_arguments: Any) -> tuple[dict[str, Any], str | None]:
        if not raw_arguments:
            return {}, None
        if isinstance(raw_arguments, dict):
            return raw_arguments, None
        if not isinstance(raw_arguments, str):
            return (
                {},
                "Tool call arguments must be JSON text or an object, "
                f"got {type(raw_arguments)!r}",
            )
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            return {}, f"Tool call arguments were not valid JSON: {exc}"
        if not isinstance(parsed, dict):
            return {}, "Tool call arguments must decode to a JSON object."
        return parsed, None

    @staticmethod
    def _build_result_payload(
        *,
        final_response: str,
        discovered_tools: list[ToolSpec],
        tool_calls: list[dict[str, Any]],
    ) -> dict[str, Any]:
        available_tools = [tool.tool_name for tool in discovered_tools]
        return {
            "final_response": final_response,
            "available_tools": available_tools,
            "available_tools_count": len(available_tools),
            "tool_calls": tool_calls,
        }

    def _persist(self, record: AgentRunRecord) -> None:
        self.result_writer.write_run_record(record)
        self.result_writer.write_output_record(
            AgentOutputRecord(
                run_id=record.run_id,
                task_name=record.task_name,
                status=record.status,
                output_payload=record.result,
                error_message=record.error_message,
            )
        )
