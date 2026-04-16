from __future__ import annotations

import sys

from .cli import run_named_command


def run_agent_task() -> None:
    exit_code = run_named_command(
        "run-agent-task",
        sys.argv[1:],
        prog="run-agent-task",
    )
    if exit_code:
        raise SystemExit(exit_code)
