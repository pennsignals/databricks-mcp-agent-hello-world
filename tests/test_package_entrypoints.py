from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

import databricks_mcp_agent_hello_world as package_root
from databricks_mcp_agent_hello_world.commands import CommandResult
from databricks_mcp_agent_hello_world.storage.bootstrap import InitStorageReport


def test_run_agent_task_forwards_sys_argv_to_cli_command() -> None:
    with patch(
        "databricks_mcp_agent_hello_world.cli.run_named_command",
        return_value=0,
    ) as run_named_command, patch.object(
        sys,
        "argv",
        [
            "databricks_mcp_agent_hello_world.run_agent_task",
            "--config-path",
            "/Workspace/Repos/user/project/workspace-config.yml",
            "--task-input-json",
            '{"task_name":"workspace_onboarding_brief"}',
            "--output",
            "json",
        ],
    ):
        package_root.run_agent_task()

    run_named_command.assert_called_once_with(
        "run-agent-task",
        [
            "--config-path",
            "/Workspace/Repos/user/project/workspace-config.yml",
            "--task-input-json",
            '{"task_name":"workspace_onboarding_brief"}',
            "--output",
            "json",
        ],
        prog="run-agent-task",
    )


def test_run_agent_task_raises_system_exit_when_command_fails() -> None:
    with patch(
        "databricks_mcp_agent_hello_world.cli.run_named_command",
        return_value=2,
    ), patch.object(
        sys,
        "argv",
        ["databricks_mcp_agent_hello_world.run_agent_task", "--task-input-json", "{}"],
    ):
        with pytest.raises(SystemExit) as excinfo:
            package_root.run_agent_task()

    assert excinfo.value.code == 2


def test_run_init_storage_parses_config_path_prints_messages_and_exits_on_success(
    capsys,
) -> None:
    result = CommandResult(
        exit_code=0,
        payload=InitStorageReport(
            exit_code=0,
            messages=["Schema main.agent created", "Table main.agent.agent_events created"],
        ),
    )

    with patch(
        "databricks_mcp_agent_hello_world.commands.run_init_storage_command",
        return_value=result,
    ) as run_init_storage_command, patch.object(
        sys,
        "argv",
        [
            "databricks_mcp_agent_hello_world.run_init_storage",
            "--config-path",
            "/Workspace/Repos/user/project/workspace-config.yml",
        ],
    ):
        package_root.run_init_storage()

    output = capsys.readouterr().out
    run_init_storage_command.assert_called_once_with(
        "/Workspace/Repos/user/project/workspace-config.yml"
    )
    assert "Schema main.agent created" in output
    assert "Table main.agent.agent_events created" in output


def test_run_init_storage_defaults_to_workspace_config() -> None:
    result = CommandResult(
        exit_code=0,
        payload=InitStorageReport(exit_code=0, messages=[]),
    )

    with patch(
        "databricks_mcp_agent_hello_world.commands.run_init_storage_command",
        return_value=result,
    ) as run_init_storage_command, patch.object(
        sys,
        "argv",
        ["databricks_mcp_agent_hello_world.run_init_storage"],
    ):
        package_root.run_init_storage()

    run_init_storage_command.assert_called_once_with("workspace-config.yml")


def test_run_init_storage_raises_system_exit_when_command_fails(capsys) -> None:
    result = CommandResult(
        exit_code=1,
        payload=InitStorageReport(exit_code=1, messages=["boom"]),
    )

    with patch(
        "databricks_mcp_agent_hello_world.commands.run_init_storage_command",
        return_value=result,
    ), patch.object(
        sys,
        "argv",
        ["databricks_mcp_agent_hello_world.run_init_storage"],
    ):
        with pytest.raises(SystemExit) as excinfo:
            package_root.run_init_storage()

    assert excinfo.value.code == 1
    assert "boom" in capsys.readouterr().out


def test_importing_package_does_not_run_command_logic() -> None:
    assert callable(package_root.run_agent_task)
    assert callable(package_root.run_init_storage)
