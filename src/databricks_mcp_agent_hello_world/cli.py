from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

from .config import (
    DEFAULT_CONFIG_PATH,
    load_settings,
    parse_task_input,
    parse_task_input_file,
)
from .evals.harness import load_eval_scenarios, run_eval_scenarios
from .logging_utils import configure_logging
from .models import AgentTaskRequest
from .ops import (
    discover_tools,
    print_discovery_report,
    print_json_report,
    print_preflight_summary,
    run_preflight,
)
from .profiles.compiler import ToolProfileCompiler
from .profiles.compiler import build_hello_world_demo_task
from .runner.agent_runner import AgentRunner
from .tooling.runtime import set_runtime_settings

OUTPUT_CHOICES = ("text", "json")
COMMAND_NAMES = (
    "preflight",
    "discover-tools",
    "compile-tool-profile",
    "run-agent-task",
    "run-evals",
)


def preflight_entrypoint() -> None:
    raise SystemExit(run_named_command("preflight"))


def discover_tools_entrypoint() -> None:
    raise SystemExit(run_named_command("discover-tools"))


def compile_tool_profile_entrypoint() -> None:
    raise SystemExit(run_named_command("compile-tool-profile"))


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
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1


def build_parser(command_name: str, *, prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, description=f"{command_name} command")
    parser.add_argument("--config-path", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output", choices=OUTPUT_CHOICES, default="text")

    if command_name == "compile-tool-profile":
        parser.add_argument("--force-refresh", action="store_true")
    elif command_name == "run-agent-task":
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--task-input-json")
        group.add_argument("--task-input-file")
    elif command_name == "run-evals":
        parser.add_argument("--scenario")

    return parser


def _run_preflight(args: argparse.Namespace) -> int:
    report = run_preflight(args.config_path)
    _render_output(report, output_format=args.output, text_renderer=print_preflight_summary)
    return 0 if report.overall_status == "pass" else 1


def _run_discover_tools(args: argparse.Namespace) -> int:
    settings = _load_settings_for_command(args.config_path, "discover-tools")
    set_runtime_settings(settings)
    report = discover_tools(settings)
    _render_output(report, output_format=args.output, text_renderer=print_discovery_report)
    return 0


def _run_compile_tool_profile(args: argparse.Namespace) -> int:
    settings = _load_settings_for_command(
        args.config_path,
        "compile-tool-profile",
        next_step="compile_tool_profile_job",
    )
    set_runtime_settings(settings)
    compiler = ToolProfileCompiler(settings)
    result = compiler.compile(
        build_hello_world_demo_task(),
        force_refresh=args.force_refresh,
    )
    _render_output(result, output_format=args.output, text_renderer=_print_compilation_summary)
    return 0


def _run_agent_task(args: argparse.Namespace) -> int:
    settings = _load_settings_for_command(
        args.config_path,
        "run-agent-task",
        next_step="run_agent_task_job",
    )
    set_runtime_settings(settings)
    payload = _load_task_payload(args)
    request_kwargs = {
        "task_name": payload.get("task_name", "demo-task"),
        "instructions": payload.get("instructions", "Complete the requested task."),
        "payload": payload.get("payload", payload),
    }
    if payload.get("run_id"):
        request_kwargs["run_id"] = payload["run_id"]

    request = AgentTaskRequest(**request_kwargs)
    runner = AgentRunner(settings)
    record = runner.run(request)
    _render_output(record, output_format=args.output, text_renderer=_print_run_summary)
    return 0


def _run_evals(args: argparse.Namespace) -> int:
    settings = _load_settings_for_command(args.config_path, "run-evals")
    set_runtime_settings(settings)
    ToolProfileCompiler(settings).compile(build_hello_world_demo_task())
    runner = AgentRunner(settings)
    scenarios = load_eval_scenarios(str(Path("evals") / "sample_scenarios.json"))
    if args.scenario:
        summary = run_eval_scenarios(scenarios, runner, scenario_id=args.scenario)
        if summary.total_scenarios == 0:
            raise ValueError(f"Scenario not found: {args.scenario}")
    else:
        summary = run_eval_scenarios(scenarios, runner)
    _render_output(summary, output_format=args.output, text_renderer=_print_eval_summary)
    return 0


def _load_task_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.task_input_json:
        return parse_task_input(args.task_input_json)
    return parse_task_input_file(args.task_input_file)


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
        raise RuntimeError(f"Missing config file at {location} while running {command_name}.") from exc


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


def _print_compilation_summary(profile) -> None:
    status = "Reused" if profile.reused_existing else "Compiled"
    print(f"{status} tool profile: {profile.profile.profile_name}")
    print(f"Profile version: {profile.profile.profile_version}")
    print(f"Allowed tools: {len(profile.profile.allowed_tools)}")
    print(f"Inventory hash: {profile.profile.inventory_hash}")


def _print_run_summary(record) -> None:
    if hasattr(record, "status"):
        print(f"Run status: {record.status}")
        print(f"Run id: {record.run_id}")
        print(f"Task name: {record.task_name}")
        print(f"Tools called: {len(record.tools_called)}")
        final_response = record.result.get("final_response")
        if final_response:
            print("Final response:")
            print(final_response)
        return

    print(f"Task name: {record.task_name}")
    print(f"Available tools: {record.available_tools_count}")
    print(", ".join(record.available_tools))
    print(f"Allowed tools: {', '.join(record.allowed_tools)}")
    print(f"Tool calls: {len(record.tool_calls)}")
    if record.tool_calls:
        print(", ".join(call.tool_name for call in record.tool_calls))
    if record.final_answer:
        print("Final answer:")
        print(record.final_answer)


def _print_eval_summary(summary) -> None:
    print(
        "Eval summary: "
        f"{summary.passed} passed, {summary.failed} failed, {summary.errored} errored"
    )
    for result in summary.results:
        line = f"- {result.scenario_id}: {result.status}"
        if result.failure_reason:
            line += f" - {result.failure_reason}"
        print(line)


COMMAND_HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "preflight": _run_preflight,
    "discover-tools": _run_discover_tools,
    "compile-tool-profile": _run_compile_tool_profile,
    "run-agent-task": _run_agent_task,
    "run-evals": _run_evals,
}


if __name__ == "__main__":
    raise SystemExit(main())
