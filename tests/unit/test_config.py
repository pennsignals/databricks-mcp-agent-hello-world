from __future__ import annotations

from pathlib import Path

import pytest

from databricks_mcp_agent_hello_world.config import (
    build_settings,
    collect_config_warnings,
    collect_dotenv_warnings,
    load_dotenv_values,
    load_settings,
    load_yaml_config,
    resolve_deprecated_config_aliases,
)
from tests.conftest import write_workspace_config


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


def test_build_settings_uses_dotenv_for_optional_values_when_yaml_omits_them(
    tmp_path: Path,
) -> None:
    config_path = write_workspace_config(tmp_path)
    raw = load_yaml_config(str(config_path))
    del raw["databricks_config_profile"]
    (tmp_path / ".env").write_text(
        "DATABRICKS_CONFIG_PROFILE=FROM_DOTENV\nLOG_LEVEL=DEBUG\nSTORAGE_REQUIRE_SPARK=true\n",
        encoding="utf-8",
    )
    dotenv_path, dotenv_values = load_dotenv_values(str(config_path))

    settings = build_settings(
        raw,
        config_path=str(config_path),
        dotenv_path=dotenv_path,
        dotenv_values=dotenv_values,
    )

    assert settings.databricks_config_profile == "FROM_DOTENV"
    assert settings.log_level == "DEBUG"
    assert settings.storage.require_spark is True


def test_databricks_host_allowed_in_local_dotenv(tmp_path: Path) -> None:
    config_path = write_workspace_config(tmp_path)
    (tmp_path / ".env").write_text(
        "DATABRICKS_HOST=https://example.cloud.databricks.com\n",
        encoding="utf-8",
    )

    settings = load_settings(str(config_path))

    assert settings.workspace_host == "https://example.cloud.databricks.com"


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
    settings = load_settings(str(write_workspace_config(tmp_path)))

    assert settings.tool_provider_type == "local_python"
    assert settings.storage.agent_events_table == "main.agent.agent_events"
    assert settings.storage.require_spark is False


