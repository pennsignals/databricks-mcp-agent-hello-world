from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .storage.spark import get_spark_session

DEFAULT_CONFIG_PATH = "workspace-config.yml"
DEFAULT_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
FORBIDDEN_LOCAL_DOTENV_KEYS = {
    "DATABRICKS_HOST",
    "DATABRICKS_TOKEN",
    "DATABRICKS_CLIENT_ID",
    "DATABRICKS_CLIENT_SECRET",
}
SUPPORTED_TOOL_PROVIDER_TYPES = {"local_python", "managed_mcp"}
DEPRECATED_CONFIG_ALIASES = {
    "provider_type": "tool_provider_type",
    "databricks_cli_profile": "databricks_config_profile",
}
ALLOWED_TOP_LEVEL_CONFIG_KEYS = {
    "tool_provider_type",
    "provider_type",
    "llm_endpoint_name",
    "max_agent_steps",
    "storage",
    "prompts",
    "agent_system_prompt_path",
    "databricks_config_profile",
    "databricks_cli_profile",
    "workspace_host",
    "log_level",
}
ALLOWED_NESTED_CONFIG_KEYS = {
    "storage": {"agent_events_table", "local_data_dir"},
    "prompts": {"agent_system_prompt"},
}
IGNORED_TOP_LEVEL_CONFIG_KEYS = {"auth_mode", "local_tool_backend_mode", "sql"}
IGNORED_NESTED_CONFIG_KEYS = {
    "storage": {"agent_runs_table", "agent_output_table"},
}
REMOVED_DOTENV_KEYS = {
    "AUTH_MODE",
    "LOCAL_TOOL_BACKEND_MODE",
}

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StorageConfig:
    agent_events_table: str | None
    local_data_dir: str = "./.local_state"


@dataclass(slots=True)
class PromptConfig:
    agent_system_prompt_path: str
    agent_system_prompt: str


@dataclass(slots=True)
class Settings:
    tool_provider_type: str
    llm_endpoint_name: str
    max_agent_steps: int
    storage: StorageConfig
    prompts: PromptConfig
    databricks_config_profile: str | None = None
    workspace_host: str | None = None
    log_level: str = "INFO"
    config_path: str | None = None
    dotenv_path: str | None = None

    @property
    def provider_type(self) -> str:
        return self.tool_provider_type


def resolve_config_path(config_path: str | None = None) -> str:
    return str(Path(config_path or DEFAULT_CONFIG_PATH))


def load_yaml_config(config_path: str | None = None) -> dict[str, Any]:
    resolved_path = Path(resolve_config_path(config_path))
    if not resolved_path.exists():
        raise FileNotFoundError(f"Config file not found: {resolved_path}")
    with resolved_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError("Config file must parse to a YAML mapping.")
    return data


def load_dotenv_values(config_path: str | None = None) -> tuple[str | None, dict[str, str]]:
    config_dir = Path(resolve_config_path(config_path)).resolve().parent
    dotenv_path = config_dir / ".env"
    if not dotenv_path.exists():
        return None, {}
    values = _parse_dotenv(dotenv_path)
    forbidden_keys = sorted(FORBIDDEN_LOCAL_DOTENV_KEYS.intersection(values))
    if forbidden_keys:
        keys = ", ".join(forbidden_keys)
        raise ValueError(
            "Local .env must not contain direct Databricks credentials for the supported "
            f"quickstart path: {keys}"
        )
    return str(dotenv_path), values


def collect_config_warnings(raw_config: dict[str, Any]) -> list[str]:
    warnings_by_path: dict[str, str] = {}

    for alias_key, canonical_key in DEPRECATED_CONFIG_ALIASES.items():
        if alias_key in raw_config:
            warnings_by_path[alias_key] = (
                f"Deprecated config key '{alias_key}' used; use '{canonical_key}' instead."
            )

    for key in sorted(raw_config):
        if key in IGNORED_TOP_LEVEL_CONFIG_KEYS:
            warnings_by_path[key] = (
                f"Unused config key '{key}' is ignored by the current runtime."
            )
            continue
        if key not in ALLOWED_TOP_LEVEL_CONFIG_KEYS:
            warnings_by_path[key] = (
                f"Unused config key '{key}' is ignored by the current runtime."
            )
            continue

        allowed_nested_keys = ALLOWED_NESTED_CONFIG_KEYS.get(key)
        if not allowed_nested_keys:
            continue
        section = raw_config.get(key)
        if not isinstance(section, dict):
            continue
        ignored_nested_keys = IGNORED_NESTED_CONFIG_KEYS.get(key, set())
        for nested_key in sorted(section):
            nested_path = f"{key}.{nested_key}"
            if nested_key in ignored_nested_keys or nested_key not in allowed_nested_keys:
                warnings_by_path[nested_path] = (
                    f"Unused config key '{nested_path}' is ignored by the current runtime."
                )

    return [warnings_by_path[path] for path in sorted(warnings_by_path)]


def collect_dotenv_warnings(dotenv_values: dict[str, str]) -> list[str]:
    warnings_by_key = {
        key: f"Unused .env key '{key}' is ignored by the current runtime."
        for key in REMOVED_DOTENV_KEYS
        if key in dotenv_values
    }
    return [warnings_by_key[key] for key in sorted(warnings_by_key)]


