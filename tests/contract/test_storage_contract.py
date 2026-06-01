from __future__ import annotations

import json

import pyarrow as pa
import pytest

from databricks_tool_agent_template.storage.schema import (
    EVENT_SCHEMA,
    serialize_event_row,
    validate_event_rows,
)
from databricks_tool_agent_template.storage.write import write_event_rows
from tests.helpers import make_settings


def _event_row(**overrides):
    return serialize_event_row(
        run_key=overrides.pop("run_key", "run-1"),
        task_name=overrides.pop("task_name", "customer_account_brief"),
        turn_index=overrides.pop("turn_index", 0),
        event_index=overrides.pop("event_index", 0),
        event_type=overrides.pop("event_type", "tool_result"),
        status=overrides.pop("status", "ok"),
        tool_name=overrides.pop("tool_name", "lookup_user"),
        tool_call_id=overrides.pop("tool_call_id", "call-1"),
        model_name=overrides.pop("model_name", "databricks-meta-llama"),
        inventory_hash=overrides.pop("inventory_hash", "inventory-hash"),
        final_response_excerpt=overrides.pop("final_response_excerpt", None),
        error_message=overrides.pop("error_message", None),
        payload=overrides.pop("payload", {"message": "hello", "nested": {"count": 1}}),
    )


def test_validate_event_rows_accepts_current_event_row_schema() -> None:
    table = validate_event_rows([_event_row()])

    assert isinstance(table, pa.Table)
    assert table.schema == EVENT_SCHEMA
    assert table.num_rows == 1


def test_write_event_rows_appends_jsonl_in_event_index_order(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "databricks_tool_agent_template.storage.write.require_spark_session",
        lambda: (_ for _ in ()).throw(AssertionError("Spark should not be required.")),
    )
    settings = make_settings(
        storage={
            "local_data_dir": str(tmp_path),
            "agent_events_table": None,
        }
    )
    rows = [_event_row(event_index=0), _event_row(event_index=1, payload={"step": 2})]

    write_event_rows(settings, rows)

    output_path = tmp_path / "agent_events.jsonl"
    persisted = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert [row["event_index"] for row in persisted] == [0, 1]
    assert all("conversation_id" not in row for row in persisted)
    assert all("event_id" not in row for row in persisted)
    assert json.loads(persisted[1]["payload_json"]) == {"step": 2}


def test_write_event_rows_requires_spark_without_local_fallback_when_table_is_configured(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "databricks_tool_agent_template.storage.write.require_spark_session",
        lambda: (_ for _ in ()).throw(RuntimeError("no active Spark session")),
    )
    settings = make_settings(
        storage={
            "local_data_dir": str(tmp_path),
            "agent_events_table": "main.agent.agent_events",
        }
    )

    with pytest.raises(RuntimeError, match="no active Spark session"):
        write_event_rows(settings, [_event_row()])

    assert not (tmp_path / "agent_events.jsonl").exists()


class _FakeDeltaWriter:
    def __init__(self, frame):
        self.frame = frame
        self.mode_name = None
        self.table_name = None

    def mode(self, mode_name: str):
        self.mode_name = mode_name
        return self

    def saveAsTable(self, table_name: str) -> None:
        self.table_name = table_name


class _FakeDataFrame:
    def __init__(self, arrow_table):
        self.arrow_table = arrow_table
        self.write = _FakeDeltaWriter(self)


class _FakeSparkSession:
    def __init__(self):
        self.arrow_table = None
        self.last_dataframe = None

    def createDataFrame(self, arrow_table):
        self.arrow_table = arrow_table
        self.last_dataframe = _FakeDataFrame(arrow_table)
        return self.last_dataframe


def test_write_event_rows_uses_arrow_table_for_spark_writes(monkeypatch) -> None:
    spark = _FakeSparkSession()
    monkeypatch.setattr(
        "databricks_tool_agent_template.storage.write.require_spark_session",
        lambda: spark,
    )
    settings = make_settings(
        storage={
            "local_data_dir": ".local_state",
            "agent_events_table": "main.agent.agent_events",
        }
    )

    write_event_rows(settings, [_event_row(payload={"tool_result": {"team": "support"}})])

    assert isinstance(spark.arrow_table, pa.Table)
    assert spark.arrow_table is not None
    assert spark.arrow_table.schema == EVENT_SCHEMA
    assert spark.last_dataframe is not None
    assert spark.last_dataframe.write.mode_name == "append"
    assert spark.last_dataframe.write.table_name == "main.agent.agent_events"
