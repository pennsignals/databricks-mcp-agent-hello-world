from __future__ import annotations

import json
from datetime import datetime, timezone

import pyarrow as pa

SCHEMA_VERSION = "v1"
_FINAL_RESPONSE_EXCERPT_LIMIT = 500

EVENT_SCHEMA = pa.schema(
    [
        pa.field("schema_version", pa.string(), nullable=False),
        pa.field("conversation_id", pa.string(), nullable=False),
        pa.field("run_key", pa.string(), nullable=False),
        pa.field("task_name", pa.string(), nullable=False),
        pa.field("turn_index", pa.int64(), nullable=True),
        pa.field("event_index", pa.int64(), nullable=False),
        pa.field("event_id", pa.string(), nullable=False),
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


def get_canonical_event_schema() -> pa.Schema:
    return EVENT_SCHEMA


def build_empty_event_table() -> pa.Table:
    return pa.Table.from_pylist([], schema=EVENT_SCHEMA)


def validate_event_rows(rows: list[dict[str, object]]) -> pa.Table:
    return pa.Table.from_pylist(rows, schema=EVENT_SCHEMA)


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
    conversation_id: str,
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

    return {
        "schema_version": SCHEMA_VERSION,
        "conversation_id": conversation_id,
        "run_key": run_key,
        "task_name": task_name,
        "turn_index": turn_index,
        "event_index": event_index,
        "event_id": f"{conversation_id}:{event_index}",
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
