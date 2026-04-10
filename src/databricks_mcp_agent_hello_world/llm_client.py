from __future__ import annotations

import json
import logging
import re
from typing import Any

from databricks_openai import DatabricksOpenAI

from .config import Settings

logger = logging.getLogger(__name__)


class DatabricksLLM:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = DatabricksOpenAI()

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        response = self.client.chat.completions.create(
            model=self.settings.llm_endpoint_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        content = response.choices[0].message.content or "{}"
        return self._extract_json(content)

    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.settings.llm_endpoint_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        return response.choices[0].message.content or ""

    def tool_step(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ):
        return self.client.chat.completions.create(
            model=self.settings.llm_endpoint_name,
            messages=messages,
            tools=tools,
            temperature=0,
        )

    @staticmethod
    def _extract_json(content: str) -> dict[str, Any]:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        match = re.search(r"```json\s*(\{.*\}|\[.*\])\s*```", content, re.DOTALL)
        if match:
            return json.loads(match.group(1))

        match = re.search(r"(\{.*\}|\[.*\])", content, re.DOTALL)
        if match:
            return json.loads(match.group(1))

        logger.error("Model did not return parseable JSON: %s", content)
        raise ValueError("Model did not return parseable JSON")
