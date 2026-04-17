"""Starter package for a non-interactive Databricks agent with local code tools."""

from .job_entrypoints import run_agent_task, run_init_storage
from .versioning import read_installed_package_version

__all__ = ["__version__", "run_agent_task", "run_init_storage"]
__version__ = read_installed_package_version("databricks-mcp-agent-hello-world")
