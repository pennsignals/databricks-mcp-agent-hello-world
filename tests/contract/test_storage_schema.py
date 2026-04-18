import json

import pyarrow as pa

from databricks_mcp_agent_hello_world.storage import schema


def test_event_schema_contains_current_persisted_fields() -> None:
    field_names = schema.EVENT_SCHEMA.names

    assert "run_key" in field_names
    assert "event_index" in field_names
    assert "payload_json" in field_names
    assert "conversation_id" not in field_names
    assert "event_id" not in field_names


def test_serialize_event_row_is_json_serializable_and_truncates_excerpt() -> None:
    row = schema.serialize_event_row(
        run_key="run-123",
        task_name="workspace_onboarding_brief",
        event_index=7,
        event_type="tool_result",
        payload={"message": "hello", "nested": {"count": 1}},
        final_response_excerpt="x" * 700,
    )

    assert row["schema_version"] == schema.SCHEMA_VERSION
    assert row["run_key"] == "run-123"
    assert row["event_index"] == 7
    assert isinstance(row["payload_json"], str)
    assert json.loads(row["payload_json"]) == {"message": "hello", "nested": {"count": 1}}
    assert row["final_response_excerpt"] == "x" * 500


def test_arrow_schema_helpers_match_storage_contract() -> None:
    arrow_schema = pa.schema(
        [
            pa.field("event_index", pa.int64(), nullable=False),
            pa.field("payload_json", pa.large_string(), nullable=False),
            pa.field("error_message", pa.string(), nullable=True),
        ]
    )

    assert schema.arrow_schema_to_sql_columns(arrow_schema) == (
        "`event_index` BIGINT NOT NULL,\n"
        "`payload_json` STRING NOT NULL,\n"
        "`error_message` STRING"
    )
    assert schema.arrow_schema_to_field_specs(arrow_schema) == [
        schema.SchemaFieldSpec(name="event_index", data_type="bigint", nullable=False),
        schema.SchemaFieldSpec(name="payload_json", data_type="string", nullable=False),
        schema.SchemaFieldSpec(name="error_message", data_type="string", nullable=True),
    ]
