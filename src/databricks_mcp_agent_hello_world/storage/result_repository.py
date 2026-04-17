from __future__ import annotations

from pathlib import Path

from .persistence_schema import json_dumps_compact, validate_event_rows

EVENTS_JSONL_FILE_NAME = "agent_events.jsonl"


def append_local_jsonl_event_rows(base_dir: str, rows: list[dict[str, object]]) -> None:
    if not rows:
        return

    table = validate_event_rows(rows)
    path = Path(base_dir) / EVENTS_JSONL_FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in table.to_pylist():
            handle.write(json_dumps_compact(row) + "\n")


def append_delta_table_event_rows(
    spark, table_name: str, rows: list[dict[str, object]]
) -> None:
    if not rows:
        return

    arrow_table = validate_event_rows(rows)
    spark.createDataFrame(arrow_table).write.mode("append").saveAsTable(table_name)
