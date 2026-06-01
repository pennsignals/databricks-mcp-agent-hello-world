from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = "workspace-config.yml"
DEFAULT_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
FORBIDDEN_LOCAL_DOTENV_KEYS = {
    "DATABRICKS_TOKEN",
    "DATABRICKS_CLIENT_ID",
    "DATABRICKS_CLIENT_SECRET",
}
ALLOWED_LOCAL_DOTENV_KEYS = {
    "AGENT_EVENTS_TABLE",
    "AGENT_SYSTEM_PROMPT_PATH",
    "DATABRICKS_CONFIG_PROFILE",
    "DATABRICKS_HOST",
    "DATABRICKS_MCP_SERVER_NAME",
    "DATABRICKS_MCP_SERVER_URL",
    "LLM_ENDPOINT_NAME",
    "LOCAL_DATA_DIR",
    "LOG_LEVEL",
    "MAX_AGENT_STEPS",
}
ALLOWED_CONFIG_KEYS = {
    "llm_endpoint_name": None,
    "agent_system_prompt_path": None,
    "max_agent_steps": None,
    "log_level": None,
    "databricks_config_profile": None,
    "workspace_host": None,
    "tools": {
        "local_python": {"enabled": None},
        "databricks_mcp": {
            "enabled": None,
            "server": {"name": None, "url": None},
        },
    },
    "storage": {
        "local_data_dir": None,
        "agent_events_table": None,
    },
}


@dataclass(slots=True)
class StorageConfig:
    agent_events_table: str | None
    local_data_dir: str = "./.local_state"


@dataclass(slots=True)
class PromptConfig:
    agent_system_prompt_path: str
    agent_system_prompt: str


@dataclass(slots=True)
class MCPServerConfig:
    name: str
    url: str


@dataclass(slots=True)
class LocalPythonToolsConfig:
    enabled: bool = True


@dataclass(slots=True)
class DatabricksMCPToolsConfig:
    enabled: bool = False
    server: MCPServerConfig | None = None


@dataclass(slots=True)
class ToolsConfig:
    local_python: LocalPythonToolsConfig = field(default_factory=LocalPythonToolsConfig)
    databricks_mcp: DatabricksMCPToolsConfig = field(default_factory=DatabricksMCPToolsConfig)


@dataclass(slots=True)
class Settings:
    llm_endpoint_name: str
    max_agent_steps: int
    tools: ToolsConfig
    storage: StorageConfig
    prompts: PromptConfig
    databricks_config_profile: str | None = None
    workspace_host: str | None = None
    log_level: str = "INFO"
    config_path: str | None = None
    dotenv_path: str | None = None


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


