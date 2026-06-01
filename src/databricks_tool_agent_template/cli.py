from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from .commands import (
    CommandResult,
    run_agent_task_command,
    run_discover_tools_command,
    run_evals_command,
    run_init_storage_command,
    run_preflight_command,
)
from .config import DEFAULT_CONFIG_PATH
from .evals.harness import EvalSetupError

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
    raise SystemExit(discover_tools_main())


def run_agent_task_entrypoint() -> None:
    raise SystemExit(run_agent_task_main())


def run_evals_entrypoint() -> None:
    raise SystemExit(run_named_command("run-evals"))


def discover_tools_main(argv: Sequence[str] | None = None) -> int:
    return run_named_command("discover-tools", _argv_list(argv), prog="discover-tools")


def run_agent_task_main(argv: Sequence[str] | None = None) -> int:
    return run_named_command("run-agent-task", _argv_list(argv), prog="run-agent-task")


# Internal wheel entrypoint runner. The underscore name mirrors the Databricks
# package-root callable and is intentionally not exposed as a normal CLI subcommand.
def run_init_storage_main(argv: Sequence[str] | None = None) -> int:
    return run_named_command("run_init_storage", _argv_list(argv), prog="run_init_storage")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(
            "Usage: python -m databricks_tool_agent_template.cli <command> [options]",
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
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _argv_list(argv: Sequence[str] | None) -> list[str] | None:
    return None if argv is None else list(argv)


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


def _run_init_storage(args: argparse.Namespace) -> CommandResult:
    return run_init_storage_command(args.config_path)


def _render_command_result(
    command_name: str,
    args: argparse.Namespace,
    command_result: CommandResult,
) -> None:
    text_renderers: dict[str, Callable[[Any], None]] = {
        "preflight": print_preflight_summary,
        "discover-tools": print_discovery_report,
        "run-agent-task": print_run_summary,
        "run-evals": _print_eval_summary,
        "run_init_storage": print_init_storage_summary,
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


def print_run_summary(record) -> None:
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
        print(f"FAIL {result.scenario_id}")
        print(f"  Checks failed: {', '.join(result.failed_checks)}")
        print(f"  Task name: {result.task_name}")
        if result.run_record_id:
            print(f"  Run id: {result.run_record_id}")
        if "status_mismatch" in result.failed_checks:
            print(f"  Expected status: {result.expected_status}")
            print(f"  Actual status: {result.actual_status or '-'}")
        if "missing_required_output_substrings" in result.failed_checks:
            print(
                "  Missing output substrings: "
                f"{', '.join(result.missing_required_output_substrings)}"
            )
        if "missing_required_executed_tools" in result.failed_checks:
            print(f"  Missing executed tools: {', '.join(result.missing_required_executed_tools)}")
            print(f"  Executed tools: {_format_csv(result.executed_tools)}")
        if "forbidden_executed_tools" in result.failed_checks:
            print(f"  Forbidden executed tools: {', '.join(result.forbidden_executed_tools)}")
            print(f"  Executed tools: {_format_csv(result.executed_tools)}")
        if "scenario_execution_error" in result.failed_checks:
            print("  Scenario execution failed before scoring.")
            if result.scenario_execution_error_message:
                print(f"  Error: {result.scenario_execution_error_message}")
        if (
            "missing_required_output_substrings" in result.failed_checks
            and result.final_response_excerpt
        ):
            print(f"  Final response excerpt: {result.final_response_excerpt}")
        print()
    print(f"Passed {summary.passed_scenarios}/{summary.total_scenarios} scenarios")


def _format_csv(values: list[str]) -> str:
    return ", ".join(values) if values else "-"


def print_json_report(payload: Any) -> None:
    print(payload.model_dump_json(indent=2))


def print_preflight_summary(report) -> None:
    print(f"Preflight: {report.overall_status}")
    print(
        "Scope: local configuration sanity check; "
        "does not call the LLM endpoint or verify serving permissions."
    )
    for check in report.checks:
        print(f"- {check.name}: {check.status} - {check.message}")


def print_discovery_report(report) -> None:
    print(f"Enabled tool sources: {_format_csv(report.enabled_tool_sources)}")
    print(f"Total tools: {report.tool_count}")
    for tool in report.tools:
        function_spec = tool.spec.get("function", {})
        summary = _summarize_input_schema(function_spec.get("parameters", {}))
        description = function_spec.get("description", "")
        print(f"- {tool.name}: {description}")
        print(f"  Source: {tool.source_type}/{tool.source_id}")
        print(f"  Input schema: {summary}")


def print_init_storage_summary(report) -> None:
    for message in report.messages:
        print(message)


def _summarize_input_schema(schema: dict[str, Any]) -> str:
    properties = schema.get("properties", {})
    if not isinstance(properties, dict) or not properties:
        return "no parameters"
    required = set(schema.get("required", []))
    parts = []
    for name, value in properties.items():
        value_type = value.get("type", "any") if isinstance(value, dict) else "any"
        suffix = "required" if name in required else "optional"
        parts.append(f"{name}:{value_type} ({suffix})")
    return ", ".join(parts)


COMMAND_HANDLERS: dict[str, Callable[[argparse.Namespace], CommandResult]] = {
    "preflight": _run_preflight,
    "discover-tools": _run_discover_tools,
    "run-agent-task": _run_agent_task,
    "run-evals": _run_evals,
    "run_init_storage": _run_init_storage,
}


if __name__ == "__main__":
    raise SystemExit(main())
