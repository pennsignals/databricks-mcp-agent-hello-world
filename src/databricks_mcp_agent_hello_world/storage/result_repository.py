from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def normalize_record(record: Any) -> dict[str, Any]:
    if hasattr(record, "model_dump"):
        return record.model_dump()
    if is_dataclass(record):
        return asdict(record)
    if isinstance(record, dict):
        return record
    raise TypeError(f"Unsupported record type: {type(record)!r}")


def append_local_jsonl_record(base_dir: str, name: str, record: Any) -> None:
    path = Path(base_dir) / f"{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(normalize_record(record), ensure_ascii=False) + "\n")


def append_delta_table_record(spark, table_name: str, record: Any) -> None:
    normalized = normalize_record(record)
    spark.createDataFrame([normalized]).write.mode("append").saveAsTable(table_name)
