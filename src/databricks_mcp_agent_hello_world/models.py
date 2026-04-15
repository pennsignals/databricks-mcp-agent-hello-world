from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolSpec(BaseModel):
    tool_name: str
    description: str
    input_schema: dict[str, Any]
    provider_type: str
    provider_id: str
    version: str = "1"

    @field_validator("tool_name")
    @classmethod
    def validate_tool_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("tool_name must not be empty")
        return normalized

    @field_validator("input_schema")
    @classmethod
    def validate_input_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        if value.get("type") != "object":
            raise ValueError("input_schema must be a JSON schema object with type=object")
        return value

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.tool_name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


class ToolCall(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    profile_name: str
    profile_version: str
    request_id: str = Field(default_factory=lambda: str(uuid4()))


class ToolResult(BaseModel):
    tool_name: str
    status: Literal["ok", "error", "blocked"]
    content: dict[str, Any] | list[Any] | str
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ToolProfile(BaseModel):
    profile_name: str
    profile_version: str
    inventory_hash: str
    provider_type: str
    llm_endpoint_name: str
    prompt_version: str
    compile_task_name: str
    compile_task_hash: str
    compile_task_summary: str
    discovered_tools: list[ToolSpec]
    allowed_tools: list[str]
    disallowed_tools: list[str]
    justifications: dict[str, str]
    audit_report_text: str
    selection_policy: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_active: bool = True


class AgentTaskRequest(BaseModel):
    task_name: str
    instructions: str
    payload: dict[str, Any] = Field(default_factory=dict)
    expected_blocked_calls: bool = False
    run_id: str = Field(default_factory=lambda: str(uuid4()))


class AgentRunRecord(BaseModel):
    run_id: str
    profile_name: str
    profile_version: str
    task_name: str
    status: Literal["success", "error", "blocked", "max_steps_exceeded"]
    tools_called: list[dict[str, Any]] = Field(default_factory=list)
    llm_turn_count: int = 0
    result: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    blocked_calls: list[dict[str, Any]] = Field(default_factory=list)
    inventory_hash: str | None = None
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class FilterDecision(BaseModel):
    allowed_tools: list[str]
    disallowed_tools: list[str]
    tool_justifications: dict[str, str]
    summary_reasoning: str | None = None


class ToolProfileRecord(BaseModel):
    profile_name: str
    profile_version: str
    inventory_hash: str
    provider_type: str
    llm_endpoint_name: str
    prompt_version: str
    compile_task_name: str
    compile_task_hash: str
    compile_task_summary: str
    is_active: bool
    created_at: str
    selection_policy: str
    audit_report_text: str
    discovered_tools_json: str
    allowed_tools_json: str
    disallowed_tools_json: str
    justifications_json: str


class AgentOutputRecord(BaseModel):
    run_id: str
    task_name: str
    status: str
    profile_name: str
    profile_version: str
    output_payload: dict[str, Any]
    error_message: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DiscoveryReport(BaseModel):
    provider_type: str
    tool_count: int
    provider_id: str
    inventory_hash: str
    tools: list[ToolSpec]
    active_profile: ToolProfile | None = None


class PreflightCheck(BaseModel):
    name: str
    status: Literal["pass", "fail", "warn"]
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class PreflightReport(BaseModel):
    overall_status: Literal["pass", "fail"]
    checks: list[PreflightCheck]
    has_active_profile: bool = False
    can_compile_profile: bool = False
    settings_summary: dict[str, Any] = Field(default_factory=dict)


class CompileToolProfileResult(BaseModel):
    profile: ToolProfile
    reused_existing: bool


class EvalScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    task_name: str
    task_input: dict[str, Any]
    expected_tool_calls_min: int
    expected_allowed_tools_subset: list[str]
    expected_excluded_tools: list[str] = Field(default_factory=list)
    expect_blocked_tool: bool = False
    expected_status: Literal["success", "blocked"]


class EvalScenarioResult(BaseModel):
    scenario_id: str
    status: Literal["pass", "fail", "error"]
    run_id: str | None = None
    tools_called: list[str] = Field(default_factory=list)
    blocked_tools: list[str] = Field(default_factory=list)
    output_excerpt: str | None = None
    failure_reason: str | None = None


class EvalSummary(BaseModel):
    total_scenarios: int
    passed: int
    failed: int
    errored: int
    results: list[EvalScenarioResult]
