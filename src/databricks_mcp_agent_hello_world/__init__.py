"""Starter package for a non-interactive Databricks agent with local code tools."""

from .versioning import read_installed_package_version

__all__ = ["__version__", "run_agent_task", "run_init_storage"]
__version__ = read_installed_package_version("databricks-mcp-agent-hello-world")


def run_agent_task() -> None:
    import sys

    from .cli import run_named_command

    exit_code = run_named_command(
        "run-agent-task",
        sys.argv[1:],
        prog="run-agent-task",
    )
    if exit_code:
        raise SystemExit(exit_code)


def run_init_storage() -> None:
    import argparse
    import sys

    from .commands import run_init_storage_command
    from .config import DEFAULT_CONFIG_PATH
    from .logging_utils import configure_logging

    configure_logging()
    parser = argparse.ArgumentParser(prog="run_init_storage")
    parser.add_argument("--config-path", default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args(sys.argv[1:])

    result = run_init_storage_command(args.config_path)
    for message in result.payload.messages:
        print(message)
    if result.exit_code:
        raise SystemExit(result.exit_code)
