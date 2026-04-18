"""Starter package for a non-interactive Databricks agent with local code tools."""

from .versioning import read_installed_package_version

__all__ = ["__version__", "run_agent_task", "run_init_storage"]
__version__ = read_installed_package_version("databricks-mcp-agent-hello-world")


def run_agent_task() -> None:
    import argparse
    import sys

    from .cli import OUTPUT_CHOICES, print_json_report, print_run_summary
    from .commands import run_agent_task_command
    from .config import DEFAULT_CONFIG_PATH

    parser = argparse.ArgumentParser(prog="run-agent-task")
    parser.add_argument("--config-path", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output", choices=OUTPUT_CHOICES, default="text")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--task-input-json")
    group.add_argument("--task-input-file")
    args = parser.parse_args(sys.argv[1:])

    result = run_agent_task_command(
        args.config_path,
        task_input_json=args.task_input_json,
        task_input_file=args.task_input_file,
    )
    if args.output == "json":
        print_json_report(result.payload)
    else:
        print_run_summary(result.payload)
    if result.exit_code:
        raise SystemExit(result.exit_code)


def run_init_storage() -> None:
    import argparse
    import sys

    from .commands import run_init_storage_command
    from .config import DEFAULT_CONFIG_PATH

    parser = argparse.ArgumentParser(prog="run_init_storage")
    parser.add_argument("--config-path", default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args(sys.argv[1:])

    result = run_init_storage_command(args.config_path)
    for message in result.payload.messages:
        print(message)
    if result.exit_code:
        raise SystemExit(result.exit_code)
