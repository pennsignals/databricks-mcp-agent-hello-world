from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = "workspace-config.yml"
DEFAULT_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
FORBIDDEN_LOCAL_DOTENV_KEYS = {
    "DATABRICKS_HOST",
    "DATABRICKS_TOKEN",
    "DATABRICKS_CLIENT_ID",
    "DATABRICKS_CLIENT_SECRET",
}
SUPPORTED_TOOL_PROVIDER_TYPES = {"local_python", "managed_mcp"}
SQL_OPTIONAL_PROVIDER_TYPES = {"local_python"}


@dataclass(slots=True)
class StorageConfig:
    agent_runs_table: str | None
    agent_output_table: str | None
    local_data_dir: str = "./.local_state"

    @property
    def agent_outputs_table(self) -> str | None:
        return self.agent_output_table


@dataclass(slots=True)
class SqlToolConfig:
    warehouse_id: str | None = None
    catalog: str | None = None
    schema: str | None = None
    incident_kb_table: str | None = None
    runbook_table: str | None = None
    customer_summary_table: str | None = None
    service_incidents_table: str | None = None
    service_dependencies_table: str | None = None


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
    databricks_cli_profile: str | None = None
    workspace_host: str | None = None
    local_tool_backend_mode: str = "auto"
    auth_mode: str = "local-dev"
    log_level: str = "INFO"
    config_path: str | None = None
    dotenv_path: str | None = None
    sql: SqlToolConfig = field(default_factory=SqlToolConfig)

    @property
    def provider_type(self) -> str:
        return self.tool_provider_type

    @property
    def sql_config_is_optional(self) -> bool:
        return self.tool_provider_type in SQL_OPTIONAL_PROVIDER_TYPES

    @property
    def sql_config_required(self) -> bool:
        return not self.sql_config_is_optional


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
                yaml_value=raw.get("tool_provider_type", raw.get("provider_type")),
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
            agent_runs_table=_resolve_value(
                yaml_value=_deep_get(raw, "storage", "agent_runs_table"),
                dotenv_values=dotenv_values,
                dotenv_key="AGENT_RUNS_TABLE",
            ),
            agent_output_table=_resolve_value(
                yaml_value=_deep_get(raw, "storage", "agent_output_table")
                or _deep_get(raw, "storage", "agent_outputs_table"),
                dotenv_values=dotenv_values,
                dotenv_key="AGENT_OUTPUT_TABLE",
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
        databricks_cli_profile=_resolve_value(
            yaml_value=raw.get("databricks_config_profile") or raw.get("databricks_cli_profile"),
            dotenv_values=dotenv_values,
            dotenv_key="DATABRICKS_CONFIG_PROFILE",
        ),
        workspace_host=_resolve_value(
            yaml_value=raw.get("workspace_host"),
            dotenv_values=dotenv_values,
            dotenv_key="DATABRICKS_HOST",
        ),
        local_tool_backend_mode=(
            _resolve_value(
                yaml_value=raw.get("local_tool_backend_mode"),
                dotenv_values=dotenv_values,
                dotenv_key="LOCAL_TOOL_BACKEND_MODE",
                default="auto",
            )
            or "auto"
        ),
        auth_mode=(
            _resolve_value(
                yaml_value=raw.get("auth_mode"),
                dotenv_values=dotenv_values,
                dotenv_key="AUTH_MODE",
                default="local-dev",
            )
            or "local-dev"
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
        sql=SqlToolConfig(
            warehouse_id=_resolve_value(
                yaml_value=_deep_get(raw, "sql", "warehouse_id"),
                dotenv_values=dotenv_values,
                dotenv_key="DATABRICKS_SQL_WAREHOUSE_ID",
            ),
            catalog=_resolve_value(
                yaml_value=_deep_get(raw, "sql", "catalog"),
                dotenv_values=dotenv_values,
                dotenv_key="DATABRICKS_SQL_CATALOG",
            ),
            schema=_resolve_value(
                yaml_value=_deep_get(raw, "sql", "schema"),
                dotenv_values=dotenv_values,
                dotenv_key="DATABRICKS_SQL_SCHEMA",
            ),
            incident_kb_table=_resolve_value(
                yaml_value=_deep_get(raw, "sql", "incident_kb_table"),
                dotenv_values=dotenv_values,
                dotenv_key="INCIDENT_KB_TABLE",
            ),
            runbook_table=_resolve_value(
                yaml_value=_deep_get(raw, "sql", "runbook_table"),
                dotenv_values=dotenv_values,
                dotenv_key="RUNBOOK_TABLE",
            ),
            customer_summary_table=_resolve_value(
                yaml_value=_deep_get(raw, "sql", "customer_summary_table"),
                dotenv_values=dotenv_values,
                dotenv_key="CUSTOMER_SUMMARY_TABLE",
            ),
            service_incidents_table=_resolve_value(
                yaml_value=_deep_get(raw, "sql", "service_incidents_table"),
                dotenv_values=dotenv_values,
                dotenv_key="SERVICE_INCIDENTS_TABLE",
            ),
            service_dependencies_table=_resolve_value(
                yaml_value=_deep_get(raw, "sql", "service_dependencies_table"),
                dotenv_values=dotenv_values,
                dotenv_key="SERVICE_DEPENDENCIES_TABLE",
            ),
        ),
    )


def validate_settings(settings: Settings) -> None:
    missing_required: list[str] = []
    if not settings.llm_endpoint_name.strip():
        missing_required.append("llm_endpoint_name")
    if not (settings.storage.agent_runs_table or "").strip():
        missing_required.append("storage.agent_runs_table")
    if not (settings.storage.agent_output_table or "").strip():
        missing_required.append("storage.agent_output_table")
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
    settings = build_settings(
        raw,
        config_path=config_path,
        dotenv_path=dotenv_path,
        dotenv_values=dotenv_values,
    )
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
