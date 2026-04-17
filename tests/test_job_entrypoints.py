from __future__ import annotations

from types import SimpleNamespace

import pytest

import databricks_mcp_agent_hello_world as package_root
from databricks_mcp_agent_hello_world.job_entrypoints import (
    run_agent_task,
    run_init_storage,
)
from databricks_mcp_agent_hello_world.storage.bootstrap import InitStorageReport


def test_run_agent_task_forwards_sys_argv_to_cli_command(monkeypatch) -> None:
    recorded: dict[str, object] = {}

    def _run_named_command(command_name, argv=None, *, prog=None):
        recorded["command_name"] = command_name
        recorded["argv"] = argv
        recorded["prog"] = prog
        return 0

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.job_entrypoints.run_named_command",
        _run_named_command,
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.job_entrypoints.sys.argv",
        [
            "databricks_mcp_agent_hello_world.run_agent_task",
            "--config-path",
            "/Workspace/Repos/user/project/workspace-config.yml",
            "--task-input-json",
            '{"task_name":"workspace_onboarding_brief"}',
            "--output",
            "json",
        ],
    )

    run_agent_task()

    assert recorded == {
        "command_name": "run-agent-task",
        "argv": [
            "--config-path",
            "/Workspace/Repos/user/project/workspace-config.yml",
            "--task-input-json",
            '{"task_name":"workspace_onboarding_brief"}',
            "--output",
            "json",
        ],
        "prog": "run-agent-task",
    }


def test_run_agent_task_passes_empty_argv_when_no_cli_args_are_present(monkeypatch) -> None:
    recorded: dict[str, object] = {}

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.job_entrypoints.run_named_command",
        lambda command_name, argv=None, *, prog=None: (
            recorded.update(
                {
                    "command_name": command_name,
                    "argv": argv,
                    "prog": prog,
                }
            )
            or 0
        ),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.job_entrypoints.sys.argv",
        ["databricks_mcp_agent_hello_world.run_agent_task"],
    )

    run_agent_task()

    assert recorded == {
        "command_name": "run-agent-task",
        "argv": [],
        "prog": "run-agent-task",
    }


def test_run_agent_task_raises_system_exit_when_command_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.job_entrypoints.run_named_command",
        lambda command_name, argv=None, *, prog=None: 2,
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.job_entrypoints.sys.argv",
        ["databricks_mcp_agent_hello_world.run_agent_task", "--task-input-json", "{}"],
    )

    with pytest.raises(SystemExit) as excinfo:
        run_agent_task()

    assert excinfo.value.code == 2


def test_package_root_run_agent_task_is_lazy_and_invokes_job_entrypoint(monkeypatch) -> None:
    called: list[str] = []

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.job_entrypoints.run_agent_task",
        lambda: called.append("run_agent_task"),
    )

    package_root.run_agent_task()

    assert called == ["run_agent_task"]


def test_run_init_storage_loads_settings_and_calls_bootstrap(monkeypatch, capsys) -> None:
    settings = SimpleNamespace(storage=SimpleNamespace())
    recorded: dict[str, object] = {}

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.job_entrypoints.load_settings",
        lambda config_path: recorded.update({"config_path": config_path}) or settings,
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.job_entrypoints.init_storage",
        lambda loaded_settings: (
            recorded.update({"settings": loaded_settings})
            or InitStorageReport(
                exit_code=0,
                messages=["Schema main.agent created", "Table main.agent.agent_events created"],
            )
        ),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.job_entrypoints.sys.argv",
        [
            "databricks_mcp_agent_hello_world.run_init_storage",
            "--config-path",
            "/Workspace/Repos/user/project/workspace-config.yml",
        ],
    )

    run_init_storage()
    output = capsys.readouterr().out

    assert recorded == {
        "config_path": "/Workspace/Repos/user/project/workspace-config.yml",
        "settings": settings,
    }
    assert "Schema main.agent created" in output
    assert "Table main.agent.agent_events created" in output


def test_run_init_storage_defaults_to_workspace_config(monkeypatch) -> None:
    recorded: dict[str, object] = {}

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.job_entrypoints.load_settings",
        lambda config_path: recorded.update({"config_path": config_path}) or SimpleNamespace(),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.job_entrypoints.init_storage",
        lambda loaded_settings: InitStorageReport(exit_code=0, messages=[]),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.job_entrypoints.sys.argv",
        ["databricks_mcp_agent_hello_world.run_init_storage"],
    )

    run_init_storage()

    assert recorded == {"config_path": "workspace-config.yml"}


def test_run_init_storage_raises_system_exit_when_bootstrap_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.job_entrypoints.load_settings",
        lambda config_path: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.job_entrypoints.init_storage",
        lambda loaded_settings: InitStorageReport(exit_code=1, messages=["boom"]),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.job_entrypoints.sys.argv",
        ["databricks_mcp_agent_hello_world.run_init_storage"],
    )

    with pytest.raises(SystemExit) as excinfo:
        run_init_storage()

    assert excinfo.value.code == 1


def test_package_root_run_init_storage_is_lazy_and_invokes_job_entrypoint(
    monkeypatch,
) -> None:
    called: list[str] = []

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.job_entrypoints.run_init_storage",
        lambda: called.append("run_init_storage"),
    )

    package_root.run_init_storage()

    assert called == ["run_init_storage"]
