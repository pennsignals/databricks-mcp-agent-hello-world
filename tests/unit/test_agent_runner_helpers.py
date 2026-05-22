from __future__ import annotations

import json
from types import SimpleNamespace

from databricks_mcp_agent_hello_world.models import AgentTaskRequest
from databricks_mcp_agent_hello_world.runner.agent_runner import AgentRunner


def _runner() -> AgentRunner:
    # Pure-helper tests only need settings; avoid wiring provider/LLM dependencies.
    runner = AgentRunner.__new__(AgentRunner)
    runner.settings = SimpleNamespace(
        prompts=SimpleNamespace(agent_system_prompt="system prompt"),
    )
    return runner


def test_build_initial_messages_preserves_current_prompt_shape() -> None:
    runner = _runner()

    messages = runner._build_initial_messages(
        AgentTaskRequest(
            task_name="workspace_onboarding_brief",
            instructions="Write the report.",
            payload={"user_id": "usr_ada_01"},
        )
    )

    assert messages[0] == {"role": "system", "content": "system prompt"}
    assert messages[1]["role"] == "user"
    assert json.loads(messages[1]["content"]) == {
        "task_name": "workspace_onboarding_brief",
        "instructions": "Write the report.",
        "payload": {"user_id": "usr_ada_01"},
    }


def test_build_assistant_message_preserves_tool_call_shape() -> None:
    call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(
            name="get_user_profile",
            arguments='{"user_id":"usr_ada_01"}',
        ),
    )
    message = SimpleNamespace(content="Checking.", tool_calls=[call])

    assert AgentRunner._build_assistant_message(message, [call]) == {
        "role": "assistant",
        "content": "Checking.",
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "get_user_profile",
                    "arguments": '{"user_id":"usr_ada_01"}',
                },
            }
        ],
    }


def test_emit_event_increments_event_index(monkeypatch) -> None:
    runner = _runner()
    persisted_event_rows = []
    task = AgentTaskRequest(
        task_name="workspace_onboarding_brief",
        instructions="Write the report.",
        run_id="run-123",
    )
    state = runner._initialize_run_state(
        task=task,
        discovered_tools=[],
        inventory_hash="inventory-hash",
    )

    def _stub_write_event_rows(settings, rows) -> None:
        del settings
        persisted_event_rows.extend(dict(row) for row in rows)

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.runner.agent_runner.write_event_rows",
        _stub_write_event_rows,
    )

    runner._emit_event(
        state,
        event_type="first",
        turn_index=None,
        payload={"step": 1},
    )
    runner._emit_event(
        state,
        event_type="second",
        turn_index=0,
        payload={"step": 2},
    )

    assert [row["event_index"] for row in persisted_event_rows] == [0, 1]
    assert state.event_index == 2


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
