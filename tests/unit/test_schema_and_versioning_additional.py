from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pytest
from pydantic import BaseModel, ValidationError

import databricks_mcp_agent_hello_world as package_root
from databricks_mcp_agent_hello_world.config import collect_config_warnings, load_yaml_config
from databricks_mcp_agent_hello_world.devtools.wheel_build import discover_built_wheel
from databricks_mcp_agent_hello_world.models import ToolSpec
from databricks_mcp_agent_hello_world.storage import schema
from databricks_mcp_agent_hello_world.versioning import (
    bundle_wheel_glob,
    read_project_name,
)


def test_package_root_run_init_storage_success(capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.run_init_storage_command",
        lambda config_path: SimpleNamespace(
            exit_code=0,
            payload=SimpleNamespace(messages=["created"]),
        ),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["run_init_storage", "--config-path", "workspace-config.yml"],
    )

    package_root.run_init_storage()
    assert "created" in capsys.readouterr().out


def test_package_root_run_agent_task_json_output(capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.run_agent_task_command",
        lambda config_path, *, task_input_json, task_input_file: SimpleNamespace(
            exit_code=0,
            payload=SimpleNamespace(model_dump_json=lambda indent=2: '{"ok": true}'),
        ),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["run-agent-task", "--output", "json", "--task-input-json", '{"task_name":"demo"}'],
    )

    package_root.run_agent_task()
    assert '{"ok": true}' in capsys.readouterr().out


def test_models_and_schema_additional_validation_paths() -> None:
    with pytest.raises(ValidationError, match="tool_name must not be empty"):
        ToolSpec(
            tool_name="   ",
            description="desc",
            input_schema={"type": "object", "properties": {}},
            provider_type="local_python",
            provider_id="builtin_tools",
        )
    with pytest.raises(ValidationError, match="type=object"):
        ToolSpec(
            tool_name="tool",
            description="desc",
            input_schema={"type": "array"},
            provider_type="local_python",
            provider_id="builtin_tools",
        )

    with pytest.raises(ValueError, match="Unsupported Arrow type"):
        schema.arrow_field_to_spark_sql_type(pa.field("bad", pa.bool_(), nullable=False))

    class ModelDumpPayload(BaseModel):
        value: str = "model"

    class AsDictPayload:
        def as_dict(self) -> object:
            return {"value": "as_dict"}

    class DictPayload:
        def dict(self) -> object:
            return {"value": "dict"}

    assert schema.safe_jsonable(ModelDumpPayload()) == {"value": "model"}
    assert schema.safe_jsonable(AsDictPayload()) == {"value": "as_dict"}
    assert schema.safe_jsonable(DictPayload()) == {"value": "dict"}
    assert schema.safe_jsonable({1: {"nested": {1, 2}}})["1"]["nested"] in ([1, 2], [2, 1])
    assert (
        schema.validate_event_rows(
            [
                schema.serialize_event_row(
                    run_key="run-1",
                    task_name="task",
                    event_index=0,
                    event_type="started",
                    payload={"ok": True},
                )
            ]
        ).num_rows
        == 1
    )


def test_versioning_and_wheel_discovery_unhappy_paths(tmp_path: Path) -> None:
    assert (
        bundle_wheel_glob(read_project_name()) == "../dist/databricks_mcp_agent_hello_world-*.whl"
    )

    with pytest.raises(RuntimeError, match="Did not find a built wheel"):
        discover_built_wheel(
            tmp_path,
            project_name="databricks-mcp-agent-hello-world",
        )

    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "databricks_mcp_agent_hello_world-0.1.0-py3-none-any.whl").write_text(
        "wheel-a",
        encoding="utf-8",
    )
    (dist_dir / "databricks_mcp_agent_hello_world-0.1.1-py3-none-any.whl").write_text(
        "wheel-b",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Expected exactly one built wheel"):
        discover_built_wheel(
            tmp_path,
            project_name="databricks-mcp-agent-hello-world",
        )


def test_config_file_and_warning_edge_cases(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        load_yaml_config(str(tmp_path / "missing.yml"))

    assert collect_config_warnings({"storage": "not-a-mapping"}) == []
