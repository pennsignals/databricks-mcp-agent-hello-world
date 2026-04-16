from __future__ import annotations

import pytest

from databricks_mcp_agent_hello_world.job_entrypoints import run_agent_task


def test_run_agent_task_translates_databricks_kwargs_to_cli_argv(monkeypatch) -> None:
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

    run_agent_task(
        task_input_json='{"task_name":"workspace_onboarding_brief"}',
        config_path="/Workspace/Repos/user/project/workspace-config.yml",
        output="json",
    )

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


def test_run_agent_task_uses_documented_defaults(monkeypatch) -> None:
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

    run_agent_task(task_input_json="{}")

    assert recorded["argv"] == [
        "--config-path",
        "workspace-config.yml",
        "--task-input-json",
        "{}",
        "--output",
        "text",
    ]


def test_run_agent_task_raises_system_exit_when_command_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.job_entrypoints.run_named_command",
        lambda command_name, argv=None, *, prog=None: 2,
    )

    with pytest.raises(SystemExit) as excinfo:
        run_agent_task(task_input_json="{}")

    assert excinfo.value.code == 2
