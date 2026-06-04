"""Starter package for a non-interactive Databricks agent with local code tools."""

from .versioning import read_installed_package_version

__all__ = [
    "__version__",
    "discover_tools",
    "run_agent_task",
    "run_init_storage",
    "run_preflight",
]
__version__ = read_installed_package_version("databricks_tool_agent_template")


# Databricks Python wheel tasks in resources/jobs.yml call these package-root
# functions via package_name + entry_point.
def _raise_if_failed(exit_code: int) -> None:
    if exit_code:
        raise SystemExit(exit_code)


def discover_tools() -> None:
    from .cli import discover_tools_main

    _raise_if_failed(discover_tools_main())


def run_preflight() -> None:
    from .cli import preflight_main

    _raise_if_failed(preflight_main())


def run_agent_task() -> None:
    from .cli import run_agent_task_main

    _raise_if_failed(run_agent_task_main())


def run_init_storage() -> None:
    from .cli import run_init_storage_main

    _raise_if_failed(run_init_storage_main())
