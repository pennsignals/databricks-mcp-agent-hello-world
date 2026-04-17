from __future__ import annotations

import argparse
import sys

from .cli import run_named_command
from .config import DEFAULT_CONFIG_PATH, load_settings
from .storage.bootstrap import init_storage
from .tooling.runtime import set_runtime_settings


def run_agent_task() -> None:
    exit_code = run_named_command(
        "run-agent-task",
        sys.argv[1:],
        prog="run-agent-task",
    )
    if exit_code:
        raise SystemExit(exit_code)


def run_init_storage() -> None:
    parser = argparse.ArgumentParser(prog="run_init_storage")
    parser.add_argument("--config-path", default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args(sys.argv[1:])

    settings = load_settings(args.config_path)
    set_runtime_settings(settings)
    report = init_storage(settings)
    for message in report.messages:
        print(message)
    if report.exit_code:
        raise SystemExit(report.exit_code)
