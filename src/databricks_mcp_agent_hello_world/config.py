from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


@dataclass(slots=True)
class StorageConfig:
    tool_profiles_table: str | None
    agent_runs_table: str | None
    agent_outputs_table: str | None
    local_data_dir: str = "./.local_state"


@dataclass(slots=True)
class PromptConfig:
    filter_prompt_path: str
    audit_prompt_path: str
    agent_system_prompt_path: str
    filter_prompt: str
    audit_prompt: str
    agent_system_prompt: str


@dataclass(slots=True)
class Settings:
    provider_type: str
    llm_endpoint_name: str
    active_profile_name: str
    max_allowed_tools: int
    max_agent_steps: int
    storage: StorageConfig
    prompts: PromptConfig
    databricks_cli_profile: str | None = None
    workspace_host: str | None = None
    auth_mode: str = "local-dev"
    log_level: str = "INFO"
    config_path: str | None = None


def _read_yaml(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with file_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def _read_prompt(path: str, fallback: str) -> str:
    prompt_path = Path(path)
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8").strip()
    return fallback


def _deep_get(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def load_settings(config_path: str | None = None) -> Settings:
    raw = _read_yaml(config_path or _env("AGENT_CONFIG_PATH"))
    filter_prompt_path = _env(
        "TOOL_FILTER_PROMPT_PATH",
        raw.get("tool_filter_prompt_path", str(DEFAULT_PROMPT_DIR / "tool_filter_prompt.txt")),
    ) or str(DEFAULT_PROMPT_DIR / "tool_filter_prompt.txt")
    audit_prompt_path = _env(
        "TOOL_AUDIT_PROMPT_PATH",
        raw.get("tool_audit_prompt_path", str(DEFAULT_PROMPT_DIR / "tool_audit_prompt.txt")),
    ) or str(DEFAULT_PROMPT_DIR / "tool_audit_prompt.txt")
    agent_prompt_path = _env(
        "AGENT_SYSTEM_PROMPT_PATH",
        raw.get("agent_system_prompt_path", str(DEFAULT_PROMPT_DIR / "agent_system_prompt.txt")),
    ) or str(DEFAULT_PROMPT_DIR / "agent_system_prompt.txt")

    settings = Settings(
        provider_type=_env(
            "TOOL_PROVIDER_TYPE",
            raw.get("tool_provider_type", raw.get("provider_type", "local_python")),
        )
        or "local_python",
        llm_endpoint_name=_env("LLM_ENDPOINT_NAME", raw.get("llm_endpoint_name")) or "",
        active_profile_name=_env(
            "ACTIVE_PROFILE_NAME",
            raw.get("active_profile_name", raw.get("profile_name", "default")),
        )
        or "default",
        max_allowed_tools=int(
            _env("MAX_ALLOWED_TOOLS", str(raw.get("max_allowed_tools", 4))) or "4"
        ),
        max_agent_steps=int(_env("MAX_AGENT_STEPS", str(raw.get("max_agent_steps", 8))) or "8"),
        storage=StorageConfig(
            tool_profiles_table=_env(
                "TOOL_PROFILE_TABLE", _deep_get(raw, "storage", "tool_profiles_table")
            ),
            agent_runs_table=_env(
                "AGENT_RUNS_TABLE", _deep_get(raw, "storage", "agent_runs_table")
            ),
            agent_outputs_table=_env(
                "AGENT_OUTPUT_TABLE", _deep_get(raw, "storage", "agent_outputs_table")
            ),
            local_data_dir=_env(
                "LOCAL_DATA_DIR",
                _deep_get(raw, "storage", "local_data_dir", default="./.local_state"),
            )
            or "./.local_state",
        ),
        prompts=PromptConfig(
            filter_prompt_path=filter_prompt_path,
            audit_prompt_path=audit_prompt_path,
            agent_system_prompt_path=agent_prompt_path,
            filter_prompt=_read_prompt(
                filter_prompt_path,
                _deep_get(raw, "prompts", "filter_prompt", default="Return JSON only."),
            ),
            audit_prompt=_read_prompt(
                audit_prompt_path,
                _deep_get(raw, "prompts", "audit_prompt", default="Explain the grouped tools."),
            ),
            agent_system_prompt=_read_prompt(
                agent_prompt_path,
                _deep_get(raw, "prompts", "agent_system_prompt", default="Use tools when helpful."),
            ),
        ),
        databricks_cli_profile=_env("DATABRICKS_CLI_PROFILE", raw.get("databricks_cli_profile")),
        workspace_host=_env("WORKSPACE_HOST", raw.get("workspace_host")),
        auth_mode=_env("AUTH_MODE", raw.get("auth_mode", "local-dev")) or "local-dev",
        log_level=_env("LOG_LEVEL", raw.get("log_level", "INFO")) or "INFO",
        config_path=config_path,
    )

    if not settings.llm_endpoint_name:
        raise ValueError("LLM_ENDPOINT_NAME must be set via environment variable or config file.")
    if settings.provider_type != "local_python":
        raise ValueError(
            "This starter template currently supports provider_type=local_python only."
        )
    if settings.max_allowed_tools < 1:
        raise ValueError("MAX_ALLOWED_TOOLS must be at least 1.")
    if settings.max_agent_steps < 1:
        raise ValueError("MAX_AGENT_STEPS must be at least 1.")
    return settings


def parse_task_input(task_input_json: str | None) -> dict[str, Any]:
    if not task_input_json:
        return {}
    return json.loads(task_input_json)
