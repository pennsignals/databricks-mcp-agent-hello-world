from __future__ import annotations

from pathlib import Path

import pytest

from databricks_mcp_agent_hello_world.config import collect_config_warnings, load_yaml_config


def test_load_yaml_config_rejects_missing_config_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        load_yaml_config(str(tmp_path / "missing.yml"))


def test_collect_config_warnings_ignores_malformed_storage_section() -> None:
    assert collect_config_warnings({"storage": "not-a-mapping"}) == []
