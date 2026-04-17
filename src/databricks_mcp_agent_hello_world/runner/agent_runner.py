from __future__ import annotations

import json
import logging
from typing import Any

from ..config import Settings
from ..llm_client import DatabricksLLM
from ..models import (
    AgentRunRecord,
    AgentTaskRequest,
    ToolCall,
    ToolResult,
    ToolSpec,
)
from ..providers.factory import get_tool_provider
from ..storage.schema import safe_jsonable, serialize_event_row
from ..storage.write import write_event_rows

logger = logging.getLogger(__name__)


class AgentRunner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = get_tool_provider(settings)
        self.llm = DatabricksLLM(settings)

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
        run_key = task.run_id
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
        event_index = 0

        def emit_event(
            *,
            event_type: str,
            payload: Any,
            turn_index: int | None,
            status: str | None = None,
            tool_name: str | None = None,
            tool_call_id: str | None = None,
            model_name: str | None = None,
            final_response_excerpt: str | None = None,
            error_message: str | None = None,
            event_inventory_hash: str | None = None,
        ) -> None:
            nonlocal event_index
            row = serialize_event_row(
                run_key=run_key,
                task_name=task.task_name,
                turn_index=turn_index,
                event_index=event_index,
                event_type=event_type,
                status=status,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                model_name=model_name,
                inventory_hash=event_inventory_hash,
                final_response_excerpt=final_response_excerpt,
                error_message=error_message,
                payload=payload,
            )
            write_event_rows(self.settings, [row])
            event_index += 1

        emit_event(
            event_type="run_started",
            turn_index=None,
            status="started",
            payload={
                "task_name": task.task_name,
                "instructions": task.instructions,
                "payload": task.payload,
                "available_tools": [tool.tool_name for tool in discovered_tools],
                "available_tools_count": len(discovered_tools),
            },
        )

        try:
            for _ in range(self.settings.max_agent_steps):
                turn_index = llm_turn_count
                emit_event(
                    event_type="llm_request",
                    turn_index=turn_index,
                    model_name=self.settings.llm_endpoint_name,
                    payload={
                        "model": self.settings.llm_endpoint_name,
                        "messages": messages,
                        "tools": openai_tools,
                        "tool_choice": "auto",
                    },
                )
                llm_turn_count += 1
                response = self.llm.tool_step(messages, openai_tools, tool_choice="auto")
                message = response.choices[0].message
                tool_calls = getattr(message, "tool_calls", None)
                terminal_excerpt = None
                if not tool_calls and (message.content or ""):
                    terminal_excerpt = self._truncate_excerpt(message.content or "")

                emit_event(
                    event_type="llm_response",
                    turn_index=turn_index,
                    final_response_excerpt=terminal_excerpt,
                    payload=safe_jsonable(response),
                )

                assistant_message: dict[str, Any] = {
                    "role": "assistant",
                    "content": message.content or "",
                }
                if tool_calls:
                    assistant_message["tool_calls"] = [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in tool_calls
                    ]
                messages.append(assistant_message)

                if not tool_calls:
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
                    emit_event(
                        event_type="run_completed",
                        turn_index=None,
                        status="success",
                        event_inventory_hash=inventory_hash,
                        final_response_excerpt=self._truncate_excerpt(message.content or ""),
                        payload=record.result,
                    )
                    return record

                for index, call in enumerate(tool_calls, start=1):
                    tool_args, parse_error = self._parse_tool_arguments(call.function.arguments)
                    emit_event(
                        event_type="tool_call",
                        turn_index=turn_index,
                        status="requested",
                        tool_name=call.function.name,
                        tool_call_id=call.id,
                        payload={
                            "arguments_raw": call.function.arguments,
                            "arguments_parsed": tool_args if parse_error is None else None,
                            "parse_error": parse_error,
                        },
                    )
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
                    emit_event(
                        event_type="tool_result",
                        turn_index=turn_index,
                        status=tool_result.status,
                        tool_name=call.function.name,
                        tool_call_id=call.id,
                        error_message=tool_result.error,
                        payload=tool_result.model_dump(mode="json"),
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
            emit_event(
                event_type="run_max_steps_exceeded",
                turn_index=None,
                status="max_steps_exceeded",
                event_inventory_hash=inventory_hash,
                error_message="Maximum agent steps exceeded.",
                payload=record.result,
            )
            return record
        except Exception as exc:
            emit_event(
                event_type="run_failed",
                turn_index=None,
                status="error",
                event_inventory_hash=inventory_hash,
                error_message=str(exc),
                payload={
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "result": self._build_result_payload(
                        final_response="",
                        discovered_tools=discovered_tools,
                        tool_calls=tool_call_trace,
                    ),
                },
            )
            raise

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
        return self.provider.call_tool(tool_call)

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

    @staticmethod
    def _truncate_excerpt(content: str) -> str:
        return content[:500]
