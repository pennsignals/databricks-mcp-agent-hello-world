from __future__ import annotations

from databricks_mcp_agent_hello_world.runner.agent_runner import AgentRunner


def test_parse_tool_arguments_accepts_dicts_and_json_objects() -> None:
    assert AgentRunner._parse_tool_arguments({}) == ({}, None)
    assert AgentRunner._parse_tool_arguments({"a": 1}) == ({"a": 1}, None)


def test_parse_tool_arguments_rejects_non_mapping_values() -> None:
    assert AgentRunner._parse_tool_arguments(5)[1] is not None
    assert AgentRunner._parse_tool_arguments("[]") == (
        {},
        "Tool call arguments must decode to a JSON object.",
    )


def test_build_result_payload_summarizes_discovered_tools_and_tool_calls() -> None:
    assert AgentRunner._build_result_payload(
        final_response="done",
        discovered_tools=[],
        tool_calls=[],
    ) == {
        "final_response": "done",
        "available_tools": [],
        "available_tools_count": 0,
        "tool_calls": [],
    }


def test_truncate_excerpt_limits_text_to_five_hundred_characters() -> None:
    assert AgentRunner._truncate_excerpt("x" * 600) == "x" * 500
