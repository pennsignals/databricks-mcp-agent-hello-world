from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import load_settings, parse_task_input, parse_task_input_file
from .discovery import discover_tools
from .evals.harness import EvalSetupError, run_evals
from .models import (
    AgentRunRecord,
    AgentTaskRequest,
)
from .preflight import run_preflight
from .runner.agent_runner import AgentRunner
from .storage.bootstrap import init_storage


@dataclass(frozen=True, slots=True)
class CommandResult:
    exit_code: int
    payload: Any


def run_preflight_command(config_path: str) -> CommandResult:
    report = run_preflight(config_path)
    return CommandResult(exit_code=0 if report.overall_status == "pass" else 1, payload=report)


def run_discover_tools_command(config_path: str) -> CommandResult:
    settings = _load_settings_for_command(config_path, "discover-tools")
    report = discover_tools(settings)
    return CommandResult(exit_code=0, payload=report)


def run_agent_task_command(
    config_path: str,
    *,
    task_input_json: str | None = None,
    task_input_file: str | None = None,
) -> CommandResult:
    if (task_input_json is None) == (task_input_file is None):
        raise ValueError(
            "run-agent-task requires exactly one of --task-input-json or --task-input-file."
        )

    settings = _load_settings_for_command(
        config_path,
        "run-agent-task",
        next_step="run_agent_task_job",
    )
    request = _build_agent_task_request(
        _load_task_payload(task_input_json=task_input_json, task_input_file=task_input_file),
        command_name="run-agent-task",
    )
    record = AgentRunner(settings).run(request)
    return CommandResult(exit_code=_agent_run_exit_code(record), payload=record)


def run_evals_command(
    config_path: str,
    *,
    scenario_file: str = "evals/sample_scenarios.json",
) -> CommandResult:
    try:
        settings = load_settings(config_path)
    except Exception as exc:  # noqa: BLE001
        raise EvalSetupError(
            f"Unable to load config from {Path(config_path)} while running run-evals: {exc}"
        ) from exc

    try:
        report = run_evals(settings, scenario_file)
    except EvalSetupError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise EvalSetupError(str(exc)) from exc

    return CommandResult(exit_code=0 if report.all_passed else 1, payload=report)


def run_init_storage_command(config_path: str) -> CommandResult:
    settings = load_settings(config_path)
    report = init_storage(settings)
    return CommandResult(exit_code=report.exit_code, payload=report)


def _load_task_payload(
    *,
    task_input_json: str | None,
    task_input_file: str | None,
) -> dict[str, Any]:
    if task_input_json is not None:
        return parse_task_input(task_input_json)
    return parse_task_input_file(task_input_file)


def _build_agent_task_request(
    payload: dict[str, Any],
    *,
    command_name: str,
) -> AgentTaskRequest:
    missing_fields = [
        field_name
        for field_name in ("task_name", "instructions", "payload")
        if field_name not in payload
    ]
    if missing_fields:
        formatted = ", ".join(missing_fields)
        raise RuntimeError(f"{command_name} requires task fields: {formatted}.")

    request_kwargs = {
        "task_name": payload["task_name"],
        "instructions": payload["instructions"],
        "payload": payload["payload"],
    }
    if payload.get("run_id"):
        request_kwargs["run_id"] = payload["run_id"]
    return AgentTaskRequest(**request_kwargs)


def _load_settings_for_command(
    config_path: str,
    command_name: str,
    *,
    next_step: str | None = None,
):
    try:
        return load_settings(config_path)
    except FileNotFoundError as exc:
        location = Path(config_path)
        if next_step:
            raise RuntimeError(
                f"Missing config file at {location} while running {command_name}. "
                f"Create workspace-config.yml and rerun {next_step}."
            ) from exc
        raise RuntimeError(
            f"Missing config file at {location} while running {command_name}."
        ) from exc


def _agent_run_exit_code(record: AgentRunRecord) -> int:
    if record.status == "success":
        return 0
    if record.status in {"max_steps_exceeded", "error"}:
        return 1
    raise ValueError(f"Unsupported agent run status: {record.status}")
