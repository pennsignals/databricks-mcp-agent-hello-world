from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def _normalize_record(record: Any) -> dict[str, Any]:
    if hasattr(record, "model_dump"):
        return record.model_dump()
    if is_dataclass(record):
        return asdict(record)
    if isinstance(record, dict):
        return record
    raise TypeError(f"Unsupported record type: {type(record)!r}")


class LocalJsonlRepository:
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def append(self, name: str, record: Any) -> None:
        path = self.base_dir / f"{name}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(_normalize_record(record), ensure_ascii=False) + "\n")


class DeltaOrLocalRepository:
    def __init__(self, spark, base_dir: str):
        self.spark = spark
        self.local = LocalJsonlRepository(base_dir)

    def append(self, table_name: str | None, fallback_name: str, record: Any) -> None:
        normalized = _normalize_record(record)
        if self.spark and table_name:
            df = self.spark.createDataFrame([normalized])
            df.write.mode("append").saveAsTable(table_name)
            return
        self.local.append(fallback_name, normalized)
