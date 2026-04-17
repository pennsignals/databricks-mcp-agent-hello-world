from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

from .commands import (
    CommandResult,
    run_agent_task_command,
    run_discover_tools_command,
    run_evals_command,
    run_preflight_command,
)
from .config import DEFAULT_CONFIG_PATH
from .evals.harness import EvalSetupError
from .logging_utils import configure_logging
from .ops import (
    print_discovery_report,
    print_json_report,
    print_preflight_summary,
)

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
        command_result = COMMAND_HANDLERS[command_name](args)
        _render_command_result(command_name, args, command_result)
        return command_result.exit_code
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


def _run_preflight(args: argparse.Namespace) -> CommandResult:
    return run_preflight_command(args.config_path)


def _run_discover_tools(args: argparse.Namespace) -> CommandResult:
    return run_discover_tools_command(args.config_path)


def _run_agent_task(args: argparse.Namespace) -> CommandResult:
    return run_agent_task_command(
        args.config_path,
        task_input_json=args.task_input_json,
        task_input_file=args.task_input_file,
    )


def _run_evals(args: argparse.Namespace) -> CommandResult:
    return run_evals_command(args.config_path, scenario_file=args.scenario_file)


def _render_command_result(
    command_name: str,
    args: argparse.Namespace,
    command_result: CommandResult,
) -> None:
    text_renderers: dict[str, Callable[[Any], None]] = {
        "preflight": print_preflight_summary,
        "discover-tools": print_discovery_report,
        "run-agent-task": _print_run_summary,
        "run-evals": _print_eval_summary,
    }
    _render_output(
        command_result.payload,
        output_format=getattr(args, "output", "text"),
        text_renderer=text_renderers[command_name],
    )


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


COMMAND_HANDLERS: dict[str, Callable[[argparse.Namespace], CommandResult]] = {
    "preflight": _run_preflight,
    "discover-tools": _run_discover_tools,
    "run-agent-task": _run_agent_task,
    "run-evals": _run_evals,
}


if __name__ == "__main__":
    raise SystemExit(main())
