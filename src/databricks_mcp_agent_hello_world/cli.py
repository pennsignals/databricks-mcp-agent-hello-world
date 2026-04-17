from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

from .config import DEFAULT_CONFIG_PATH, load_settings, parse_task_input, parse_task_input_file
from .evals.harness import EvalSetupError, run_evals
from .logging_utils import configure_logging
from .models import AgentTaskRequest
from .ops import (
    discover_tools,
    print_discovery_report,
    print_json_report,
    print_preflight_summary,
    run_preflight,
)
from .runner.agent_runner import AgentRunner

OUTPUT_CHOICES = ("text", "json")
COMMAND_NAMES = (
    "preflight",
    "discover-tools",
    "run-agent-task",
    "run-evals",
)


def preflight_entrypoint() -> None:
    raise SystemExit(run_named_command("preflight"))


def discover_tools_entrypoint() -> None:
    raise SystemExit(run_named_command("discover-tools"))


def run_agent_task_entrypoint() -> None:
    raise SystemExit(run_named_command("run-agent-task"))


def run_evals_entrypoint() -> None:
    raise SystemExit(run_named_command("run-evals"))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(
            "Usage: python -m databricks_mcp_agent_hello_world.cli "
            "<command> [options]",
            file=sys.stderr,
        )
        return 2

    command_name = args[0]
    if command_name not in COMMAND_NAMES:
        print(
            f"Invalid command {command_name!r}. Expected one of: {', '.join(COMMAND_NAMES)}",
            file=sys.stderr,
        )
        return 2
    return run_named_command(
        command_name,
        args[1:],
        prog=f"{Path(sys.argv[0]).name} {command_name}",
    )


def run_named_command(
    command_name: str,
    argv: list[str] | None = None,
    *,
    prog: str | None = None,
) -> int:
    configure_logging()
    parser = build_parser(command_name, prog=prog or command_name)
    try:
        args = parser.parse_args(argv)
        return COMMAND_HANDLERS[command_name](args)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2
    except EvalSetupError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1


def build_parser(command_name: str, *, prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, description=f"{command_name} command")
    parser.add_argument("--config-path", default=DEFAULT_CONFIG_PATH)

    if command_name == "run-agent-task":
        parser.add_argument("--output", choices=OUTPUT_CHOICES, default="text")
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--task-input-json")
        group.add_argument("--task-input-file")
    elif command_name == "run-evals":
        parser.add_argument("--output", choices=OUTPUT_CHOICES, default="text")
        parser.add_argument("--scenario-file", default="evals/sample_scenarios.json")
    elif command_name in {"preflight", "discover-tools"}:
        parser.add_argument("--output", choices=OUTPUT_CHOICES, default="text")

    return parser


def _run_preflight(args: argparse.Namespace) -> int:
    report = run_preflight(args.config_path)
    _render_output(report, output_format=args.output, text_renderer=print_preflight_summary)
    return 0 if report.overall_status == "pass" else 1


def _run_discover_tools(args: argparse.Namespace) -> int:
    settings = _load_settings_for_command(args.config_path, "discover-tools")
    report = discover_tools(settings)
    _render_output(report, output_format=args.output, text_renderer=print_discovery_report)
    return 0


def _run_agent_task(args: argparse.Namespace) -> int:
    settings = _load_settings_for_command(
        args.config_path,
        "run-agent-task",
        next_step="run_agent_task_job",
    )
    request = _build_agent_task_request(
        _load_task_payload(args),
        command_name="run-agent-task",
    )
    runner = AgentRunner(settings)
    record = runner.run(request)
    _render_output(record, output_format=args.output, text_renderer=_print_run_summary)
    return 0


def _run_evals(args: argparse.Namespace) -> int:
    try:
        settings = load_settings(args.config_path)
    except Exception as exc:  # noqa: BLE001
        raise EvalSetupError(
            f"Unable to load config from {Path(args.config_path)} while running run-evals: {exc}"
        ) from exc

    try:
        summary = run_evals(settings, args.scenario_file)
    except EvalSetupError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise EvalSetupError(str(exc)) from exc

    _render_output(summary, output_format=args.output, text_renderer=_print_eval_summary)
    return 0 if summary.all_passed else 1


def _load_task_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.task_input_json:
        return parse_task_input(args.task_input_json)
    return parse_task_input_file(args.task_input_file)


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


def _render_output(
    payload: Any,
    *,
    output_format: str,
    text_renderer: Callable[[Any], None],
) -> None:
    if output_format == "json":
        print_json_report(payload)
        return
    text_renderer(payload)


def _print_run_summary(record) -> None:
    print(f"Run status: {record.status}")
    print(f"Run id: {record.run_id}")
    print(f"Task name: {record.task_name}")
    print(f"Tools called: {len(record.tools_called)}")
    final_response = record.result.get("final_response")
    if final_response:
        print("Final answer:")
        print(final_response)


def _print_eval_summary(summary) -> None:
    for result in summary.results:
        if result.passed:
            print(f"PASS {result.scenario_id}")
            continue
        print(f"FAIL {result.scenario_id}: {'; '.join(result.failed_checks)}")
    print(f"Passed {summary.passed_scenarios}/{summary.total_scenarios} scenarios")


COMMAND_HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "preflight": _run_preflight,
    "discover-tools": _run_discover_tools,
    "run-agent-task": _run_agent_task,
    "run-evals": _run_evals,
}


if __name__ == "__main__":
    raise SystemExit(main())
