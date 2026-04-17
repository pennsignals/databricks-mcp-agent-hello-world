"""Starter package for a non-interactive Databricks agent with local code tools."""

from .job_entrypoints import run_agent_task, run_init_storage

__all__ = ["__version__", "run_agent_task", "run_init_storage"]
__version__ = "0.1.0"
