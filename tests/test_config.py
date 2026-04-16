from pathlib import Path

import pytest

from databricks_mcp_agent_hello_world.config import (
    build_settings,
    load_dotenv_values,
    load_settings,
    load_yaml_config,
)


def _write_complete_config(
    tmp_path: Path,
    *,
    llm_endpoint_name: str = "endpoint-a",
    include_sql: bool = False,
    sql_values: dict[str, str] | None = None,
) -> Path:
    config_path = tmp_path / "workspace-config.yml"
    sql_values = sql_values or {}
    lines = [
        f"llm_endpoint_name: {llm_endpoint_name}",
        "tool_provider_type: local_python",
        "databricks_config_profile: DEFAULT",
        "storage:",
        "  agent_runs_table: main.agent.agent_runs",
        "  agent_output_table: main.agent.agent_outputs",
    ]
    if include_sql:
        lines.extend(
            [
                "sql:",
                f"  warehouse_id: {sql_values.get('warehouse_id', 'warehouse-placeholder')}",
                f"  catalog: {sql_values.get('catalog', 'catalog-placeholder')}",
                f"  schema: {sql_values.get('schema', 'schema-placeholder')}",
                f"  incident_kb_table: {sql_values.get('incident_kb_table', 'incident_kb_placeholder')}",
                f"  runbook_table: {sql_values.get('runbook_table', 'runbook_placeholder')}",
                f"  customer_summary_table: {sql_values.get('customer_summary_table', 'customer_summary_placeholder')}",
                f"  service_incidents_table: {sql_values.get('service_incidents_table', 'service_incidents_placeholder')}",
                f"  service_dependencies_table: {sql_values.get('service_dependencies_table', 'service_dependencies_placeholder')}",
            ]
        )
    config_path.write_text("\n".join(lines), encoding="utf-8")
    return config_path


def test_load_settings_reads_agent_prompt_file(tmp_path: Path) -> None:
    config_path = _write_complete_config(tmp_path)
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
    config_path = _write_complete_config(tmp_path, llm_endpoint_name="")

    with pytest.raises(ValueError, match="llm_endpoint_name"):
        load_settings(str(config_path))


def test_load_settings_prefers_yaml_over_dotenv(tmp_path: Path) -> None:
    config_path = _write_complete_config(tmp_path, llm_endpoint_name="yaml-endpoint")
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

    assert settings.llm_endpoint_name == "yaml-endpoint"
    assert settings.databricks_cli_profile == "DEFAULT"


def test_selected_config_path_controls_loaded_yaml(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first_path = _write_complete_config(first_dir, llm_endpoint_name="endpoint-one")
    second_path = _write_complete_config(second_dir, llm_endpoint_name="endpoint-two")
    (first_dir / ".env").write_text("LOG_LEVEL=DEBUG\n", encoding="utf-8")
    (second_dir / ".env").write_text("LOG_LEVEL=WARNING\n", encoding="utf-8")

    first_settings = load_settings(str(first_path))
    second_settings = load_settings(str(second_path))

    assert first_settings.llm_endpoint_name == "endpoint-one"
    assert second_settings.llm_endpoint_name == "endpoint-two"
    assert first_settings.log_level == "DEBUG"
    assert second_settings.log_level == "WARNING"


def test_load_dotenv_rejects_direct_databricks_credentials(tmp_path: Path) -> None:
    _write_complete_config(tmp_path)
    (tmp_path / ".env").write_text("DATABRICKS_TOKEN=dapi-secret\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must not contain direct Databricks credentials"):
        load_dotenv_values(str(tmp_path / "workspace-config.yml"))


def test_build_settings_uses_dotenv_when_yaml_omits_optional_values(tmp_path: Path) -> None:
    config_path = _write_complete_config(tmp_path)
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

    assert settings.databricks_cli_profile == "FROM_DOTENV"
    assert settings.log_level == "DEBUG"


def test_load_settings_accepts_missing_sql_section_for_local_python(tmp_path: Path) -> None:
    config_path = _write_complete_config(tmp_path)

    settings = load_settings(str(config_path))

    assert settings.tool_provider_type == "local_python"
    assert settings.sql_config_required is False
    assert settings.sql.warehouse_id is None
    assert settings.sql.catalog is None
    assert settings.sql.schema is None
    assert settings.local_tool_backend_mode == "auto"


def test_load_settings_accepts_placeholder_sql_section_for_local_python(tmp_path: Path) -> None:
    config_path = _write_complete_config(
        tmp_path,
        include_sql=True,
        sql_values={
            "warehouse_id": "warehouse-placeholder",
            "catalog": "catalog-placeholder",
            "schema": "schema-placeholder",
        },
    )

    settings = load_settings(str(config_path))

    assert settings.tool_provider_type == "local_python"
    assert settings.sql_config_required is False
    assert settings.sql.warehouse_id == "warehouse-placeholder"
    assert settings.sql.catalog == "catalog-placeholder"
    assert settings.sql.schema == "schema-placeholder"