def resolve_deprecated_config_aliases(raw_config: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(raw_config)
    for alias_key, canonical_key in DEPRECATED_CONFIG_ALIASES.items():
        if canonical_key not in resolved and alias_key in raw_config:
            resolved[canonical_key] = raw_config[alias_key]
    return resolved


def build_settings(
    raw: dict[str, Any],
    *,
    config_path: str | None = None,
    dotenv_path: str | None = None,
    dotenv_values: dict[str, str] | None = None,
) -> Settings:
    dotenv_values = dotenv_values or {}
    agent_prompt_path = _resolve_value(
        yaml_value=raw.get("agent_system_prompt_path"),
        dotenv_values=dotenv_values,
        dotenv_key="AGENT_SYSTEM_PROMPT_PATH",
        default=str(DEFAULT_PROMPT_DIR / "agent_system_prompt.txt"),
    )

    return Settings(
        tool_provider_type=(
            _resolve_value(
                yaml_value=raw.get("tool_provider_type"),
                dotenv_values=dotenv_values,
                dotenv_key="TOOL_PROVIDER_TYPE",
                default="local_python",
            )
            or "local_python"
        ),
        llm_endpoint_name=(
            _resolve_value(
                yaml_value=raw.get("llm_endpoint_name"),
                dotenv_values=dotenv_values,
                dotenv_key="LLM_ENDPOINT_NAME",
            )
            or ""
        ),
        max_agent_steps=_coerce_int(
            _resolve_value(
                yaml_value=raw.get("max_agent_steps"),
                dotenv_values=dotenv_values,
                dotenv_key="MAX_AGENT_STEPS",
                default="8",
            ),
            name="max_agent_steps",
        ),
        storage=StorageConfig(
            agent_events_table=_resolve_value(
                yaml_value=_deep_get(raw, "storage", "agent_events_table"),
                dotenv_values=dotenv_values,
                dotenv_key="AGENT_EVENTS_TABLE",
            ),
            local_data_dir=(
                _resolve_value(
                    yaml_value=_deep_get(raw, "storage", "local_data_dir"),
                    dotenv_values=dotenv_values,
                    dotenv_key="LOCAL_DATA_DIR",
                    default="./.local_state",
                )
                or "./.local_state"
            ),
        ),
        prompts=PromptConfig(
            agent_system_prompt_path=agent_prompt_path,
            agent_system_prompt=_read_prompt(
                agent_prompt_path,
                _deep_get(
                    raw,
                    "prompts",
                    "agent_system_prompt",
                    default="Use the provided tools when helpful.",
                ),
            ),
        ),
        databricks_config_profile=_resolve_value(
            yaml_value=raw.get("databricks_config_profile"),
            dotenv_values=dotenv_values,
            dotenv_key="DATABRICKS_CONFIG_PROFILE",
        ),
        workspace_host=_resolve_value(
            yaml_value=raw.get("workspace_host"),
            dotenv_values=dotenv_values,
            dotenv_key="DATABRICKS_HOST",
        ),
        log_level=(
            _resolve_value(
                yaml_value=raw.get("log_level"),
                dotenv_values=dotenv_values,
                dotenv_key="LOG_LEVEL",
                default="INFO",
            )
            or "INFO"
        ),
        config_path=resolve_config_path(config_path),
        dotenv_path=dotenv_path,
    )


def validate_settings(settings: Settings) -> None:
    missing_required: list[str] = []
    if not settings.llm_endpoint_name.strip():
        missing_required.append("llm_endpoint_name")
    if not (settings.storage.local_data_dir or "").strip():
        missing_required.append("storage.local_data_dir")
    if get_spark_session() is not None and not (settings.storage.agent_events_table or "").strip():
        missing_required.append("storage.agent_events_table")
    if missing_required:
        formatted = ", ".join(missing_required)
        raise ValueError(f"Missing required settings: {formatted}")

    if settings.tool_provider_type not in SUPPORTED_TOOL_PROVIDER_TYPES:
        supported = ", ".join(sorted(SUPPORTED_TOOL_PROVIDER_TYPES))
        raise ValueError(
            "Unsupported tool_provider_type "
            f"{settings.tool_provider_type!r}. Supported values: {supported}"
        )
    if settings.max_agent_steps < 1:
        raise ValueError("max_agent_steps must be at least 1.")


def load_settings(config_path: str | None = None, *, validate: bool = True) -> Settings:
    raw = load_yaml_config(config_path)
    dotenv_path, dotenv_values = load_dotenv_values(config_path)
    warnings = collect_config_warnings(raw) + collect_dotenv_warnings(dotenv_values)
    resolved_raw = resolve_deprecated_config_aliases(raw)
    settings = build_settings(
        resolved_raw,
        config_path=config_path,
        dotenv_path=dotenv_path,
        dotenv_values=dotenv_values,
    )
    for warning in warnings:
        logger.warning(warning)
    if validate:
        validate_settings(settings)
    return settings


def parse_task_input(task_input_json: str | None) -> dict[str, Any]:
    if not task_input_json:
        return {}
    payload = json.loads(task_input_json)
    if not isinstance(payload, dict):
        raise ValueError("Task input JSON must decode to an object.")
    return payload


def parse_task_input_file(task_input_file: str | None) -> dict[str, Any]:
    if not task_input_file:
        return {}
    return parse_task_input(Path(task_input_file).read_text(encoding="utf-8"))


def _deep_get(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def _resolve_value(
    *,
    yaml_value: Any = None,
    dotenv_values: dict[str, str],
    dotenv_key: str,
    default: str | None = None,
) -> Any:
    if yaml_value is not None:
        return yaml_value
    if dotenv_key in dotenv_values:
        return dotenv_values[dotenv_key]
    return default


def _read_prompt(path: str, fallback: str) -> str:
    prompt_path = Path(path)
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8").strip()
    return fallback


def _parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid .env line {line_number} in {path}: {raw_line}")
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def _coerce_int(value: Any, *, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer.") from exc
