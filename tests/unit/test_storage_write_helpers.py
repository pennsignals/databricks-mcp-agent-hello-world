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


def test_write_event_rows_uses_local_jsonl_when_table_is_blank(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.write.require_spark_session",
        lambda: (_ for _ in ()).throw(AssertionError("Spark should not be required.")),
    )

    write.write_event_rows(
        make_settings(storage={"agent_events_table": "   ", "local_data_dir": str(tmp_path)}),
        [{"schema_version": "1"}],
    )

    assert (tmp_path / "agent_events.jsonl").exists()


def test_write_event_rows_requires_spark_when_table_is_configured(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.write.require_spark_session",
        lambda: (_ for _ in ()).throw(RuntimeError("no active Spark session")),
    )

    with pytest.raises(RuntimeError, match="no active Spark session"):
        write.write_event_rows(
            make_settings(
                storage={
                    "agent_events_table": "main.demo.events",
                    "local_data_dir": str(tmp_path),
                }
            ),
            [{"schema_version": "1"}],
        )

    assert not (tmp_path / "agent_events.jsonl").exists()


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

    write._append_spark_event_rows(FakeSpark(), "main.demo.events", [{"schema_version": "1"}])

    assert save_calls == ["main.demo.events"]
