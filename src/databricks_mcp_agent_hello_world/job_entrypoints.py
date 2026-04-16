from __future__ import annotations

from .cli import run_named_command


def run_agent_task(
    *,
    task_input_json: str,
    config_path: str = "workspace-config.yml",
    output: str = "text",
) -> None:
    argv = [
        "--config-path",
        config_path,
        "--task-input-json",
        task_input_json,
        "--output",
        output,
    ]
    exit_code = run_named_command("run-agent-task", argv, prog="run-agent-task")
    if exit_code:
        raise SystemExit(exit_code)
