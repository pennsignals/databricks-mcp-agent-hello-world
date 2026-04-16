from __future__ import annotations

import json
import time
from functools import lru_cache
from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.config import Config
from databricks.sdk.service.sql import StatementParameterListItem, StatementState
from databricks_openai import DatabricksOpenAI

from ..config import Settings


def _workspace_client_config_kwargs(settings: Settings) -> dict[str, str]:
    kwargs: dict[str, str] = {}
    if settings.databricks_cli_profile:
        kwargs["profile"] = settings.databricks_cli_profile
    if settings.workspace_host:
        kwargs["host"] = settings.workspace_host
    return kwargs


@lru_cache(maxsize=8)
def _cached_config(profile: str | None, host: str | None) -> Config:
    kwargs = {
        key: value
        for key, value in {
            "profile": profile,
            "host": host,
        }.items()
        if value
    }
    return Config(**kwargs)


def get_databricks_config(settings: Settings) -> Config:
    kwargs = _workspace_client_config_kwargs(settings)
    return _cached_config(kwargs.get("profile"), kwargs.get("host"))


@lru_cache(maxsize=8)
def _cached_workspace_client(profile: str | None, host: str | None) -> WorkspaceClient:
    return WorkspaceClient(config=_cached_config(profile, host))


def get_workspace_client(settings: Settings) -> WorkspaceClient:
    kwargs = _workspace_client_config_kwargs(settings)
    return _cached_workspace_client(kwargs.get("profile"), kwargs.get("host"))


@lru_cache(maxsize=8)
def _cached_openai_client(profile: str | None, host: str | None) -> DatabricksOpenAI:
    return DatabricksOpenAI(workspace_client=_cached_workspace_client(profile, host))


def get_openai_client(settings: Settings) -> DatabricksOpenAI:
    kwargs = _workspace_client_config_kwargs(settings)
    return _cached_openai_client(kwargs.get("profile"), kwargs.get("host"))


class DatabricksWorkspaceGateway:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.workspace_client = get_workspace_client(settings)

    def get_serving_endpoint(self) -> dict[str, Any]:
        endpoint = self.workspace_client.serving_endpoints.get(self.settings.llm_endpoint_name)
        if hasattr(endpoint, "as_dict"):
            return endpoint.as_dict()
        return json.loads(json.dumps(endpoint, default=str))

    def list_warehouses(self) -> list[dict[str, Any]]:
        warehouses = []
        for warehouse in self.workspace_client.warehouses.list():
            warehouses.append(
                warehouse.as_dict() if hasattr(warehouse, "as_dict") else dict(warehouse)
            )
        return warehouses


class DatabricksSqlGateway:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.workspace_client = get_workspace_client(settings)

    def is_configured(self) -> bool:
        return bool(self.settings.sql.warehouse_id)

    def execute_query(
        self,
        statement: str,
        *,
        parameters: dict[str, Any] | None = None,
        row_limit: int = 50,
        wait_timeout: str = "30s",
    ) -> list[dict[str, Any]]:
        if not self.settings.sql.warehouse_id:
            raise ValueError(
                "DATABRICKS_SQL_WAREHOUSE_ID must be configured for Databricks SQL tools."
            )

        sdk_parameters = [
            StatementParameterListItem(name=name, value=None if value is None else str(value))
            for name, value in (parameters or {}).items()
        ]
        response = self.workspace_client.statement_execution.execute_statement(
            statement=statement,
            warehouse_id=self.settings.sql.warehouse_id,
            catalog=self.settings.sql.catalog,
            schema=self.settings.sql.schema,
            wait_timeout=wait_timeout,
            row_limit=row_limit,
            parameters=sdk_parameters or None,
        )
        response = self._wait_for_terminal_state(response)
        return self._rows_from_response(response)

    def _wait_for_terminal_state(self, response):
        deadline = time.time() + 60
        current = response
        while (
            current.status
            and current.status.state in {StatementState.PENDING, StatementState.RUNNING}
            and current.statement_id
        ):
            if time.time() > deadline:
                raise TimeoutError("Timed out waiting for Databricks SQL statement execution.")
            time.sleep(1)
            current = self.workspace_client.statement_execution.get_statement(current.statement_id)
        if current.status and current.status.state != StatementState.SUCCEEDED:
            message = (
                current.status.error.message
                if current.status and current.status.error
                else "SQL execution failed."
            )
            raise RuntimeError(message)
        return current

    def _rows_from_response(self, response) -> list[dict[str, Any]]:
        column_names = []
        if response.manifest and response.manifest.schema and response.manifest.schema.columns:
            column_names = [
                column.name or f"col_{idx}"
                for idx, column in enumerate(response.manifest.schema.columns)
            ]

        rows = list(self._chunk_to_rows(column_names, response.result))
        next_chunk_index = response.result.next_chunk_index if response.result else None
        while next_chunk_index is not None and response.statement_id:
            chunk = self.workspace_client.statement_execution.get_statement_result_chunk_n(
                response.statement_id,
                next_chunk_index,
            )
            rows.extend(self._chunk_to_rows(column_names, chunk))
            next_chunk_index = chunk.next_chunk_index
        return rows

    @staticmethod
    def _chunk_to_rows(column_names: list[str], chunk) -> list[dict[str, Any]]:
        data_array = chunk.data_array if chunk and chunk.data_array else []
        rows: list[dict[str, Any]] = []
        for row in data_array:
            row_dict = {
                column_names[idx] if idx < len(column_names) else f"col_{idx}": value
                for idx, value in enumerate(row)
            }
            rows.append(row_dict)
        return rows
