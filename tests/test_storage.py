import json
from types import SimpleNamespace

import pyarrow as pa

from databricks_mcp_agent_hello_world.storage.persistence_schema import (
    EVENT_SCHEMA,
    SCHEMA_VERSION,
    serialize_event_row,
    validate_event_rows,
)
from databricks_mcp_agent_hello_world.storage.result_writer import ResultWriter


def _event_row(**overrides):
    return serialize_event_row(
        conversation_id=overrides.pop("conversation_id", "conv-1"),
        run_key=overrides.pop("run_key", "run-1"),
        task_name=overrides.pop("task_name", "workspace_onboarding_brief"),
        turn_index=overrides.pop("turn_index", 0),
        event_index=overrides.pop("event_index", 3),
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


def test_validate_event_rows_accepts_valid_event_rows() -> None:
    row = _event_row()

    table = validate_event_rows([row])

    assert isinstance(table, pa.Table)
    assert table.schema == EVENT_SCHEMA
    assert table.num_rows == 1
    assert table.column("event_id").to_pylist() == ["conv-1:3"]
    assert table.column("payload_json").to_pylist() == [row["payload_json"]]


def test_validate_event_rows_rejects_invalid_event_rows() -> None:
    row = _event_row(event_index="not-an-int")

    try:
        validate_event_rows([row])
    except (pa.ArrowInvalid, pa.ArrowTypeError, ValueError, TypeError):
        pass
    else:
        raise AssertionError("Expected Arrow validation to fail for an invalid event row.")


def test_serialize_event_row_is_deterministic_and_json_string_payload() -> None:
    row = _event_row(
        conversation_id="conversation-123",
        event_index=7,
        final_response_excerpt="x" * 700,
    )

    assert row["schema_version"] == SCHEMA_VERSION
    assert row["event_id"] == "conversation-123:7"
    assert isinstance(row["payload_json"], str)
    assert json.loads(row["payload_json"]) == {"message": "hello", "nested": {"count": 1}}
    assert row["final_response_excerpt"] == "x" * 500
    assert isinstance(row["created_at"], str)


def test_result_writer_writes_validated_event_rows_locally(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.result_writer.get_spark_session",
        lambda: None,
    )

    settings = SimpleNamespace(
        storage=SimpleNamespace(
            local_data_dir=str(tmp_path),
            agent_events_table="main.agent.agent_events",
        )
    )
    writer = ResultWriter(settings)
    row = _event_row()

    writer.write_event_rows([row])

    output_path = tmp_path / "agent_events.jsonl"
    written_rows = output_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(written_rows) == 1
    persisted = json.loads(written_rows[0])
    assert persisted["event_id"] == "conv-1:3"
    assert isinstance(persisted["payload_json"], str)
    assert json.loads(persisted["payload_json"]) == {"message": "hello", "nested": {"count": 1}}


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


def test_result_writer_uses_arrow_table_for_spark_event_writes(monkeypatch) -> None:
    spark = _FakeSparkSession()
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.result_writer.get_spark_session",
        lambda: spark,
    )

    settings = SimpleNamespace(
        storage=SimpleNamespace(
            local_data_dir=".local_state",
            agent_events_table="main.agent.agent_events",
        )
    )
    writer = ResultWriter(settings)
    row = _event_row(payload={"tool_result": {"team": "support"}})

    writer.write_event_rows([row])

    assert isinstance(spark.arrow_table, pa.Table)
    assert spark.arrow_table.schema == EVENT_SCHEMA
    assert spark.arrow_table.column("payload_json").to_pylist() == [
        json.dumps({"tool_result": {"team": "support"}}, ensure_ascii=False, separators=(",", ":"))
    ]
    assert spark.last_dataframe is not None
    assert spark.last_dataframe.write.mode_name == "append"
    assert spark.last_dataframe.write.table_name == "main.agent.agent_events"
