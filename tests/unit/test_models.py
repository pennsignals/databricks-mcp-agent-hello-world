from __future__ import annotations

import pytest
from pydantic import ValidationError

from databricks_mcp_agent_hello_world.models import (
    AgentRunRecord,
    EvalScenario,
    ToolResult,
    ToolSpec,
)


def _base_tool_spec(**overrides) -> dict:
    payload = {
        "tool_name": "sample_tool",
        "description": "Sample description",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "provider_type": "local_python",
        "provider_id": "builtin_tools",
    }
    payload.update(overrides)
    return payload


def test_tool_spec_metadata_defaults_are_applied() -> None:
    tool = ToolSpec(**_base_tool_spec())

    assert tool.capability_tags == []
    assert tool.side_effect_level == "read_only"
    assert tool.data_domains == []
    assert tool.example_uses == []


def test_tool_spec_metadata_is_normalized_deduplicated_and_sorted() -> None:
    tool = ToolSpec(
        **_base_tool_spec(
            capability_tags=["Docs_Search", "docs_search", "config_lookup"],
            data_domains=["Workspace_Config", "workspace_config", "docs"],
        )
    )

    assert tool.capability_tags == ["config_lookup", "docs_search"]
    assert tool.data_domains == ["docs", "workspace_config"]


def test_tool_spec_example_uses_preserves_order_and_deduplicates() -> None:
    tool = ToolSpec(
        **_base_tool_spec(
            example_uses=[
                "Retrieve the runtime target",
                "Retrieve the runtime target",
                "Look up the workspace region",
            ]
        )
    )

    assert tool.example_uses == [
        "Retrieve the runtime target",
        "Look up the workspace region",
    ]


@pytest.mark.parametrize(
    "field_name,bad_values",
    [
        ("capability_tags", [""]),
        ("capability_tags", ["bad tag"]),
        ("capability_tags", ["bad-tag"]),
        ("data_domains", [""]),
        ("data_domains", ["Bad Domain"]),
        ("example_uses", [""]),
    ],
)
def test_tool_spec_rejects_invalid_metadata_values(field_name: str, bad_values: list[str]) -> None:
    with pytest.raises(ValidationError):
        ToolSpec(**_base_tool_spec(**{field_name: bad_values}))


def test_tool_result_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        ToolResult.model_validate({"tool_name": "sample_tool", "status": "blocked", "content": {}})


def test_agent_run_record_matches_current_runtime_shape() -> None:
    record = AgentRunRecord(
        run_id="run-1",
        task_name="workspace_onboarding_brief",
        status="success",
        result={
            "final_response": "done",
            "available_tools": ["sample_tool"],
            "tool_calls": [],
        },
    )

    assert set(record.model_dump()) == {
        "run_id",
        "task_name",
        "status",
        "tools_called",
        "llm_turn_count",
        "result",
        "error_message",
        "inventory_hash",
        "started_at",
        "created_at",
    }


def test_eval_scenario_rejects_invalid_task_input_sources() -> None:
    with pytest.raises(ValidationError, match="exactly one of task_input or task_input_file"):
        EvalScenario(scenario_id="missing-input", description="Invalid scenario")


def test_eval_scenario_rejects_min_tool_calls_above_max_tool_calls(
    demo_task_path,
) -> None:
    with pytest.raises(ValidationError):
        EvalScenario(
            scenario_id="bad-bounds",
            description="Invalid bounds",
            task_input_file=str(demo_task_path),
            min_tool_calls=3,
            max_tool_calls=2,
        )
