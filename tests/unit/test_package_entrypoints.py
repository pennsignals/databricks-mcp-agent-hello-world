from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

import databricks_mcp_agent_hello_world as package_root
from databricks_mcp_agent_hello_world.commands import CommandResult
from databricks_mcp_agent_hello_world.models import AgentRunRecord
from databricks_mcp_agent_hello_world.storage.bootstrap import InitStorageReport


def test_run_agent_task_calls_command_layer_directly_and_renders_text(capsys) -> None:
    result = CommandResult(
        exit_code=0,
        payload=AgentRunRecord(
            run_id="run-123",
            task_name="workspace_onboarding_brief",
            status="success",
            result={"final_response": "All set", "available_tools": [], "tool_calls": []},
        ),
    )

    with patch(
        "databricks_mcp_agent_hello_world.commands.run_agent_task_command",
        return_value=result,
    ) as run_agent_task_command, patch.object(
        sys,
        "argv",
        [
            "databricks_mcp_agent_hello_world.run_agent_task",
            "--config-path",
            "/Workspace/Repos/user/project/workspace-config.yml",
            "--task-input-json",
            '{"task_name":"workspace_onboarding_brief"}',
        ],
    ):
        package_root.run_agent_task()

    run_agent_task_command.assert_called_once_with(
        "/Workspace/Repos/user/project/workspace-config.yml",
        task_input_json='{"task_name":"workspace_onboarding_brief"}',
        task_input_file=None,
    )
    output = capsys.readouterr().out
    assert "Run status: success" in output
    assert "Final answer:" in output


def test_run_agent_task_raises_system_exit_when_command_fails() -> None:
    result = CommandResult(
        exit_code=1,
        payload=AgentRunRecord(
            run_id="run-123",
            task_name="workspace_onboarding_brief",
            status="error",
            result={"final_response": "", "available_tools": [], "tool_calls": []},
        ),
    )

    with patch(
        "databricks_mcp_agent_hello_world.commands.run_agent_task_command",
        return_value=result,
    ), patch.object(
        sys,
        "argv",
        [
            "databricks_mcp_agent_hello_world.run_agent_task",
            "--task-input-json",
            '{"task_name":"workspace_onboarding_brief"}',
        ],
    ):
        with pytest.raises(SystemExit) as excinfo:
            package_root.run_agent_task()

    assert excinfo.value.code == 1


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
