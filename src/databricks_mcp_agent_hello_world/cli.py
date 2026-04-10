from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_settings, parse_task_input
from .logging_utils import configure_logging
from .models import AgentTaskRequest
from .profiles.compiler import ToolProfileCompiler
from .runner.agent_runner import AgentRunner


def compile_tool_profile_entrypoint(config_path: str | None = None, **_: Any) -> None:
    configure_logging()
    settings = load_settings(config_path)
    compiler = ToolProfileCompiler(settings)
    profile = compiler.compile()
    print(profile.model_dump_json(indent=2))


def run_agent_task_entrypoint(
    config_path: str | None = None,
    task_input_json: str | None = None,
    **_: Any,
) -> None:
    configure_logging()
    settings = load_settings(config_path)
    payload = parse_task_input(task_input_json)

    request_kwargs = {
        "task_name": payload.get("task_name", "demo-task"),
        "instructions": payload.get("instructions", "Complete the requested task."),
        "payload": payload.get("payload", payload),
    }
    if payload.get("run_id"):
        request_kwargs["run_id"] = payload["run_id"]
    if payload.get("idempotency_key"):
        request_kwargs["idempotency_key"] = payload["idempotency_key"]

    request = AgentTaskRequest(**request_kwargs)
    runner = AgentRunner(settings)
    record = runner.run(request)
    print(record.model_dump_json(indent=2))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="databricks-mcp-agent-hello-world")
    parser.add_argument("command", choices=["compile", "run"])
    parser.add_argument("--config-path", default=str(Path("workspace-config.yml")))
    parser.add_argument("--task-input-json", default=None)
    args = parser.parse_args()

    if args.command == "compile":
        compile_tool_profile_entrypoint(config_path=args.config_path)
    else:
        run_agent_task_entrypoint(
            config_path=args.config_path, task_input_json=args.task_input_json
        )
