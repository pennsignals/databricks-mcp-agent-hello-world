"""Starter package for a non-interactive Databricks agent with local code tools."""

from .versioning import read_installed_package_version

__all__ = ["__version__", "run_agent_task", "run_init_storage"]
__version__ = read_installed_package_version("databricks-mcp-agent-hello-world")


def run_agent_task() -> None:
    from .job_entrypoints import run_agent_task as _run_agent_task

    _run_agent_task()


def run_init_storage() -> None:
    from .job_entrypoints import run_init_storage as _run_init_storage

    _run_init_storage()
