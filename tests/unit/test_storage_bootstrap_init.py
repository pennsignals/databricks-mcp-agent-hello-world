from __future__ import annotations

from types import SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world.storage import bootstrap
from tests.helpers import make_settings


def test_init_storage_requires_remote_table_when_spark_is_available(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: object(),
    )

    with pytest.raises(ValueError, match=r"storage\.agent_events_table must be configured"):
        bootstrap.init_storage(
            make_settings(
                storage={
                    "agent_events_table": "   ",
                    "local_data_dir": str(tmp_path),
                }
            )
        )


def test_init_storage_reports_existing_matching_table(tmp_path, monkeypatch) -> None:
    same_schema_spark = SimpleNamespace(
        sql=lambda query: SimpleNamespace(
            collect=lambda: (
                [SimpleNamespace(tableName="events")]
                if query.startswith("SHOW TABLES")
                else [SimpleNamespace()]
            )
        ),
        table=lambda name: SimpleNamespace(schema=SimpleNamespace(fields=[])),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.catalog_exists",
        lambda spark_obj, name: True,
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.schema_exists",
        lambda spark_obj, target_obj: True,
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.table_exists",
        lambda spark_obj, target_obj: True,
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.compare_table_schema",
        lambda spark_obj, target_obj: None,
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: same_schema_spark,
    )

    matched = bootstrap.init_storage(
        make_settings(
            storage={
                "agent_events_table": "main.demo.events",
                "local_data_dir": str(tmp_path),
            }
        )
    )

    assert matched.exit_code == 0
    assert matched.messages == ["Table main.demo.events already exists and matches expected schema"]


def test_storage_table_exists_delegates_to_table_exists(monkeypatch) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.table_exists",
        lambda spark_obj, target_obj: True,
    )

    assert bootstrap.storage_table_exists(object(), "main.demo.events") is True
