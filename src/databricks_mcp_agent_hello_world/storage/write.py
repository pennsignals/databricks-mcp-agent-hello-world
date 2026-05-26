from __future__ import annotations

from pathlib import Path

from ..config import Settings
from .schema import json_dumps_compact, validate_event_rows
from .spark import get_spark_session

EVENTS_JSONL_FILE_NAME = "agent_events.jsonl"


def write_event_rows(settings: Settings, rows: list[dict[str, object]]) -> None:
    if not rows:
        return

    spark = get_spark_session()
    if spark is not None:
        table_name = (getattr(settings.storage, "agent_events_table", "") or "").strip()
        if not table_name:
            raise ValueError(
                "storage.agent_events_table must be configured when Spark is available."
            )
        _append_delta_event_rows(spark, table_name, rows)
        return

    local_data_dir = getattr(settings.storage, "local_data_dir", "./.local_state")
    _append_local_jsonl_event_rows(local_data_dir, rows)


def _append_local_jsonl_event_rows(base_dir: str, rows: list[dict[str, object]]) -> None:
    table = validate_event_rows(rows)
    path = _event_rows_jsonl_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in table.to_pylist():
            handle.write(json_dumps_compact(row) + "\n")


def _append_delta_event_rows(spark, table_name: str, rows: list[dict[str, object]]) -> None:
    arrow_table = validate_event_rows(rows)
    spark.createDataFrame(arrow_table).write.mode("append").saveAsTable(table_name)


def _event_rows_jsonl_path(base_dir: str) -> Path:
    return Path(base_dir) / EVENTS_JSONL_FILE_NAME
