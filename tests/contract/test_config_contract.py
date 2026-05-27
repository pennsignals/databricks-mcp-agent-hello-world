from __future__ import annotations

from pathlib import Path

import pytest

from databricks_mcp_agent_hello_world.config import (
    DEFAULT_PROMPT_DIR,
    build_settings,
    load_dotenv_values,
    load_settings,
    load_yaml_config,
)
from tests.conftest import REPO_ROOT, write_workspace_config


def test_load_settings_uses_default_agent_prompt_when_path_is_omitted(tmp_path: Path) -> None:
    config_path = write_workspace_config(tmp_path)

    settings = load_settings(str(config_path))

    assert settings.prompts.agent_system_prompt_path == str(
        DEFAULT_PROMPT_DIR / "agent_system_prompt.txt"
    )
    assert settings.prompts.agent_system_prompt.startswith(
        "You are a non-interactive Databricks batch agent."
    )


def test_load_settings_uses_default_agent_prompt_when_path_is_null(tmp_path: Path) -> None:
    config_path = write_workspace_config(
        tmp_path,
        extra_lines=["agent_system_prompt_path: null"],
    )

    settings = load_settings(str(config_path))

    assert settings.prompts.agent_system_prompt_path == str(
        DEFAULT_PROMPT_DIR / "agent_system_prompt.txt"
    )
    assert settings.prompts.agent_system_prompt.startswith(
        "You are a non-interactive Databricks batch agent."
    )


def test_load_settings_reads_explicit_agent_prompt_file_from_yaml(tmp_path: Path) -> None:
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


def test_load_settings_resolves_relative_agent_prompt_file_from_config_directory(
    tmp_path: Path,
) -> None:
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    agent_prompt = prompt_dir / "agent.txt"
    agent_prompt.write_text("relative agent prompt", encoding="utf-8")
    config_path = write_workspace_config(
        tmp_path,
        extra_lines=["agent_system_prompt_path: prompts/agent.txt"],
    )

    settings = load_settings(str(config_path))

    assert settings.prompts.agent_system_prompt_path == str(agent_prompt)
    assert settings.prompts.agent_system_prompt == "relative agent prompt"


def test_load_settings_rejects_missing_explicit_agent_prompt_file_from_yaml(
    tmp_path: Path,
) -> None:
    missing_prompt = tmp_path / "prompts" / "missing-agent.md"
    config_path = write_workspace_config(
        tmp_path,
        extra_lines=["agent_system_prompt_path: ./prompts/missing-agent.md"],
    )

    with pytest.raises(
        FileNotFoundError,
        match=rf"Configured agent system prompt path does not exist: {missing_prompt}",
    ):
        load_settings(str(config_path))


@pytest.mark.parametrize("configured_path", ['""', '"   "'])
def test_load_settings_rejects_empty_explicit_agent_prompt_path_from_yaml(
    tmp_path: Path,
    configured_path: str,
) -> None:
    config_path = write_workspace_config(
        tmp_path,
        extra_lines=[f"agent_system_prompt_path: {configured_path}"],
    )

    with pytest.raises(
        ValueError,
        match=r"Configured agent system prompt path must not be empty\.",
    ):
        load_settings(str(config_path))


def test_load_settings_rejects_empty_explicit_agent_prompt_file_from_yaml(
    tmp_path: Path,
) -> None:
    agent_prompt = tmp_path / "empty-agent.txt"
    agent_prompt.write_text(" \n", encoding="utf-8")
    config_path = write_workspace_config(
        tmp_path,
        extra_lines=[f"agent_system_prompt_path: {agent_prompt}"],
    )

    with pytest.raises(
        ValueError,
        match=rf"Configured agent system prompt file is empty: {agent_prompt}",
    ):
        load_settings(str(config_path))


