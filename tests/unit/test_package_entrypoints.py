from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import databricks_mcp_agent_hello_world as package_root
from databricks_mcp_agent_hello_world.commands import CommandResult
from databricks_mcp_agent_hello_world.models import AgentRunRecord
from databricks_mcp_agent_hello_world.storage.bootstrap import InitStorageReport


def test_run_agent_task_calls_command_layer_directly_and_renders_text(capsys, monkeypatch) -> None:
    result = CommandResult(
        exit_code=0,
        payload=AgentRunRecord(
            run_id="run-123",
            task_name="workspace_onboarding_brief",
            status="success",
            result={"final_response": "All set", "available_tools": [], "tool_calls": []},
        ),
    )
    calls = []

    def _run_agent_task_command(config_path, *, task_input_json, task_input_file):
        calls.append(
            {
                "config_path": config_path,
                "task_input_json": task_input_json,
                "task_input_file": task_input_file,
            }
        )
        return result

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.run_agent_task_command",
        _run_agent_task_command,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "databricks_mcp_agent_hello_world.run_agent_task",
            "--config-path",
            "/Workspace/Repos/user/project/workspace-config.yml",
            "--task-input-json",
            '{"task_name":"workspace_onboarding_brief"}',
        ],
    )

    package_root.run_agent_task()

    assert calls == [
        {
            "config_path": "/Workspace/Repos/user/project/workspace-config.yml",
            "task_input_json": '{"task_name":"workspace_onboarding_brief"}',
            "task_input_file": None,
        }
    ]
    output = capsys.readouterr().out
    assert "Run status: success" in output
    assert "Final answer:" in output


def test_run_agent_task_raises_system_exit_when_command_fails(monkeypatch) -> None:
    result = CommandResult(
        exit_code=1,
        payload=AgentRunRecord(
            run_id="run-123",
            task_name="workspace_onboarding_brief",
            status="error",
            result={"final_response": "", "available_tools": [], "tool_calls": []},
        ),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.run_agent_task_command",
        lambda config_path, *, task_input_json, task_input_file: result,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "databricks_mcp_agent_hello_world.run_agent_task",
            "--task-input-json",
            '{"task_name":"workspace_onboarding_brief"}',
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        package_root.run_agent_task()

    assert excinfo.value.code == 1


def test_run_init_storage_raises_system_exit_when_command_fails(capsys, monkeypatch) -> None:
    result = CommandResult(
        exit_code=1,
        payload=InitStorageReport(exit_code=1, messages=["boom"]),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.run_init_storage_command",
        lambda config_path: result,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["databricks_mcp_agent_hello_world.run_init_storage"],
    )

    with pytest.raises(SystemExit) as excinfo:
        package_root.run_init_storage()

    assert excinfo.value.code == 1
    assert "boom" in capsys.readouterr().out


def test_importing_package_does_not_run_command_logic() -> None:
    assert callable(package_root.run_agent_task)
    assert callable(package_root.run_init_storage)


def test_run_init_storage_renders_success_messages(capsys, monkeypatch) -> None:
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


def test_run_agent_task_renders_json_output(capsys, monkeypatch) -> None:
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
