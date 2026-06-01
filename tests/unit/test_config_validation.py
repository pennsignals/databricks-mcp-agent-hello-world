from __future__ import annotations

import json
from pathlib import Path

import pytest

from databricks_tool_agent_template import config
from databricks_tool_agent_template.storage import spark
from tests.conftest import write_workspace_config
from tests.helpers import make_settings


def test_resolve_config_path_defaults_to_workspace_config() -> None:
    assert config.resolve_config_path() == "workspace-config.yml"


def test_load_yaml_config_requires_mapping(tmp_path: Path) -> None:
    config_path = tmp_path / "workspace-config.yml"
    config_path.write_text("- item\n", encoding="utf-8")

    with pytest.raises(ValueError, match="YAML mapping"):
        config.load_yaml_config(str(config_path))


def test_load_settings_rejects_unknown_top_level_key(tmp_path: Path) -> None:
    config_path = write_workspace_config(tmp_path, extra_lines=["unexpected: value"])

    with pytest.raises(ValueError, match="Unknown config key"):
        config.load_settings(str(config_path))


def test_load_settings_rejects_unknown_nested_key(tmp_path: Path) -> None:
    config_path = write_workspace_config(tmp_path, extra_lines=["  unexpected: value"])

    with pytest.raises(ValueError, match=r"storage\.unexpected"):
        config.load_settings(str(config_path))


def test_load_dotenv_values_returns_empty_when_no_env_file(tmp_path: Path) -> None:
    config_path = write_workspace_config(tmp_path)

    assert config.load_dotenv_values(str(config_path)) == (None, {})


@pytest.mark.parametrize(
    ("settings_overrides", "message"),
    [
        pytest.param(
            {"storage": {"local_data_dir": "   "}},
            r"storage\.local_data_dir",
            id="blank-local-data-dir",
        ),
        pytest.param(
            {"tools": {"local_python": {"enabled": False}}},
            "At least one tool source",
            id="zero-enabled-tool-sources",
        ),
        pytest.param(
            {"tools": {"local_python": {"enabled": False}, "databricks_mcp": {"enabled": True}}},
            r"tools\.databricks_mcp\.server",
            id="missing-mcp-server-url",
        ),
        pytest.param(
            {"max_agent_steps": 0},
            "at least 1",
            id="zero-max-agent-steps",
        ),
    ],
)
def test_validate_settings_rejects_invalid_shapes(
    settings_overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        config.validate_settings(make_settings(**settings_overrides))


def test_validate_settings_does_not_probe_spark(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Spark should not be inspected during config validation.")

    monkeypatch.setattr(spark, "get_spark_session", fail_if_called)
    monkeypatch.setattr(spark, "require_spark_session", fail_if_called)

    config.validate_settings(make_settings(storage={"agent_events_table": "main.demo.events"}))


def test_load_settings_can_skip_validation(tmp_path: Path) -> None:
    config_path = write_workspace_config(tmp_path, llm_endpoint_name="''")

    settings = config.load_settings(str(config_path), validate=False)

    assert settings.llm_endpoint_name == ""


def test_parse_task_input_variants(tmp_path: Path) -> None:
    assert config.parse_task_input(None) == {}

    with pytest.raises(ValueError, match="decode to an object"):
        config.parse_task_input("[]")

    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps({"task_name": "demo"}), encoding="utf-8")
    assert config.parse_task_input_file(None) == {}
    assert config.parse_task_input_file(str(task_file)) == {"task_name": "demo"}


def test_load_dotenv_values_rejects_invalid_lines(tmp_path: Path) -> None:
    config_path = write_workspace_config(tmp_path)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("# comment\n\nBROKEN_LINE\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"Invalid \.env line 3"):
        config.load_dotenv_values(str(config_path))


def test_load_dotenv_values_rejects_unknown_keys(tmp_path: Path) -> None:
    config_path = write_workspace_config(tmp_path)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("UNSUPPORTED=value\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"Local \.env contains unsupported keys"):
        config.load_dotenv_values(str(config_path))


def test_load_settings_rejects_non_integer_max_steps(tmp_path: Path) -> None:
    config_path = write_workspace_config(tmp_path, extra_lines=["max_agent_steps: nope"])
    with pytest.raises(ValueError, match="max_agent_steps must be an integer"):
        config.load_settings(str(config_path))
