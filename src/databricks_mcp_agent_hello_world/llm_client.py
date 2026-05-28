from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import Settings


@dataclass(frozen=True)
class LLMToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class LLMTurnResult:
    content: str | None
    tool_calls: list[LLMToolCall]
    raw_response: Any | None = None


class DatabricksLLM:
    def __init__(self, settings: Settings):
        if not settings.llm_endpoint_name.strip():
            raise ValueError("llm_endpoint_name must be configured before initializing the LLM.")
        from .clients.databricks import get_openai_client

        self.settings = settings
        self.client = get_openai_client(settings)

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMTurnResult:
        kwargs: dict[str, Any] = {
            "model": self.settings.llm_endpoint_name,
            "messages": messages,
            "tools": tools,
            "temperature": 0,
        }
        response = self.client.chat.completions.create(**kwargs)
        return _normalize_chat_completion_response(response)


def _normalize_chat_completion_response(response: Any) -> LLMTurnResult:
    message = response.choices[0].message
    return LLMTurnResult(
        content=message.content,
        tool_calls=[
            LLMToolCall(
                id=call.id,
                name=call.function.name,
                arguments=call.function.arguments,
            )
            for call in (message.tool_calls or [])
        ],
        raw_response=response,
    )
