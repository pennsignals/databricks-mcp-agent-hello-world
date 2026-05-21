from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class DiscoveredTool(BaseModel):
    name: str
    source_type: str
    source_id: str
    spec: dict[str, Any]


class ToolCall(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(default_factory=lambda: str(uuid4()))


class ToolResult(BaseModel):
    tool_name: str
    status: Literal["ok", "error"]
    content: dict[str, Any] | list[Any] | str
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class AgentTaskRequest(BaseModel):
    task_name: str
    instructions: str
    payload: dict[str, Any] = Field(default_factory=dict)
    run_id: str = Field(default_factory=lambda: str(uuid4()))


class AgentRunRecord(BaseModel):
    run_id: str
    task_name: str
    status: Literal["success", "error", "max_steps_exceeded"]
    tools_called: list[dict[str, Any]] = Field(default_factory=list)
    llm_turn_count: int = 0
    result: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    inventory_hash: str | None = None
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class DiscoveryReport(BaseModel):
    provider_type: str
    tool_count: int
    provider_id: str
    inventory_hash: str
    tools: list[DiscoveredTool]


class PreflightCheck(BaseModel):
    name: str
    status: Literal["pass", "fail", "warn"]
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class PreflightReport(BaseModel):
    overall_status: Literal["pass", "fail"]
    checks: list[PreflightCheck]
    settings_summary: dict[str, Any] = Field(default_factory=dict)


class EvalScenario(BaseModel):
    scenario_id: str
    description: str
    task_input: AgentTaskRequest | None = None
    task_input_file: str | None = None

    expected_status: Literal["success", "error", "max_steps_exceeded"] = "success"
    required_available_tools: list[str] = Field(default_factory=list)
    forbidden_available_tools: list[str] = Field(default_factory=list)
    required_executed_tools: list[str] = Field(default_factory=list)
    forbidden_executed_tools: list[str] = Field(default_factory=list)
    min_tool_calls: int | None = None
    max_tool_calls: int | None = None
    required_result_keys: list[str] = Field(
        default_factory=lambda: ["final_response", "available_tools", "tool_calls"]
    )
    required_output_substrings: list[str] = Field(default_factory=list)
    forbidden_output_substrings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_tool_call_bounds(self) -> EvalScenario:
        if (self.task_input is None) == (self.task_input_file is None):
            raise ValueError("exactly one of task_input or task_input_file must be provided")
        if (
            self.min_tool_calls is not None
            and self.max_tool_calls is not None
            and self.min_tool_calls > self.max_tool_calls
        ):
            raise ValueError("min_tool_calls must be less than or equal to max_tool_calls")
        return self


class EvalScenarioResult(BaseModel):
    scenario_id: str
    passed: bool
    failed_checks: list[str]
    expected_status: str
    actual_status: str | None = None
    available_tools: list[str] = Field(default_factory=list)
    executed_tools: list[str] = Field(default_factory=list)
    tool_call_count: int = 0
    final_response_excerpt: str = ""
    task_name: str
    run_record_id: str | None = None
    missing_required_output_substrings: list[str] = Field(default_factory=list)
    found_forbidden_output_substrings: list[str] = Field(default_factory=list)
    missing_required_available_tools: list[str] = Field(default_factory=list)
    present_forbidden_available_tools: list[str] = Field(default_factory=list)
    missing_required_executed_tools: list[str] = Field(default_factory=list)
    present_forbidden_executed_tools: list[str] = Field(default_factory=list)
    missing_required_result_keys: list[str] = Field(default_factory=list)
    actual_result_keys: list[str] = Field(default_factory=list)
    expected_min_tool_calls: int | None = None
    expected_max_tool_calls: int | None = None
    scenario_execution_error_message: str | None = None


class EvalRunReport(BaseModel):
    scenario_file: str
    total_scenarios: int
    passed_scenarios: int
    failed_scenarios: int
    all_passed: bool
    results: list[EvalScenarioResult]
