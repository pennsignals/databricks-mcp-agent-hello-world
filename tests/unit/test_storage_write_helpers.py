from __future__ import annotations

import pytest

from databricks_mcp_agent_hello_world.storage import write
from tests.helpers import make_settings


def test_event_rows_jsonl_path_points_under_local_data_dir(tmp_path) -> None:
    assert write._event_rows_jsonl_path(str(tmp_path)).name == "agent_events.jsonl"


def test_write_event_rows_noops_for_empty_rows(tmp_path) -> None:
    assert (
        write.write_event_rows(
            make_settings(storage={"local_data_dir": str(tmp_path)}),
            [],
        )
        is None
    )


def test_write_event_rows_requires_remote_table_when_spark_is_available(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.write.get_spark_session",
        lambda: object(),
    )

    with pytest.raises(ValueError, match=r"storage\.agent_events_table must be configured"):
        write.write_event_rows(
            make_settings(storage={"agent_events_table": "   ", "local_data_dir": str(tmp_path)}),
            [{"schema_version": "1"}],
        )


def test_append_delta_event_rows_writes_arrow_table_to_delta(monkeypatch) -> None:
    save_calls: list[str] = []

    class FakeWriter:
        def mode(self, value):
            assert value == "append"
            return self

        def saveAsTable(self, table_name):
            save_calls.append(table_name)

    class FakeDataFrame:
        write = FakeWriter()

    class FakeSpark:
        def createDataFrame(self, arrow_table):
            return FakeDataFrame()

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.write.validate_event_rows",
        lambda rows: "arrow-table",
    )

    write._append_delta_event_rows(FakeSpark(), "main.demo.events", [{"schema_version": "1"}])

    assert save_calls == ["main.demo.events"]
