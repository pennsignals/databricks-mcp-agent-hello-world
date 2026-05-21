from __future__ import annotations

from types import SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world import llm_client
from tests.helpers import make_settings


def test_databricks_llm_rejects_blank_endpoint_name() -> None:
    with pytest.raises(ValueError, match="llm_endpoint_name must be configured"):
        llm_client.DatabricksLLM(make_settings(llm_endpoint_name="   "))


def test_databricks_llm_passes_optional_tool_choice(monkeypatch) -> None:
    create_calls: list[dict[str, object]] = []

    class FakeChatCompletions:
        def create(self, **kwargs):
            create_calls.append(kwargs)
            return {"ok": True}

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeChatCompletions()))
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.clients.databricks.get_openai_client",
        lambda settings: fake_client,
    )
    llm = llm_client.DatabricksLLM(make_settings(llm_endpoint_name="endpoint-a"))

    assert llm.tool_step([], []) == {"ok": True}
    assert "tool_choice" not in create_calls[0]
    assert llm.tool_step([], [], tool_choice="auto") == {"ok": True}
    assert create_calls[1]["tool_choice"] == "auto"
