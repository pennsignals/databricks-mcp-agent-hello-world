from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class ToolSpec(BaseModel):
    """Provider-discovered tool metadata exposed to the runtime LLM loop."""

    tool_name: str
    description: str
    input_schema: dict[str, Any]
    provider_type: str
    provider_id: str
    version: str = "1"
    capability_tags: list[str] = Field(default_factory=list)
    side_effect_level: Literal["read_only", "write"] = "read_only"
    data_domains: list[str] = Field(default_factory=list)
    example_uses: list[str] = Field(default_factory=list)

    @staticmethod
    def _normalize_metadata_values(values: list[str], field_name: str) -> list[str]:
        normalized_values: set[str] = set()
        for raw_value in values:
            candidate = raw_value.strip().lower()
            if not candidate:
                raise ValueError(f"{field_name} entries must not be empty")
            if not re.fullmatch(r"[a-z0-9_]+", candidate):
                raise ValueError(
                    f"{field_name} entries must be lowercase snake_case strings; got {raw_value!r}"
                )
            normalized_values.add(candidate)
        return sorted(normalized_values)

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

    @field_validator("capability_tags", "data_domains", "example_uses")
    @classmethod
    def validate_metadata_list(cls, value: list[str], info) -> list[str]:
        if info.field_name == "example_uses":
            normalized_values: list[str] = []
            for raw_value in value:
                candidate = raw_value.strip()
                if not candidate:
                    raise ValueError("example_uses entries must not be empty")
                if candidate not in normalized_values:
                    normalized_values.append(candidate)
            return normalized_values
        return cls._normalize_metadata_values(value, info.field_name)

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
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AgentOutputRecord(BaseModel):
    run_id: str
    task_name: str
    status: str
    output_payload: dict[str, Any]
    error_message: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DiscoveryReport(BaseModel):
    provider_type: str
    tool_count: int
    provider_id: str
    inventory_hash: str
    tools: list[ToolSpec]


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
    task_input: AgentTaskRequest

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
    def validate_tool_call_bounds(self) -> "EvalScenario":
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


class EvalRunReport(BaseModel):
    scenario_file: str
    total_scenarios: int
    passed_scenarios: int
    failed_scenarios: int
    all_passed: bool
    results: list[EvalScenarioResult]
