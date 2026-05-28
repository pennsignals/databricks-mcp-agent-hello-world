from __future__ import annotations

from types import SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world import llm_client
from tests.helpers import make_settings


def test_databricks_llm_rejects_blank_endpoint_name() -> None:
    with pytest.raises(ValueError, match="llm_endpoint_name must be configured"):
        llm_client.DatabricksLLM(make_settings(llm_endpoint_name="   "))


def _sdk_response(content: str | None = None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _sdk_tool_call(name: str, arguments: str, call_id: str = "call-1"):
    function = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(id=call_id, function=function)


def test_databricks_llm_normalizes_content_only_response(monkeypatch) -> None:
    create_calls: list[dict[str, object]] = []
    raw_response = _sdk_response(content="done")

    class FakeChatCompletions:
        def create(self, **kwargs):
            create_calls.append(kwargs)
            return raw_response

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeChatCompletions()))
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.clients.databricks.get_openai_client",
        lambda settings: fake_client,
    )
    llm = llm_client.DatabricksLLM(make_settings(llm_endpoint_name="endpoint-a"))

    turn = llm.chat(messages=[{"role": "user", "content": "hi"}], tools=[])

    assert turn == llm_client.LLMTurnResult(
        content="done",
        tool_calls=[],
        raw_response=raw_response,
    )
    assert create_calls[0]["model"] == "endpoint-a"
    assert create_calls[0]["messages"] == [{"role": "user", "content": "hi"}]
    assert create_calls[0]["tools"] == []


def test_databricks_llm_normalizes_one_tool_call(monkeypatch) -> None:
    raw_response = _sdk_response(
        tool_calls=[_sdk_tool_call("lookup_customer", '{"customer_id":"cust_acme"}')]
    )

    class FakeChatCompletions:
        def create(self, **kwargs):
            del kwargs
            return raw_response

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeChatCompletions()))
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.clients.databricks.get_openai_client",
        lambda settings: fake_client,
    )
    llm = llm_client.DatabricksLLM(make_settings(llm_endpoint_name="endpoint-a"))

    turn = llm.chat(messages=[], tools=[])

    assert turn.content is None
    assert turn.tool_calls == [
        llm_client.LLMToolCall(
            id="call-1",
            name="lookup_customer",
            arguments='{"customer_id":"cust_acme"}',
        )
    ]
    assert turn.raw_response is raw_response


def test_databricks_llm_normalizes_absent_tool_calls(monkeypatch) -> None:
    raw_response = _sdk_response(content="done", tool_calls=None)

    class FakeChatCompletions:
        def create(self, **kwargs):
            del kwargs
            return raw_response

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeChatCompletions()))
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.clients.databricks.get_openai_client",
        lambda settings: fake_client,
    )
    llm = llm_client.DatabricksLLM(make_settings(llm_endpoint_name="endpoint-a"))

    turn = llm.chat(messages=[], tools=[])

    assert turn.content == "done"
    assert turn.tool_calls == []
