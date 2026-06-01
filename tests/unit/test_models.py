from __future__ import annotations

import pytest
from pydantic import ValidationError

from databricks_tool_agent_template.models import (
    AgentRunRecord,
    DiscoveredTool,
    EvalScenario,
    ToolResult,
)


def test_discovered_tool_matches_simplified_inventory_shape() -> None:
    tool = DiscoveredTool(
        name="sample_tool",
        source_type="local_python",
        source_id="local_python",
        spec={
            "type": "function",
            "function": {
                "name": "sample_tool",
                "description": "Sample description",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
    )

    assert set(tool.model_dump()) == {"name", "source_type", "source_id", "spec"}


def test_tool_result_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        ToolResult.model_validate({"tool_name": "sample_tool", "status": "blocked", "content": {}})


def test_agent_run_record_matches_current_runtime_shape() -> None:
    record = AgentRunRecord(
        run_id="run-1",
        task_name="customer_account_brief",
        status="success",
        result={
            "final_response": "done",
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


def test_agent_run_record_rejects_error_status() -> None:
    with pytest.raises(ValidationError):
        AgentRunRecord(
            run_id="run-1",
            task_name="customer_account_brief",
            status="error",
        )
