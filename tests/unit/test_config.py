from __future__ import annotations

from pathlib import Path

import pytest

from databricks_mcp_agent_hello_world.config import (
    build_settings,
    load_dotenv_values,
    load_settings,
    load_yaml_config,
)
from tests.conftest import REPO_ROOT, write_workspace_config


def test_load_settings_reads_agent_prompt_file(tmp_path: Path) -> None:
    config_path = write_workspace_config(tmp_path)
    agent_prompt = tmp_path / "agent.txt"
    agent_prompt.write_text("agent prompt", encoding="utf-8")
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n"
        + f"agent_system_prompt_path: {agent_prompt}\n",
        encoding="utf-8",
    )

    settings = load_settings(str(config_path))

    assert settings.prompts.agent_system_prompt == "agent prompt"


def test_load_settings_requires_current_required_fields(tmp_path: Path) -> None:
    config_path = write_workspace_config(tmp_path, llm_endpoint_name="''")

    with pytest.raises(ValueError, match="llm_endpoint_name"):
        load_settings(str(config_path))


def test_load_settings_prefers_yaml_over_dotenv(tmp_path: Path) -> None:
    config_path = write_workspace_config(tmp_path)
    (tmp_path / ".env").write_text(
        "LLM_ENDPOINT_NAME=dotenv-endpoint\nDATABRICKS_CONFIG_PROFILE=DOTENV\n",
        encoding="utf-8",
    )

    settings = load_settings(str(config_path))

    assert settings.llm_endpoint_name == "endpoint-a"
    assert settings.databricks_config_profile == "DEFAULT"


def test_supported_env_vars_override_defaults_when_yaml_omits_values(tmp_path: Path) -> None:
    config_path = write_workspace_config(tmp_path, include_databricks_profile=False)
    raw = load_yaml_config(str(config_path))
    del raw["storage"]["agent_events_table"]
    del raw["storage"]["local_data_dir"]
    raw["tools"]["databricks_mcp"]["enabled"] = True
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "LLM_ENDPOINT_NAME=dotenv-endpoint",
                "AGENT_SYSTEM_PROMPT_PATH=tests/prompt.txt",
                "MAX_AGENT_STEPS=12",
                "LOG_LEVEL=DEBUG",
                "DATABRICKS_CONFIG_PROFILE=FROM_DOTENV",
                "DATABRICKS_HOST=https://example.cloud.databricks.com",
                "DATABRICKS_MCP_SERVER_NAME=uc_functions",
                "DATABRICKS_MCP_SERVER_URL=https://example.cloud.databricks.com/api/2.0/mcp",
                "AGENT_EVENTS_TABLE=main.agent.env_events",
                "LOCAL_DATA_DIR=./env_state",
            ]
        ),
        encoding="utf-8",
    )
    dotenv_path, dotenv_values = load_dotenv_values(str(config_path))

    settings = build_settings(
        raw,
        config_path=str(config_path),
        dotenv_path=dotenv_path,
        dotenv_values=dotenv_values,
    )

    assert settings.llm_endpoint_name == "endpoint-a"
    assert settings.tools.local_python.enabled is True
    assert settings.tools.databricks_mcp.enabled is True
    assert settings.prompts.agent_system_prompt_path == "tests/prompt.txt"
    assert settings.max_agent_steps == 12
    assert settings.log_level == "DEBUG"
    assert settings.databricks_config_profile == "FROM_DOTENV"
    assert settings.workspace_host == "https://example.cloud.databricks.com"
    assert settings.tools.databricks_mcp.server is not None
    assert settings.tools.databricks_mcp.server.name == "uc_functions"
    assert settings.tools.databricks_mcp.server.url == (
        "https://example.cloud.databricks.com/api/2.0/mcp"
    )
    assert settings.storage.agent_events_table == "main.agent.env_events"
    assert settings.storage.local_data_dir == "./env_state"


