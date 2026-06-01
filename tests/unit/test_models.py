from __future__ import annotations

from datetime import UTC, datetime

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
        started_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, 12, 1, tzinfo=UTC),
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
        "completed_at",
    }
    assert "created_at" not in AgentRunRecord.model_fields
    assert "started_at" in AgentRunRecord.model_fields
    assert "completed_at" in AgentRunRecord.model_fields


def test_agent_run_record_requires_explicit_timestamps() -> None:
    with pytest.raises(ValidationError) as exc_info:
        AgentRunRecord(
            run_id="run-1",
            task_name="customer_account_brief",
            status="success",
        )
    missing_fields = {tuple(error["loc"]) for error in exc_info.value.errors()}

    assert ("started_at",) in missing_fields
    assert ("completed_at",) in missing_fields


def test_eval_scenario_rejects_invalid_task_input_sources() -> None:
    with pytest.raises(ValidationError, match="exactly one of task_input or task_input_file"):
        EvalScenario(scenario_id="missing-input", description="Invalid scenario")


def test_agent_run_record_rejects_error_status() -> None:
    with pytest.raises(ValidationError):
        AgentRunRecord(
            run_id="run-1",
            task_name="customer_account_brief",
            status="error",
            started_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            completed_at=datetime(2026, 1, 1, 12, 1, tzinfo=UTC),
        )
