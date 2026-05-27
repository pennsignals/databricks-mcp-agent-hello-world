"""Starter package for a non-interactive Databricks agent with local code tools."""

from .versioning import read_installed_package_version

__all__ = ["__version__", "discover_tools", "run_agent_task", "run_init_storage"]
__version__ = read_installed_package_version("databricks-mcp-agent-hello-world")


# Databricks Python wheel tasks in resources/jobs.yml call these package-root
# functions via package_name + entry_point.
def discover_tools() -> None:
    from .cli import discover_tools_main

    raise SystemExit(discover_tools_main())


def run_agent_task() -> None:
    from .cli import run_agent_task_main

    raise SystemExit(run_agent_task_main())


def run_init_storage() -> None:
    from .cli import run_init_storage_main

    raise SystemExit(run_init_storage_main())
