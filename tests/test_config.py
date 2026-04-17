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


def _write_config(tmp_path: Path, extra_lines: list[str] | None = None) -> Path:
    config_path = tmp_path / "workspace-config.yml"
    lines = [
        "llm_endpoint_name: endpoint-a",
        "tool_provider_type: local_python",
        "databricks_config_profile: DEFAULT",
        "storage:",
        "  agent_events_table: main.agent.agent_events",
        "  local_data_dir: ./.local_state",
    ]
    if extra_lines:
        lines.extend(extra_lines)
    config_path.write_text("\n".join(lines), encoding="utf-8")
    return config_path


def test_load_settings_reads_agent_prompt_file(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
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


def test_load_settings_requires_llm_endpoint_name(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "llm_endpoint_name: endpoint-a",
            "llm_endpoint_name: ''",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="llm_endpoint_name"):
        load_settings(str(config_path))


def test_load_settings_prefers_yaml_over_dotenv(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "LLM_ENDPOINT_NAME=dotenv-endpoint",
                "DATABRICKS_CONFIG_PROFILE=DOTENV",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(str(config_path))

    assert settings.llm_endpoint_name == "endpoint-a"
    assert settings.databricks_config_profile == "DEFAULT"


def test_selected_config_path_controls_loaded_yaml(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first_path = _write_config(first_dir)
    second_path = _write_config(second_dir)
    first_path.write_text(
        first_path.read_text(encoding="utf-8").replace("endpoint-a", "endpoint-one"),
        encoding="utf-8",
    )
    second_path.write_text(
        second_path.read_text(encoding="utf-8").replace("endpoint-a", "endpoint-two"),
        encoding="utf-8",
    )
    (first_dir / ".env").write_text("LOG_LEVEL=DEBUG\n", encoding="utf-8")
    (second_dir / ".env").write_text("LOG_LEVEL=WARNING\n", encoding="utf-8")

    first_settings = load_settings(str(first_path))
    second_settings = load_settings(str(second_path))

    assert first_settings.llm_endpoint_name == "endpoint-one"
    assert second_settings.llm_endpoint_name == "endpoint-two"
    assert first_settings.log_level == "DEBUG"
    assert second_settings.log_level == "WARNING"


def test_load_dotenv_rejects_direct_databricks_credentials(tmp_path: Path) -> None:
    _write_config(tmp_path)
    (tmp_path / ".env").write_text("DATABRICKS_TOKEN=dapi-secret\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must not contain direct Databricks credentials"):
        load_dotenv_values(str(tmp_path / "workspace-config.yml"))


def test_build_settings_uses_dotenv_when_yaml_omits_optional_values(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    raw = load_yaml_config(str(config_path))
    del raw["databricks_config_profile"]
    (tmp_path / ".env").write_text(
        "DATABRICKS_CONFIG_PROFILE=FROM_DOTENV\nLOG_LEVEL=DEBUG\n",
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


def test_load_settings_accepts_managed_mcp(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "tool_provider_type: local_python",
            "tool_provider_type: managed_mcp",
        ),
        encoding="utf-8",
    )

    settings = load_settings(str(config_path))

    assert settings.tool_provider_type == "managed_mcp"


def test_provider_type_alias_loads_and_warns(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    config_path = _write_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "tool_provider_type: local_python",
            "provider_type: managed_mcp",
        ),
        encoding="utf-8",
    )

    with caplog.at_level("WARNING"):
        settings = load_settings(str(config_path))

    assert settings.tool_provider_type == "managed_mcp"
    assert (
        "Deprecated config key 'provider_type' used; use 'tool_provider_type' instead."
        in caplog.messages
    )


def test_databricks_cli_profile_alias_loads_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config_path = _write_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "databricks_config_profile: DEFAULT",
            "databricks_cli_profile: LEGACY",
        ),
        encoding="utf-8",
    )

    with caplog.at_level("WARNING"):
        settings = load_settings(str(config_path))

    assert settings.databricks_config_profile == "LEGACY"
    assert (
        "Deprecated config key 'databricks_cli_profile' used; use "
        "'databricks_config_profile' instead."
        in caplog.messages
    )


def test_canonical_key_wins_over_alias(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    config_path = _write_config(
        tmp_path,
        extra_lines=["provider_type: managed_mcp"],
    )

    with caplog.at_level("WARNING"):
        settings = load_settings(str(config_path))

    assert settings.tool_provider_type == "local_python"
    assert (
        "Deprecated config key 'provider_type' used; use 'tool_provider_type' instead."
        in caplog.messages
    )


def test_removed_top_level_key_warns_but_loads(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config_path = _write_config(tmp_path, extra_lines=["auth_mode: local-dev"])

    with caplog.at_level("WARNING"):
        settings = load_settings(str(config_path))

    assert settings.tool_provider_type == "local_python"
    assert "Unused config key 'auth_mode' is ignored by the current runtime." in caplog.messages


def test_removed_sql_section_warns_only_on_top_level(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config_path = _write_config(
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

    assert "Unused config key 'sql' is ignored by the current runtime." in caplog.messages
    assert not any("sql." in message for message in caplog.messages)


def test_stale_storage_nested_key_warns_but_loads(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config_path = _write_config(
        tmp_path,
        extra_lines=["  agent_runs_table: main.agent.agent_runs"],
    )

    with caplog.at_level("WARNING"):
        settings = load_settings(str(config_path))

    assert settings.storage.agent_events_table == "main.agent.agent_events"
    assert (
        "Unused config key 'storage.agent_runs_table' is ignored by the current runtime."
        in caplog.messages
    )


def test_removed_dotenv_keys_warn_but_load(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config_path = _write_config(tmp_path)
    (tmp_path / ".env").write_text(
        "AUTH_MODE=legacy\nLOCAL_TOOL_BACKEND_MODE=auto\n",
        encoding="utf-8",
    )

    with caplog.at_level("WARNING"):
        load_settings(str(config_path))

    assert "Unused .env key 'AUTH_MODE' is ignored by the current runtime." in caplog.messages
    assert (
        "Unused .env key 'LOCAL_TOOL_BACKEND_MODE' is ignored by the current runtime."
        in caplog.messages
    )


def test_collect_config_warnings_is_sorted_and_deduplicated() -> None:
    warnings = collect_config_warnings(
        {
            "zzz_unknown": True,
            "provider_type": "local_python",
            "storage": {
                "agent_runs_table": "main.agent.agent_runs",
                "zzz_other": "value",
            },
            "sql": {"warehouse_id": "wh"},
        }
    )

    assert warnings == sorted(warnings)
    assert warnings == [
        "Deprecated config key 'provider_type' used; use 'tool_provider_type' instead.",
        "Unused config key 'sql' is ignored by the current runtime.",
        "Unused config key 'storage.agent_runs_table' is ignored by the current runtime.",
        "Unused config key 'storage.zzz_other' is ignored by the current runtime.",
        "Unused config key 'zzz_unknown' is ignored by the current runtime.",
    ]


def test_collect_dotenv_warnings_is_sorted() -> None:
    warnings = collect_dotenv_warnings(
        {
            "LOCAL_TOOL_BACKEND_MODE": "auto",
            "AUTH_MODE": "legacy",
            "UNRELATED": "keep-quiet",
        }
    )

    assert warnings == [
        "Unused .env key 'AUTH_MODE' is ignored by the current runtime.",
        "Unused .env key 'LOCAL_TOOL_BACKEND_MODE' is ignored by the current runtime.",
    ]


def test_resolve_deprecated_config_aliases_prefers_canonical_values() -> None:
    resolved = resolve_deprecated_config_aliases(
        {
            "tool_provider_type": "local_python",
            "provider_type": "managed_mcp",
            "databricks_config_profile": "CANONICAL",
            "databricks_cli_profile": "LEGACY",
        }
    )

    assert resolved["tool_provider_type"] == "local_python"
    assert resolved["databricks_config_profile"] == "CANONICAL"


def test_load_settings_requires_agent_events_table_when_spark_is_available(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "workspace-config.yml"
    config_path.write_text(
        "\n".join(
            [
                "llm_endpoint_name: endpoint-a",
                "tool_provider_type: local_python",
                "storage:",
                "  local_data_dir: ./.local_state",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.config.get_spark_session",
        lambda: object(),
    )

    with pytest.raises(ValueError, match="storage.agent_events_table"):
        load_settings(str(config_path))


def test_load_settings_defaults_local_data_dir_when_blank(tmp_path: Path) -> None:
    config_path = tmp_path / "workspace-config.yml"
    config_path.write_text(
        "\n".join(
            [
                "llm_endpoint_name: endpoint-a",
                "tool_provider_type: local_python",
                "storage:",
                "  agent_events_table: main.agent.agent_events",
                "  local_data_dir: ''",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(str(config_path))

    assert settings.storage.local_data_dir == "./.local_state"