def test_load_settings_reads_storage_require_spark(tmp_path: Path) -> None:
    config_path = tmp_path / "workspace-config.yml"
    config_path.write_text(
        "\n".join(
            [
                "llm_endpoint_name: endpoint-a",
                "tool_provider_type: local_python",
                "storage:",
                "  require_spark: true",
                "  agent_events_table: main.agent.agent_events",
                "  local_data_dir: ./.local_state",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(str(config_path))

    assert settings.storage.require_spark is True


@pytest.mark.parametrize(
    ("replacement", "expected_value", "warning_substring"),
    [
        (
            "provider_type: databricks_mcp",
            "databricks_mcp",
            "Deprecated config key 'provider_type' used",
        ),
        (
            "databricks_cli_profile: LEGACY",
            "LEGACY",
            "Deprecated config key 'databricks_cli_profile' used",
        ),
    ],
)
def test_deprecated_aliases_load_and_warn(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    replacement: str,
    expected_value: str,
    warning_substring: str,
) -> None:
    config_path = write_workspace_config(tmp_path)
    original = (
        "tool_provider_type: local_python"
        if replacement.startswith("provider_type")
        else "databricks_config_profile: DEFAULT"
    )
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(original, replacement),
        encoding="utf-8",
    )
    if replacement.startswith("provider_type"):
        config_path.write_text(
            config_path.read_text(encoding="utf-8")
            + "\nmcp:\n"
            + "  server:\n"
            + "    url: https://example.cloud.databricks.com/api/2.0/mcp/functions/main/demo\n",
            encoding="utf-8",
        )

    with caplog.at_level("WARNING"):
        settings = load_settings(str(config_path))

    loaded_value = (
        settings.tool_provider_type
        if replacement.startswith("provider_type")
        else settings.databricks_config_profile
    )
    assert loaded_value == expected_value
    assert any(warning_substring in message for message in caplog.messages)


def test_canonical_key_wins_over_deprecated_alias(tmp_path: Path, caplog) -> None:
    config_path = write_workspace_config(tmp_path, extra_lines=["provider_type: databricks_mcp"])

    with caplog.at_level("WARNING"):
        settings = load_settings(str(config_path))

    assert settings.tool_provider_type == "local_python"
    assert any(
        "Deprecated config key 'provider_type' used" in message for message in caplog.messages
    )


@pytest.mark.parametrize(
    ("extra_lines", "warning_path"),
    [
        (["auth_mode: local-dev"], "auth_mode"),
        (
            [
                "storage:",
                "  require_spark: false",
                "  local_data_dir: ./.local_state",
                "  agent_events_table: main.agent.agent_events",
                "  agent_runs_table: main.agent.agent_runs",
            ],
            "storage.agent_runs_table",
        ),
        (["extra_section: true"], "extra_section"),
    ],
)
def test_unused_or_unknown_config_keys_warn_without_changing_runtime_behavior(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    extra_lines: list[str],
    warning_path: str,
) -> None:
    config_path = write_workspace_config(tmp_path)
    if warning_path.startswith("storage."):
        config_path.write_text(
            "\n".join(
                [
                    "llm_endpoint_name: endpoint-a",
                    "tool_provider_type: local_python",
                    "databricks_config_profile: DEFAULT",
                    "storage:",
                    "  agent_events_table: main.agent.agent_events",
                    "  local_data_dir: ./.local_state",
                    "  agent_runs_table: main.agent.agent_runs",
                ]
            ),
            encoding="utf-8",
        )
    else:
        config_path = write_workspace_config(tmp_path, extra_lines=extra_lines)

    with caplog.at_level("WARNING"):
        settings = load_settings(str(config_path))

    assert settings.tool_provider_type == "local_python"
    assert any(warning_path in message for message in caplog.messages)


def test_sql_section_warns_once_at_top_level_only(tmp_path: Path, caplog) -> None:
    config_path = write_workspace_config(
        tmp_path,
        extra_lines=[
            "sql:",
            "  warehouse_id: warehouse-id",
            "  catalog: main",
            "  schema: demo",
        ],
    )

    with caplog.at_level("WARNING"):
        load_settings(str(config_path))

    assert any("Unused config key 'sql'" in message for message in caplog.messages)
    assert not any("sql." in message for message in caplog.messages)


def test_removed_dotenv_keys_warn_but_do_not_fail(tmp_path: Path) -> None:
    warnings = collect_dotenv_warnings(
        {
            "AUTH_MODE": "legacy",
            "LOCAL_TOOL_BACKEND_MODE": "legacy",
        }
    )

    assert len(warnings) == 2
    assert all("Unused .env key" in warning for warning in warnings)


def test_collect_config_warnings_returns_stable_warning_categories() -> None:
    warnings = collect_config_warnings(
        {
            "provider_type": "local_python",
            "unknown_key": True,
            "storage": {
                "agent_events_table": "main.agent.agent_events",
                "agent_output_table": "main.agent.agent_output",
            },
        }
    )

    assert any("provider_type" in warning for warning in warnings)
    assert any("unknown_key" in warning for warning in warnings)
    assert any("storage.agent_output_table" in warning for warning in warnings)


def test_resolve_deprecated_aliases_preserves_canonical_values() -> None:
    resolved = resolve_deprecated_config_aliases(
        {
            "tool_provider_type": "local_python",
            "provider_type": "databricks_mcp",
        }
    )

    assert resolved["tool_provider_type"] == "local_python"


def test_load_settings_rejects_old_managed_mcp_value(tmp_path: Path) -> None:
    config_path = write_workspace_config(tmp_path, tool_provider_type="managed_mcp")

    with pytest.raises(ValueError, match="managed_mcp has been replaced by databricks_mcp"):
        load_settings(str(config_path))


def test_load_settings_accepts_databricks_mcp_config(tmp_path: Path) -> None:
    config_path = write_workspace_config(
        tmp_path,
        tool_provider_type="databricks_mcp",
        extra_lines=[
            "mcp:",
            "  server:",
            "    name: uc_functions",
            "    url: https://example.cloud.databricks.com/api/2.0/mcp/functions/main/demo",
        ],
    )

    settings = load_settings(str(config_path))

    assert settings.tool_provider_type == "databricks_mcp"
    assert settings.mcp.server is not None
    assert settings.mcp.server.name == "uc_functions"


def test_load_settings_rejects_non_mapping_mcp_server(tmp_path: Path) -> None:
    config_path = write_workspace_config(
        tmp_path,
        tool_provider_type="databricks_mcp",
        extra_lines=[
            "mcp:",
            "  server: not-a-mapping",
        ],
    )

    with pytest.raises(ValueError, match="mcp.server must be a YAML mapping"):
        load_settings(str(config_path))
