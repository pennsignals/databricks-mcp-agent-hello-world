from __future__ import annotations

import json
from pathlib import Path

import pytest

from databricks_mcp_agent_hello_world import config
from tests.helpers import make_settings
from tests.conftest import write_workspace_config


def test_settings_provider_type_property_reflects_tool_provider_type() -> None:
    assert make_settings(tool_provider_type="managed_mcp").provider_type == "managed_mcp"


def test_resolve_config_path_defaults_to_workspace_config() -> None:
    assert config.resolve_config_path() == "workspace-config.yml"


def test_load_yaml_config_requires_mapping(tmp_path: Path) -> None:
    config_path = tmp_path / "workspace-config.yml"
    config_path.write_text("- item\n", encoding="utf-8")

    with pytest.raises(ValueError, match="YAML mapping"):
        config.load_yaml_config(str(config_path))


def test_load_dotenv_values_returns_empty_when_no_env_file(tmp_path: Path) -> None:
    config_path = write_workspace_config(tmp_path)

    assert config.load_dotenv_values(str(config_path)) == (None, {})


def test_validate_settings_rejects_remaining_invalid_shapes(monkeypatch) -> None:
    monkeypatch.setattr("databricks_mcp_agent_hello_world.config.get_spark_session", lambda: None)

    with pytest.raises(ValueError, match="storage.local_data_dir"):
        config.validate_settings(make_settings(storage={"local_data_dir": "   "}))

    with pytest.raises(ValueError, match="Unsupported tool_provider_type"):
        config.validate_settings(make_settings(tool_provider_type="unknown"))

    with pytest.raises(ValueError, match="at least 1"):
        config.validate_settings(make_settings(max_agent_steps=0))


def test_validate_settings_requires_remote_table_when_spark_is_available(monkeypatch) -> None:
    monkeypatch.setattr("databricks_mcp_agent_hello_world.config.get_spark_session", lambda: object())

    with pytest.raises(ValueError, match="storage.agent_events_table"):
        config.validate_settings(make_settings(storage={"agent_events_table": "  "}))


def test_load_settings_bundle_can_skip_validation(tmp_path: Path) -> None:
    config_path = write_workspace_config(tmp_path, llm_endpoint_name="''")

    loaded = config.load_settings_bundle(str(config_path), validate=False)

    assert loaded.settings.llm_endpoint_name == ""


def test_parse_task_input_variants(tmp_path: Path) -> None:
    assert config.parse_task_input(None) == {}

    with pytest.raises(ValueError, match="decode to an object"):
        config.parse_task_input("[]")

    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps({"task_name": "demo"}), encoding="utf-8")
    assert config.parse_task_input_file(None) == {}
    assert config.parse_task_input_file(str(task_file)) == {"task_name": "demo"}


def test_internal_config_helpers_cover_fallback_paths(tmp_path: Path) -> None:
    assert config._deep_get({"outer": "not-a-dict"}, "outer", "inner", default="fallback") == "fallback"
    assert config._resolve_value(yaml_value="yaml", dotenv_values={"KEY": "env"}, dotenv_key="KEY") == "yaml"
    assert config._resolve_value(yaml_value=None, dotenv_values={"KEY": "env"}, dotenv_key="KEY") == "env"
    assert config._resolve_value(yaml_value=None, dotenv_values={}, dotenv_key="KEY", default="default") == "default"
    assert config._read_prompt(str(tmp_path / "missing.txt"), "fallback prompt") == "fallback prompt"


def test_parse_dotenv_rejects_invalid_lines_and_coerce_int_rejects_non_int(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("# comment\n\nBROKEN_LINE\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid .env line 3"):
        config._parse_dotenv(dotenv_path)

    with pytest.raises(ValueError, match="max_agent_steps must be an integer"):
        config._coerce_int("nope", name="max_agent_steps")
