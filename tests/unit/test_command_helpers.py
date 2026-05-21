from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world.commands import (
    _agent_run_exit_code,
    _build_agent_task_request,
    _load_settings_for_command,
    _load_task_payload,
    run_discover_tools_command,
    run_evals_command,
    run_init_storage_command,
    run_preflight_command,
)
from databricks_mcp_agent_hello_world.evals.harness import EvalSetupError


def test_command_helpers_delegate_to_runtime_operations(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "workspace-config.yml"
    task_file = tmp_path / "task.json"
    task_file.write_text('{"task_name":"demo","instructions":"hi","payload":{}}', encoding="utf-8")

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.run_preflight",
        lambda path: SimpleNamespace(overall_status="fail"),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands._load_settings_for_command",
        lambda config_path, command_name, next_step=None: "settings",
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.discover_tools",
        lambda settings: {"settings": settings},
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.load_settings",
        lambda path: "settings",
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.init_storage",
        lambda settings: SimpleNamespace(exit_code=0, messages=["done"]),
    )

    assert run_preflight_command(str(config_path)).exit_code == 1
    assert run_discover_tools_command(str(config_path)).payload == {"settings": "settings"}
    assert run_init_storage_command(str(config_path)).payload.messages == ["done"]
    assert (
        _load_task_payload(
            task_input_json=None,
            task_input_file=str(task_file),
        )["task_name"]
        == "demo"
    )
    assert (
        _build_agent_task_request(
            {
                "task_name": "demo",
                "instructions": "hi",
                "payload": {},
                "run_id": "run-123",
            },
            command_name="run-agent-task",
        ).run_id
        == "run-123"
    )


def test_load_settings_for_command_explains_missing_config_next_step(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "workspace-config.yml"
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.load_settings",
        lambda path: (_ for _ in ()).throw(FileNotFoundError(path)),
    )

    with pytest.raises(
        RuntimeError,
        match=r"Create workspace-config\.yml and rerun run_agent_task_job",
    ):
        _load_settings_for_command(
            str(config_path),
            "run-agent-task",
            next_step="run_agent_task_job",
        )
    with pytest.raises(RuntimeError, match="Missing config file"):
        _load_settings_for_command(str(config_path), "discover-tools")


def test_run_evals_command_wraps_config_and_runtime_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "workspace-config.yml"
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.load_settings",
        lambda path: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with pytest.raises(EvalSetupError, match="Unable to load config"):
        run_evals_command(str(config_path))

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.load_settings",
        lambda path: "settings",
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.run_evals",
        lambda settings, scenario_file: (_ for _ in ()).throw(RuntimeError("eval boom")),
    )
    with pytest.raises(EvalSetupError, match="eval boom"):
        run_evals_command(str(config_path))

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.run_evals",
        lambda settings, scenario_file: (_ for _ in ()).throw(EvalSetupError("already wrapped")),
    )
    with pytest.raises(EvalSetupError, match="already wrapped"):
        run_evals_command(str(config_path))


@pytest.mark.parametrize(
    ("status", "expected_exit_code"),
    [
        pytest.param("success", 0, id="success"),
        pytest.param("error", 1, id="error"),
        pytest.param("max_steps_exceeded", 1, id="max-steps-exceeded"),
    ],
)
def test_agent_run_exit_code_maps_known_statuses(status: str, expected_exit_code: int) -> None:
    assert _agent_run_exit_code(SimpleNamespace(status=status)) == expected_exit_code


def test_agent_run_exit_code_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="Unsupported agent run status"):
        _agent_run_exit_code(SimpleNamespace(status="blocked"))
