from __future__ import annotations

import inspect

import pytest

from databricks_mcp_agent_hello_world import run_agent_task as package_run_agent_task
from databricks_mcp_agent_hello_world.job_entrypoints import run_agent_task


def test_run_agent_task_uses_zero_argument_wrapper_signature() -> None:
    assert inspect.signature(run_agent_task).parameters == {}


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


def test_package_root_exports_run_agent_task() -> None:
    assert package_run_agent_task is run_agent_task
