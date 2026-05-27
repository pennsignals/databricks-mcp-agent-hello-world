from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from ..config import Settings
from ..llm_client import DatabricksLLM
from ..models import (
    AgentRunRecord,
    AgentTaskRequest,
    ToolCall,
    ToolResult,
)
from ..providers.factory import get_tool_provider
from ..storage.schema import safe_jsonable, serialize_event_row
from ..storage.write import write_event_rows
from ..tools.runtime import RuntimeTool, inventory_hash
from ..tools.validation import ToolValidationError, validate_tool_arguments

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _RunState:
    task: AgentTaskRequest
    discovered_tools: list[RuntimeTool]
    discovered_tools_by_name: dict[str, RuntimeTool]
    inventory_hash: str | None
    messages: list[dict[str, Any]]
    openai_tools: list[dict[str, Any]]
    tool_call_trace: list[dict[str, Any]]
    llm_turn_count: int = 0
    event_index: int = 0


class AgentRunner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = get_tool_provider(settings)
        self.llm = DatabricksLLM(settings)

    def run(self, task: AgentTaskRequest) -> AgentRunRecord:
        discovered_tools = self.provider.list_tools()
        discovered_inventory_hash = inventory_hash(discovered_tools)
        return self._run_generic(
            task=task,
            discovered_tools=discovered_tools,
            inventory_hash=discovered_inventory_hash,
        )

    def _run_generic(
        self,
        *,
        task: AgentTaskRequest,
        discovered_tools: list[RuntimeTool],
        inventory_hash: str | None,
    ) -> AgentRunRecord:
        state = self._initialize_run_state(
            task=task,
            discovered_tools=discovered_tools,
            inventory_hash=inventory_hash,
        )

        self._emit_run_started(state)

        try:
            return self._run_agent_loop(state)
        except Exception as exc:
            self._safe_emit_run_failed(state, exc)
            raise

    def _initialize_run_state(
        self,
        *,
        task: AgentTaskRequest,
        discovered_tools: list[RuntimeTool],
        inventory_hash: str | None,
    ) -> _RunState:
        return _RunState(
            task=task,
            discovered_tools=discovered_tools,
            discovered_tools_by_name={tool.name: tool for tool in discovered_tools},
            inventory_hash=inventory_hash,
            messages=self._build_initial_messages(task),
            openai_tools=self._build_openai_tools(discovered_tools),
            tool_call_trace=[],
        )

    def _build_initial_messages(self, task: AgentTaskRequest) -> list[dict[str, Any]]:
        return [
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

    @staticmethod
    def _build_openai_tools(discovered_tools: list[RuntimeTool]) -> list[dict[str, Any]]:
        return [tool.spec for tool in discovered_tools]

    def _emit_event(
        self,
        state: _RunState,
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
        row = serialize_event_row(
            run_key=state.task.run_id,
            task_name=state.task.task_name,
            turn_index=turn_index,
            event_index=state.event_index,
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
        state.event_index += 1

    def _emit_run_started(self, state: _RunState) -> None:
        self._emit_event(
            state,
            event_type="run_started",
            turn_index=None,
            status="started",
            payload={
                "task_name": state.task.task_name,
                "instructions": state.task.instructions,
                "payload": state.task.payload,
                "available_tools": [tool.name for tool in state.discovered_tools],
                "available_tools_count": len(state.discovered_tools),
            },
        )

    def _emit_run_failed(self, state: _RunState, exc: Exception) -> None:
        self._emit_event(
            state,
            event_type="run_failed",
            turn_index=None,
            status="error",
            event_inventory_hash=state.inventory_hash,
            error_message=str(exc),
            payload={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "result": self._build_result_payload(
                    final_response="",
                    discovered_tools=state.discovered_tools,
                    tool_calls=state.tool_call_trace,
                ),
            },
        )

    def _safe_emit_run_failed(self, state: _RunState, exc: Exception) -> None:
        try:
            self._emit_run_failed(state, exc)
        except Exception:
            logger.exception("Failed to persist run_failed event.")

    def _run_agent_loop(self, state: _RunState) -> AgentRunRecord:
        for _ in range(self.settings.max_agent_steps):
            turn_index, message, tool_calls = self._run_llm_turn(state)

            if not tool_calls:
                final_response = message.content or ""
                record = self._build_success_record(state, final_response=final_response)
                self._emit_run_completed(
                    state,
                    record=record,
                    final_response=final_response,
                )
                return record

            self._handle_tool_calls(
                state,
                turn_index=turn_index,
                tool_calls=tool_calls,
            )

        record = self._build_max_steps_record(state)
        self._emit_run_max_steps_exceeded(state, record=record)
        return record

    def _run_llm_turn(self, state: _RunState) -> tuple[int, Any, Any]:
        turn_index = state.llm_turn_count
        self._emit_event(
            state,
            event_type="llm_request",
            turn_index=turn_index,
            model_name=self.settings.llm_endpoint_name,
            payload={
                "model": self.settings.llm_endpoint_name,
                "messages": state.messages,
                "tools": state.openai_tools,
                "tool_choice": "auto",
            },
        )
        state.llm_turn_count += 1

        response = self.llm.tool_step(
            state.messages,
            state.openai_tools,
            tool_choice="auto",
        )
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None)
        terminal_excerpt = None
        if not tool_calls and (message.content or ""):
            terminal_excerpt = self._truncate_excerpt(message.content or "")

        self._emit_event(
            state,
            event_type="llm_response",
            turn_index=turn_index,
            final_response_excerpt=terminal_excerpt,
            payload=safe_jsonable(response),
        )

        state.messages.append(self._build_assistant_message(message, tool_calls))
        return turn_index, message, tool_calls

    @staticmethod
    def _build_assistant_message(message: Any, tool_calls: Any) -> dict[str, Any]:
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
        return assistant_message

    def _handle_tool_calls(
        self,
        state: _RunState,
        *,
        turn_index: int,
        tool_calls: Any,
    ) -> None:
        for index, call in enumerate(tool_calls, start=1):
            tool_args, parse_error = self._parse_tool_arguments(call.function.arguments)

            self._emit_tool_call_requested(
                state,
                turn_index=turn_index,
                call=call,
                tool_args=tool_args,
                parse_error=parse_error,
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
                    tools_by_name=state.discovered_tools_by_name,
                    request_id=f"{state.task.run_id}:{state.llm_turn_count}:{index}",
                    tool_name=call.function.name,
                    arguments=tool_args,
                )

            self._emit_tool_result(
                state,
                turn_index=turn_index,
                call=call,
                tool_result=tool_result,
            )
            self._record_tool_call_trace(
                state,
                call=call,
                tool_args=tool_args,
                parse_error=parse_error,
                tool_result=tool_result,
            )
            state.messages.append(self._build_tool_message(call, tool_result))

    def _emit_tool_call_requested(
        self,
        state: _RunState,
        *,
        turn_index: int,
        call: Any,
        tool_args: dict[str, Any],
        parse_error: str | None,
    ) -> None:
        self._emit_event(
            state,
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

    def _emit_tool_result(
        self,
        state: _RunState,
        *,
        turn_index: int,
        call: Any,
        tool_result: ToolResult,
    ) -> None:
        self._emit_event(
            state,
            event_type="tool_result",
            turn_index=turn_index,
            status=tool_result.status,
            tool_name=call.function.name,
            tool_call_id=call.id,
            error_message=tool_result.error,
            payload=tool_result.model_dump(mode="json"),
        )

    @staticmethod
    def _record_tool_call_trace(
        state: _RunState,
        *,
        call: Any,
        tool_args: dict[str, Any],
        parse_error: str | None,
        tool_result: ToolResult,
    ) -> None:
        state.tool_call_trace.append(
            {
                "tool_name": call.function.name,
                "arguments": tool_args if parse_error is None else {},
                "status": tool_result.status,
                "error": tool_result.error,
            }
        )

    @staticmethod
    def _build_tool_message(call: Any, tool_result: ToolResult) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": call.id,
            "content": json.dumps(tool_result.model_dump(), ensure_ascii=False),
        }

    def _build_success_record(
        self,
        state: _RunState,
        *,
        final_response: str,
    ) -> AgentRunRecord:
        return AgentRunRecord(
            run_id=state.task.run_id,
            task_name=state.task.task_name,
            status="success",
            tools_called=state.tool_call_trace,
            llm_turn_count=state.llm_turn_count,
            result=self._build_result_payload(
                final_response=final_response,
                discovered_tools=state.discovered_tools,
                tool_calls=state.tool_call_trace,
            ),
            inventory_hash=state.inventory_hash,
        )

    def _emit_run_completed(
        self,
        state: _RunState,
        *,
        record: AgentRunRecord,
        final_response: str,
    ) -> None:
        self._emit_event(
            state,
            event_type="run_completed",
            turn_index=None,
            status="success",
            event_inventory_hash=state.inventory_hash,
            final_response_excerpt=self._truncate_excerpt(final_response),
            payload=record.result,
        )

    def _build_max_steps_record(self, state: _RunState) -> AgentRunRecord:
        return AgentRunRecord(
            run_id=state.task.run_id,
            task_name=state.task.task_name,
            status="max_steps_exceeded",
            tools_called=state.tool_call_trace,
            llm_turn_count=state.llm_turn_count,
            result=self._build_result_payload(
                final_response="",
                discovered_tools=state.discovered_tools,
                tool_calls=state.tool_call_trace,
            ),
            error_message="Maximum agent steps exceeded.",
            inventory_hash=state.inventory_hash,
        )

    def _emit_run_max_steps_exceeded(
        self,
        state: _RunState,
        *,
        record: AgentRunRecord,
    ) -> None:
        self._emit_event(
            state,
            event_type="run_max_steps_exceeded",
            turn_index=None,
            status="max_steps_exceeded",
            event_inventory_hash=state.inventory_hash,
            error_message="Maximum agent steps exceeded.",
            payload=record.result,
        )

    def _execute_tool_call(
        self,
        *,
        tools_by_name: dict[str, RuntimeTool],
        request_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        runtime_tool = tools_by_name.get(tool_name)
        if runtime_tool is None:
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
        try:
            validated_arguments = validate_tool_arguments(
                tool_name=runtime_tool.name,
                tool_spec=runtime_tool.spec,
                arguments=tool_call.arguments,
            )
            content = runtime_tool.execute(**validated_arguments)
            logger.info("Executed tool %s from %s", tool_name, runtime_tool.source.type)
            return ToolResult(
                tool_name=tool_name,
                status="ok",
                content=content,
                metadata={
                    "source_type": runtime_tool.source.type,
                    "source_id": runtime_tool.source.id,
                    "request_id": request_id,
                },
            )
        except ToolValidationError as exc:
            logger.info("Tool validation failed for %s: %s", tool_name, exc.message)
            return ToolResult(
                tool_name=tool_name,
                status="error",
                content={
                    "error_type": exc.error_type,
                    "message": exc.message,
                },
                metadata={
                    "error_type": exc.error_type,
                    "source_type": runtime_tool.source.type,
                    "source_id": runtime_tool.source.id,
                    "request_id": request_id,
                },
                error=exc.message,
            )
        except Exception as exc:
            logger.exception("Tool execution failed for %s", tool_name)
            return ToolResult(
                tool_name=tool_name,
                status="error",
                content={},
                metadata={
                    "source_type": runtime_tool.source.type,
                    "source_id": runtime_tool.source.id,
                    "request_id": request_id,
                },
                error=str(exc),
            )

    @staticmethod
    def _parse_tool_arguments(raw_arguments: Any) -> tuple[dict[str, Any], str | None]:
        if not raw_arguments:
            return {}, None
        if isinstance(raw_arguments, dict):
            return raw_arguments, None
        if not isinstance(raw_arguments, str):
            return (
                {},
                f"Tool call arguments must be JSON text or an object, got {type(raw_arguments)!r}",
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
        discovered_tools: list[RuntimeTool],
        tool_calls: list[dict[str, Any]],
    ) -> dict[str, Any]:
        available_tools = [tool.name for tool in discovered_tools]
        return {
            "final_response": final_response,
            "available_tools": available_tools,
            "available_tools_count": len(available_tools),
            "tool_calls": tool_calls,
        }

    @staticmethod
    def _truncate_excerpt(content: str) -> str:
        return content[:500]
