from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ..config import Settings
from ..llm_client import DEFAULT_TOOL_CHOICE, DatabricksLLM, LLMToolCall, LLMTurnResult
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
    started_at: datetime
    llm_turn_count: int = 0
    event_index: int = 0


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AgentRunner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = get_tool_provider(settings)
        self.llm = DatabricksLLM(settings)

    def run(self, task: AgentTaskRequest) -> AgentRunRecord:
        started_at = _utc_now()
        discovered_tools = self.provider.list_tools()
        discovered_inventory_hash = inventory_hash(discovered_tools)
        return self._run_generic(
            task=task,
            discovered_tools=discovered_tools,
            inventory_hash=discovered_inventory_hash,
            started_at=started_at,
        )

    def _run_generic(
        self,
        *,
        task: AgentTaskRequest,
        discovered_tools: list[RuntimeTool],
        inventory_hash: str | None,
        started_at: datetime,
    ) -> AgentRunRecord:
        state = self._initialize_run_state(
            task=task,
            discovered_tools=discovered_tools,
            inventory_hash=inventory_hash,
            started_at=started_at,
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
        started_at: datetime,
    ) -> _RunState:
        return _RunState(
            task=task,
            discovered_tools=discovered_tools,
            discovered_tools_by_name={tool.name: tool for tool in discovered_tools},
            inventory_hash=inventory_hash,
            messages=self._build_initial_messages(task),
            openai_tools=self._build_openai_tools(discovered_tools),
            tool_call_trace=[],
            started_at=started_at,
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
                "tools_called": state.tool_call_trace,
            },
        )

    def _safe_emit_run_failed(self, state: _RunState, exc: Exception) -> None:
        try:
            self._emit_run_failed(state, exc)
        except Exception:
            logger.exception("Failed to persist run_failed event.")

    def _run_agent_loop(self, state: _RunState) -> AgentRunRecord:
        for _ in range(self.settings.max_agent_steps):
            turn_index, turn = self._run_llm_turn(state)

            if not turn.tool_calls:
                final_response = turn.content or ""
                completed_at = _utc_now()
                record = self._build_success_record(
                    state,
                    final_response=final_response,
                    completed_at=completed_at,
                )
                self._emit_run_completed(
                    state,
                    record=record,
                    final_response=final_response,
                )
                return record

            self._handle_tool_calls(
                state,
                turn_index=turn_index,
                tool_calls=turn.tool_calls,
            )

        completed_at = _utc_now()
        record = self._build_max_steps_record(state, completed_at=completed_at)
        self._emit_run_max_steps_exceeded(state, record=record)
        return record

    def _run_llm_turn(self, state: _RunState) -> tuple[int, LLMTurnResult]:
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
                "tool_choice": DEFAULT_TOOL_CHOICE,
            },
        )
        state.llm_turn_count += 1

        turn = self.llm.chat(
            messages=state.messages,
            tools=state.openai_tools,
        )
        terminal_excerpt = None
        if not turn.tool_calls and (turn.content or ""):
            terminal_excerpt = self._truncate_excerpt(turn.content or "")

        self._emit_event(
            state,
            event_type="llm_response",
            turn_index=turn_index,
            final_response_excerpt=terminal_excerpt,
            payload=safe_jsonable(self._turn_payload(turn)),
        )

        state.messages.append(self._build_assistant_message(turn))
        return turn_index, turn

    @staticmethod
    def _turn_payload(turn: LLMTurnResult) -> dict[str, Any]:
        return {
            "content": turn.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "name": call.name,
                    "arguments": call.arguments,
                }
                for call in turn.tool_calls
            ],
        }

    @staticmethod
    def _build_assistant_message(turn: LLMTurnResult) -> dict[str, Any]:
        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": turn.content or "",
        }
        if turn.tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": call.arguments,
                    },
                }
                for call in turn.tool_calls
            ]
        return assistant_message

    def _handle_tool_calls(
        self,
        state: _RunState,
        *,
        turn_index: int,
        tool_calls: list[LLMToolCall],
    ) -> None:
        for index, call in enumerate(tool_calls, start=1):
            tool_args, parse_error = self._parse_tool_arguments(call.arguments)

            self._emit_tool_call_requested(
                state,
                turn_index=turn_index,
                call=call,
                tool_args=tool_args,
                parse_error=parse_error,
            )

            if parse_error is not None:
                tool_result = ToolResult(
                    tool_name=call.name,
                    status="error",
                    content={},
                    error=parse_error,
                )
            else:
                tool_result = self._execute_tool_call(
                    tools_by_name=state.discovered_tools_by_name,
                    request_id=f"{state.task.run_id}:{state.llm_turn_count}:{index}",
                    tool_name=call.name,
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
        call: LLMToolCall,
        tool_args: dict[str, Any],
        parse_error: str | None,
    ) -> None:
        self._emit_event(
            state,
            event_type="tool_call",
            turn_index=turn_index,
            status="requested",
            tool_name=call.name,
            tool_call_id=call.id,
            payload={
                "arguments_raw": call.arguments,
                "arguments_parsed": tool_args if parse_error is None else None,
                "parse_error": parse_error,
            },
        )

    def _emit_tool_result(
        self,
        state: _RunState,
        *,
        turn_index: int,
        call: LLMToolCall,
        tool_result: ToolResult,
    ) -> None:
        self._emit_event(
            state,
            event_type="tool_result",
            turn_index=turn_index,
            status=tool_result.status,
            tool_name=call.name,
            tool_call_id=call.id,
            error_message=tool_result.error,
            payload=tool_result.model_dump(mode="json"),
        )

    @staticmethod
    def _record_tool_call_trace(
        state: _RunState,
        *,
        call: LLMToolCall,
        tool_args: dict[str, Any],
        parse_error: str | None,
        tool_result: ToolResult,
    ) -> None:
        state.tool_call_trace.append(
            {
                "tool_name": call.name,
                "arguments": tool_args if parse_error is None else {},
                "status": tool_result.status,
                "error": tool_result.error,
            }
        )

    @staticmethod
    def _build_tool_message(call: LLMToolCall, tool_result: ToolResult) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": call.id,
            "content": json.dumps(tool_result.model_dump(mode="json"), ensure_ascii=False),
        }

    def _build_success_record(
        self,
        state: _RunState,
        *,
        final_response: str,
        completed_at: datetime,
    ) -> AgentRunRecord:
        return AgentRunRecord(
            run_id=state.task.run_id,
            task_name=state.task.task_name,
            status="success",
            tools_called=state.tool_call_trace,
            llm_turn_count=state.llm_turn_count,
            result={"final_response": final_response},
            inventory_hash=state.inventory_hash,
            started_at=state.started_at,
            completed_at=completed_at,
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

    def _build_max_steps_record(
        self,
        state: _RunState,
        *,
        completed_at: datetime,
    ) -> AgentRunRecord:
        return AgentRunRecord(
            run_id=state.task.run_id,
            task_name=state.task.task_name,
            status="max_steps_exceeded",
            tools_called=state.tool_call_trace,
            llm_turn_count=state.llm_turn_count,
            result={"reason": "max_steps_exceeded"},
            error_message="Maximum agent steps exceeded.",
            inventory_hash=state.inventory_hash,
            started_at=state.started_at,
            completed_at=completed_at,
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
        if raw_arguments == "":
            return {}, None
        if not isinstance(raw_arguments, str):
            return (
                {},
                f"Tool call arguments must be JSON text, got {type(raw_arguments)!r}",
            )
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            return {}, f"Tool call arguments were not valid JSON: {exc}"
        if not isinstance(parsed, dict):
            return {}, "Tool call arguments must decode to a JSON object."
        return parsed, None

    @staticmethod
    def _truncate_excerpt(content: str) -> str:
        return content[:500]