def test_load_settings_rejects_directory_explicit_agent_prompt_path_from_yaml(
    tmp_path: Path,
) -> None:
    config_path = write_workspace_config(
        tmp_path,
        extra_lines=["agent_system_prompt_path: ."],
    )

    with pytest.raises(
        ValueError,
        match=rf"Configured agent system prompt path is not a file: {tmp_path}",
    ):
        load_settings(str(config_path))


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
    env_prompt = tmp_path / "env-agent.txt"
    env_prompt.write_text("env agent prompt", encoding="utf-8")
    raw = load_yaml_config(str(config_path))
    del raw["storage"]["agent_events_table"]
    del raw["storage"]["local_data_dir"]
    raw["tools"]["databricks_mcp"]["enabled"] = True
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "LLM_ENDPOINT_NAME=dotenv-endpoint",
                f"AGENT_SYSTEM_PROMPT_PATH={env_prompt}",
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
    assert settings.prompts.agent_system_prompt_path == str(env_prompt)
    assert settings.prompts.agent_system_prompt == "env agent prompt"
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


def test_load_settings_reads_explicit_agent_prompt_file_from_dotenv(tmp_path: Path) -> None:
    config_path = write_workspace_config(tmp_path)
    env_prompt = tmp_path / "env-agent.txt"
    env_prompt.write_text("env prompt", encoding="utf-8")
    (tmp_path / ".env").write_text(
        f"AGENT_SYSTEM_PROMPT_PATH={env_prompt}\n",
        encoding="utf-8",
    )

    settings = load_settings(str(config_path))

    assert settings.prompts.agent_system_prompt_path == str(env_prompt)
    assert settings.prompts.agent_system_prompt == "env prompt"


def test_load_settings_uses_dotenv_prompt_when_yaml_path_is_null(tmp_path: Path) -> None:
    env_prompt = tmp_path / "env-agent.txt"
    env_prompt.write_text("env prompt", encoding="utf-8")
    config_path = write_workspace_config(
        tmp_path,
        extra_lines=["agent_system_prompt_path: null"],
    )
    (tmp_path / ".env").write_text(
        f"AGENT_SYSTEM_PROMPT_PATH={env_prompt}\n",
        encoding="utf-8",
    )

    settings = load_settings(str(config_path))

    assert settings.prompts.agent_system_prompt_path == str(env_prompt)
    assert settings.prompts.agent_system_prompt == "env prompt"


def test_load_settings_rejects_empty_explicit_agent_prompt_path_from_dotenv(
    tmp_path: Path,
) -> None:
    config_path = write_workspace_config(tmp_path)
    (tmp_path / ".env").write_text("AGENT_SYSTEM_PROMPT_PATH=\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=r"Configured agent system prompt path must not be empty\.",
    ):
        load_settings(str(config_path))


def test_load_settings_rejects_missing_explicit_agent_prompt_file_from_dotenv(
    tmp_path: Path,
) -> None:
    config_path = write_workspace_config(tmp_path)
    missing_prompt = tmp_path / "missing-env-agent.txt"
    (tmp_path / ".env").write_text(
        f"AGENT_SYSTEM_PROMPT_PATH={missing_prompt}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        FileNotFoundError,
        match=rf"Configured agent system prompt path does not exist: {missing_prompt}",
    ):
        load_settings(str(config_path))


def test_load_settings_rejects_empty_explicit_agent_prompt_file_from_dotenv(
    tmp_path: Path,
) -> None:
    config_path = write_workspace_config(tmp_path)
    empty_prompt = tmp_path / "empty-env-agent.txt"
    empty_prompt.write_text("\n", encoding="utf-8")
    (tmp_path / ".env").write_text(
        f"AGENT_SYSTEM_PROMPT_PATH={empty_prompt}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=rf"Configured agent system prompt file is empty: {empty_prompt}",
    ):
        load_settings(str(config_path))


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
    agent_prompt = tmp_path / "agent.txt"
    agent_prompt.write_text("agent prompt", encoding="utf-8")
    config_path = write_workspace_config(
        tmp_path,
        extra_lines=[
            f"agent_system_prompt_path: {agent_prompt}",
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
