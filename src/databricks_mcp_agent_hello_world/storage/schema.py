from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

import pyarrow as pa

"""Canonical persisted event-row schema and serialization helpers.

Persisted event identity is the pair (run_key, event_index). We do not store
conversation_id because it duplicated run_key, and we do not store event_id
because callers can derive that composite when needed.
"""

SCHEMA_VERSION = "v1"
_FINAL_RESPONSE_EXCERPT_LIMIT = 500


@dataclass(frozen=True, slots=True)
class SchemaFieldSpec:
    name: str
    data_type: str
    nullable: bool


EVENT_SCHEMA = pa.schema(
    [
        pa.field("schema_version", pa.string(), nullable=False),
        pa.field("run_key", pa.string(), nullable=False),
        pa.field("task_name", pa.string(), nullable=False),
        pa.field("turn_index", pa.int64(), nullable=True),
        pa.field("event_index", pa.int64(), nullable=False),
        pa.field("event_type", pa.string(), nullable=False),
        pa.field("status", pa.string(), nullable=True),
        pa.field("tool_name", pa.string(), nullable=True),
        pa.field("tool_call_id", pa.string(), nullable=True),
        pa.field("model_name", pa.string(), nullable=True),
        pa.field("inventory_hash", pa.string(), nullable=True),
        pa.field("final_response_excerpt", pa.string(), nullable=True),
        pa.field("error_message", pa.string(), nullable=True),
        pa.field("payload_json", pa.large_string(), nullable=False),
        pa.field("created_at", pa.string(), nullable=False),
    ]
)


def validate_event_rows(rows: list[dict[str, object]]) -> pa.Table:
    return pa.Table.from_pylist(rows, schema=EVENT_SCHEMA)


def arrow_field_to_spark_sql_type(field: pa.Field) -> str:
    field_type = field.type
    if pa.types.is_string(field_type) or pa.types.is_large_string(field_type):
        return "STRING"
    if pa.types.is_int64(field_type):
        return "BIGINT"
    raise ValueError(f"Unsupported Arrow type for field {field.name}: {field_type}")


def arrow_schema_to_sql_columns(schema: pa.Schema) -> str:
    column_lines: list[str] = []
    for field in schema:
        nullability_sql = "" if field.nullable else " NOT NULL"
        column_lines.append(
            f"`{field.name}` {arrow_field_to_spark_sql_type(field)}{nullability_sql}"
        )
    return ",\n".join(column_lines)


def arrow_schema_to_field_specs(schema: pa.Schema) -> list[SchemaFieldSpec]:
    field_specs: list[SchemaFieldSpec] = []
    for field in schema:
        field_specs.append(
            SchemaFieldSpec(
                name=field.name,
                data_type=_arrow_field_to_spark_field_type(field),
                nullable=field.nullable,
            )
        )
    return field_specs


def safe_jsonable(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): safe_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [safe_jsonable(item) for item in value]

    if hasattr(value, "model_dump"):
        return safe_jsonable(value.model_dump(mode="json"))
    if hasattr(value, "as_dict"):
        return safe_jsonable(value.as_dict())
    if hasattr(value, "dict") and not isinstance(value, dict):
        return safe_jsonable(value.dict())

    return json.loads(json.dumps(value, default=str))


def json_dumps_compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def serialize_event_row(
    *,
    run_key: str,
    task_name: str,
    event_index: int,
    event_type: str,
    payload: object,
    turn_index: int | None = None,
    status: str | None = None,
    tool_name: str | None = None,
    tool_call_id: str | None = None,
    model_name: str | None = None,
    inventory_hash: str | None = None,
    final_response_excerpt: str | None = None,
    error_message: str | None = None,
    created_at: str | None = None,
) -> dict[str, object]:
    excerpt = final_response_excerpt
    if excerpt is not None:
        excerpt = excerpt[:_FINAL_RESPONSE_EXCERPT_LIMIT]

    # Events are reconstructed by the per-run identity pair (run_key, event_index).
    # We intentionally do not persist composite identifiers like event_id.
    return {
        "schema_version": SCHEMA_VERSION,
        "run_key": run_key,
        "task_name": task_name,
        "turn_index": turn_index,
        "event_index": event_index,
        "event_type": event_type,
        "status": status,
        "tool_name": tool_name,
        "tool_call_id": tool_call_id,
        "model_name": model_name,
        "inventory_hash": inventory_hash,
        "final_response_excerpt": excerpt,
        "error_message": error_message,
        "payload_json": json_dumps_compact(safe_jsonable(payload)),
        "created_at": created_at or _utc_now_iso(),
    }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _arrow_field_to_spark_field_type(field: pa.Field) -> str:
    return arrow_field_to_spark_sql_type(field).lower()
