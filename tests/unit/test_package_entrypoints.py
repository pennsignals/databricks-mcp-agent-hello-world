from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import databricks_mcp_agent_hello_world as package_root
from databricks_mcp_agent_hello_world import cli
from databricks_mcp_agent_hello_world.commands import CommandResult


def test_run_agent_task_delegates_and_returns_on_success(monkeypatch) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_agent_task_main",
        lambda: 0,
    )

    assert package_root.run_agent_task() is None


def test_run_agent_task_raises_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_agent_task_main",
        lambda: 7,
    )

    with pytest.raises(SystemExit) as excinfo:
        package_root.run_agent_task()

    assert excinfo.value.code == 7


def test_discover_tools_delegates_and_returns_on_success(monkeypatch) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.discover_tools_main",
        lambda: 0,
    )

    assert package_root.discover_tools() is None


def test_discover_tools_raises_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.discover_tools_main",
        lambda: 5,
    )

    with pytest.raises(SystemExit) as excinfo:
        package_root.discover_tools()

    assert excinfo.value.code == 5


def test_run_init_storage_delegates_and_returns_on_success(monkeypatch) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_init_storage_main",
        lambda: 0,
    )

    assert package_root.run_init_storage() is None


def test_run_init_storage_raises_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_init_storage_main",
        lambda: 3,
    )

    with pytest.raises(SystemExit) as excinfo:
        package_root.run_init_storage()

    assert excinfo.value.code == 3


def test_importing_package_does_not_run_command_logic() -> None:
    assert callable(package_root.discover_tools)
    assert callable(package_root.run_agent_task)
    assert callable(package_root.run_init_storage)


def test_run_agent_task_wrapper_uses_real_main_and_reaches_command_layer(
    monkeypatch,
    capsys,
) -> None:
    calls: list[dict[str, object]] = []
    payload = SimpleNamespace(
        status="success",
        run_id="run-123",
        task_name="customer_account_brief",
        tools_called=[],
        result={"final_response": "All set"},
    )

    def _run_agent_task_command(config_path, *, task_input_json, task_input_file):
        calls.append(
            {
                "config_path": config_path,
                "task_input_json": task_input_json,
                "task_input_file": task_input_file,
            }
        )
        return CommandResult(exit_code=0, payload=payload)

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_agent_task_command",
        _run_agent_task_command,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "databricks_mcp_agent_hello_world.run_agent_task",
            "--config-path",
            "custom.yml",
            "--task-input-json",
            '{"task_name":"demo"}',
        ],
    )

    assert package_root.run_agent_task() is None
    assert calls == [
        {
            "config_path": "custom.yml",
            "task_input_json": '{"task_name":"demo"}',
            "task_input_file": None,
        }
    ]
    assert "Run status: success" in capsys.readouterr().out


def test_discover_tools_wrapper_uses_real_main_and_reaches_command_layer(
    monkeypatch,
    capsys,
) -> None:
    calls: list[str] = []
    payload = SimpleNamespace(enabled_tool_sources=[], tool_count=0, tools=[])

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_discover_tools_command",
        lambda config_path: (
            calls.append(config_path) or CommandResult(exit_code=0, payload=payload)
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "databricks_mcp_agent_hello_world.discover_tools",
            "--config-path",
            "custom.yml",
        ],
    )

    assert package_root.discover_tools() is None
    assert calls == ["custom.yml"]
    assert "Total tools: 0" in capsys.readouterr().out


def test_run_init_storage_wrapper_uses_real_main_and_renders_messages(
    monkeypatch,
    capsys,
) -> None:
    calls: list[str] = []
    payload = SimpleNamespace(messages=["created"])

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_init_storage_command",
        lambda config_path: (
            calls.append(config_path) or CommandResult(exit_code=0, payload=payload)
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "databricks_mcp_agent_hello_world.run_init_storage",
            "--config-path",
            "custom.yml",
        ],
    )

    assert package_root.run_init_storage() is None
    assert calls == ["custom.yml"]
    assert "created" in capsys.readouterr().out


def test_cli_entrypoints_are_importable() -> None:
    for entrypoint in [
        cli.main,
        cli.discover_tools_entrypoint,
        cli.run_agent_task_entrypoint,
        cli.run_evals_entrypoint,
        package_root.discover_tools,
        package_root.run_agent_task,
        package_root.run_init_storage,
    ]:
        assert callable(entrypoint)
