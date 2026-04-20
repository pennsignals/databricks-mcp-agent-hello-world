from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from ..config import Settings

if TYPE_CHECKING:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.config import Config
    from databricks_openai import DatabricksOpenAI


def _workspace_client_config_kwargs(settings: Settings) -> dict[str, str]:
    kwargs: dict[str, str] = {}
    if settings.databricks_config_profile:
        kwargs["profile"] = settings.databricks_config_profile
    if settings.workspace_host:
        kwargs["host"] = settings.workspace_host
    return kwargs


@lru_cache(maxsize=8)
def _cached_config(profile: str | None, host: str | None) -> "Config":
    from databricks.sdk.config import Config

    kwargs = {
        key: value
        for key, value in {
            "profile": profile,
            "host": host,
        }.items()
        if value
    }
    return Config(**kwargs)


@lru_cache(maxsize=8)
def _cached_workspace_client(profile: str | None, host: str | None) -> "WorkspaceClient":
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient(config=_cached_config(profile, host))


def get_workspace_client(settings: Settings) -> "WorkspaceClient":
    kwargs = _workspace_client_config_kwargs(settings)
    return _cached_workspace_client(kwargs.get("profile"), kwargs.get("host"))


@lru_cache(maxsize=8)
def _cached_openai_client(profile: str | None, host: str | None) -> "DatabricksOpenAI":
    from databricks_openai import DatabricksOpenAI

    return DatabricksOpenAI(workspace_client=_cached_workspace_client(profile, host))


def get_openai_client(settings: Settings) -> "DatabricksOpenAI":
    kwargs = _workspace_client_config_kwargs(settings)
    return _cached_openai_client(kwargs.get("profile"), kwargs.get("host"))