def validate_unknown_keys(
    data: Mapping[str, Any],
    allowed: Mapping[str, Any],
    prefix: str = "",
) -> None:
    for key, value in data.items():
        key_path = f"{prefix}{key}"
        if key not in allowed:
            supported = ", ".join(f"{prefix}{supported_key}" for supported_key in sorted(allowed))
            raise ValueError(f"Unknown config key: {key_path}. Supported keys: {supported}")
        nested_allowed = allowed[key]
        if isinstance(nested_allowed, dict) and not isinstance(value, Mapping):
            raise ValueError(f"{key_path} must be a YAML mapping.")
        if isinstance(nested_allowed, dict):
            validate_unknown_keys(value, nested_allowed, f"{key_path}.")


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
            "Local .env must not contain forbidden Databricks auth material for the supported "
            f"quickstart path: {keys}"
        )
    unsupported_keys = sorted(set(values).difference(ALLOWED_LOCAL_DOTENV_KEYS))
    if unsupported_keys:
        keys = ", ".join(unsupported_keys)
        raise ValueError(
            "Local .env contains unsupported keys. Remove them or move them out of "
            f"repo-local .env: {keys}"
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
    yaml_agent_prompt_path = raw.get("agent_system_prompt_path")
    agent_prompt_path_from_yaml = (
        "agent_system_prompt_path" in raw and yaml_agent_prompt_path is not None
    )
    agent_prompt_path_from_env = "AGENT_SYSTEM_PROMPT_PATH" in dotenv_values
    agent_prompt_path_explicit = agent_prompt_path_from_yaml or agent_prompt_path_from_env
    if agent_prompt_path_from_yaml:
        agent_prompt_path = yaml_agent_prompt_path
    elif agent_prompt_path_from_env:
        agent_prompt_path = dotenv_values["AGENT_SYSTEM_PROMPT_PATH"]
    else:
        agent_prompt_path = str(DEFAULT_PROMPT_DIR / "agent_system_prompt.txt")
    if agent_prompt_path_explicit and str(agent_prompt_path or "").strip():
        prompt_path = Path(str(agent_prompt_path))
        if not prompt_path.is_absolute():
            config_dir = Path(resolve_config_path(config_path)).resolve().parent
            agent_prompt_path = str(config_dir / prompt_path)
    agent_prompt_path = str(agent_prompt_path or "")

    return Settings(
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
        tools=_build_tools_config(raw, dotenv_values),
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
                "Use the provided tools when helpful.",
                explicit_path=agent_prompt_path_explicit,
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
    if missing_required:
        formatted = ", ".join(missing_required)
        raise ValueError(f"Missing required settings: {formatted}")

    if not enabled_tool_sources(settings):
        raise ValueError("At least one tool source must be enabled.")
    if settings.tools.databricks_mcp.enabled and (
        settings.tools.databricks_mcp.server is None
        or not settings.tools.databricks_mcp.server.name.strip()
        or not settings.tools.databricks_mcp.server.url.strip()
    ):
        raise ValueError(
            "databricks_mcp requires tools.databricks_mcp.server.name and "
            "tools.databricks_mcp.server.url."
        )
    if settings.max_agent_steps < 1:
        raise ValueError("max_agent_steps must be at least 1.")


def load_settings(
    config_path: str | None = None,
    *,
    validate: bool = True,
) -> Settings:
    raw = load_yaml_config(config_path)
    validate_unknown_keys(raw, ALLOWED_CONFIG_KEYS)
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


def enabled_tool_sources(settings: Settings) -> list[str]:
    sources: list[str] = []
    if settings.tools.local_python.enabled:
        sources.append("local_python")
    if settings.tools.databricks_mcp.enabled:
        sources.append("databricks_mcp")
    return sources


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
    default: Any = None,
) -> Any:
    if yaml_value is not None:
        return yaml_value
    if dotenv_key in dotenv_values:
        return dotenv_values[dotenv_key]
    return default


def _read_prompt(path: str, fallback: str, *, explicit_path: bool = False) -> str:
    if explicit_path and not path.strip():
        raise ValueError("Configured agent system prompt path must not be empty.")

    prompt_path = Path(path)
    if not prompt_path.exists():
        if explicit_path:
            raise FileNotFoundError(
                f"Configured agent system prompt path does not exist: {prompt_path}"
            )
        return fallback

    if not prompt_path.is_file():
        if explicit_path:
            raise ValueError(f"Configured agent system prompt path is not a file: {prompt_path}")
        return fallback

    text = prompt_path.read_text(encoding="utf-8").strip()
    if not text:
        if explicit_path:
            raise ValueError(f"Configured agent system prompt file is empty: {prompt_path}")
        raise ValueError(f"Agent system prompt file is empty: {prompt_path}")
    return text


def _build_tools_config(raw: dict[str, Any], dotenv_values: dict[str, str]) -> ToolsConfig:
    local_enabled = _coerce_bool(
        _deep_get(raw, "tools", "local_python", "enabled", default=True),
        name="tools.local_python.enabled",
    )
    databricks_mcp_enabled = _coerce_bool(
        _deep_get(raw, "tools", "databricks_mcp", "enabled", default=False),
        name="tools.databricks_mcp.enabled",
    )
    server = _deep_get(raw, "tools", "databricks_mcp", "server")
    url = _resolve_value(
        yaml_value=_deep_get(raw, "tools", "databricks_mcp", "server", "url"),
        dotenv_values=dotenv_values,
        dotenv_key="DATABRICKS_MCP_SERVER_URL",
    )
    name = _resolve_value(
        yaml_value=_deep_get(raw, "tools", "databricks_mcp", "server", "name"),
        dotenv_values=dotenv_values,
        dotenv_key="DATABRICKS_MCP_SERVER_NAME",
    )
    mcp_server = None
    if server is not None or url is not None or name is not None:
        mcp_server = MCPServerConfig(name=str(name or ""), url=str(url or ""))

    return ToolsConfig(
        local_python=LocalPythonToolsConfig(enabled=local_enabled),
        databricks_mcp=DatabricksMCPToolsConfig(
            enabled=databricks_mcp_enabled,
            server=mcp_server,
        ),
    )


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


def _coerce_bool(value: Any, *, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise ValueError(f"{name} must be a boolean.")
