from __future__ import annotations

from typing import Any

from .config import Settings


class DatabricksLLM:
    def __init__(self, settings: Settings):
        if not settings.llm_endpoint_name.strip():
            raise ValueError("llm_endpoint_name must be configured before initializing the LLM.")
        from .clients.databricks import get_openai_client

        self.settings = settings
        self.client = get_openai_client(settings)

    def tool_step(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: Any | None = None,
    ):
        kwargs: dict[str, Any] = {
            "model": self.settings.llm_endpoint_name,
            "messages": messages,
            "tools": tools,
            "temperature": 0,
        }
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        return self.client.chat.completions.create(**kwargs)