def test_load_settings_defaults_log_level_to_info_when_omitted(tmp_path: Path) -> None:
    settings = load_settings(str(write_workspace_config(tmp_path)))

    assert settings.log_level == "INFO"


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "DATABRICKS_TOKEN",
        "DATABRICKS_CLIENT_ID",
        "DATABRICKS_CLIENT_SECRET",
    ],
)
def test_load_dotenv_rejects_forbidden_databricks_auth_material(
    tmp_path: Path,
    forbidden_key: str,
) -> None:
    config_path = write_workspace_config(tmp_path)
    (tmp_path / ".env").write_text(f"{forbidden_key}=forbidden\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must not contain forbidden Databricks auth material"):
        load_dotenv_values(str(config_path))


def test_canonical_config_keys_load_successfully(tmp_path: Path) -> None:
    config_path = write_workspace_config(
        tmp_path,
        extra_lines=[
            "agent_system_prompt_path: tests/prompt.txt",
            "max_agent_steps: 4",
            "log_level: DEBUG",
            "workspace_host: https://example.cloud.databricks.com",
            "tools:",
            "  local_python:",
            "    enabled: true",
            "  databricks_mcp:",
            "    enabled: true",
            "    server:",
            "      name: uc_functions",
            "      url: https://example.cloud.databricks.com/api/2.0/mcp",
        ],
    )

    settings = load_settings(str(config_path))

    assert settings.tools.local_python.enabled is True
    assert settings.tools.databricks_mcp.enabled is True
    assert settings.storage.agent_events_table == "main.agent.agent_events"
    assert settings.tools.databricks_mcp.server is not None
    assert settings.tools.databricks_mcp.server.name == "uc_functions"


def test_checked_in_example_config_loads_cleanly() -> None:
    settings = load_settings(str(REPO_ROOT / "workspace-config.example.yml"), validate=False)

    assert settings.tools.local_python.enabled is True
    assert settings.tools.databricks_mcp.enabled is False
    assert settings.tools.databricks_mcp.server is None


@pytest.mark.parametrize(
    ("extra_lines", "message"),
    [
        (["arbitrary_key: true"], "Unknown config key: arbitrary_key"),
    ],
)
def test_unknown_top_level_config_keys_fail(
    tmp_path: Path,
    extra_lines: list[str],
    message: str,
) -> None:
    config_path = write_workspace_config(tmp_path, extra_lines=extra_lines)

    with pytest.raises(ValueError, match=message):
        load_settings(str(config_path))


@pytest.mark.parametrize(
    ("nested_key", "message"),
    [
        ("arbitrary_nested", r"Unknown config key: storage\.arbitrary_nested"),
    ],
)
def test_unknown_storage_config_keys_fail(
    tmp_path: Path,
    nested_key: str,
    message: str,
) -> None:
    config_path = tmp_path / "workspace-config.yml"
    config_path.write_text(
        "\n".join(
            [
                "llm_endpoint_name: endpoint-a",
                "storage:",
                "  agent_events_table: main.agent.agent_events",
                "  local_data_dir: ./.local_state",
                f"  {nested_key}: stale",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        load_settings(str(config_path))


@pytest.mark.parametrize(
    ("extra_lines", "message"),
    [
        (["storage: not-a-mapping"], "storage must be a YAML mapping"),
        (
            ["tools:", "  databricks_mcp:", "    server: not-a-mapping"],
            r"tools\.databricks_mcp\.server must be a YAML mapping",
        ),
    ],
)
def test_mapping_config_sections_reject_scalar_values(
    tmp_path: Path,
    extra_lines: list[str],
    message: str,
) -> None:
    config_path = write_workspace_config(tmp_path, extra_lines=extra_lines)

    with pytest.raises(ValueError, match=message):
        load_settings(str(config_path))


def test_load_settings_accepts_databricks_mcp_config(tmp_path: Path) -> None:
    config_path = write_workspace_config(
        tmp_path,
        databricks_mcp_enabled=True,
        mcp_source_server_name="uc_functions",
        mcp_source_server_url=(
            "https://example.cloud.databricks.com/api/2.0/mcp/functions/main/demo"
        ),
    )

    settings = load_settings(str(config_path))

    assert settings.tools.local_python.enabled is True
    assert settings.tools.databricks_mcp.enabled is True
    assert settings.tools.databricks_mcp.server is not None
    assert settings.tools.databricks_mcp.server.name == "uc_functions"
