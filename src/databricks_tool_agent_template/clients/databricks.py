from __future__ import annotations

from typing import TYPE_CHECKING

from ..config import Settings

if TYPE_CHECKING:
    from databricks.sdk import WorkspaceClient
    from databricks_openai.utils.clients import DatabricksOpenAI


def _workspace_client_kwargs(settings: Settings) -> dict[str, str]:
    kwargs: dict[str, str] = {}
    if settings.databricks_config_profile:
        kwargs["profile"] = settings.databricks_config_profile
    if settings.workspace_host:
        kwargs["host"] = settings.workspace_host
    return kwargs


def get_workspace_client(settings: Settings) -> WorkspaceClient:
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient(**_workspace_client_kwargs(settings))


def get_openai_client(settings: Settings) -> DatabricksOpenAI:
    from databricks_openai.utils.clients import DatabricksOpenAI

    return DatabricksOpenAI(workspace_client=get_workspace_client(settings))
