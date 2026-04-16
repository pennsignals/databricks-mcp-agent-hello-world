from __future__ import annotations

from ..config import Settings
from .result_repository import append_delta_table_event_rows, append_local_jsonl_event_rows
from .spark_utils import get_spark_session


class ResultWriter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.spark = get_spark_session()

    def write_event_rows(self, rows: list[dict[str, object]]) -> None:
        if not rows:
            return

        if self.spark is not None:
            table_name = (getattr(self.settings.storage, "agent_events_table", "") or "").strip()
            if not table_name:
                raise ValueError(
                    "storage.agent_events_table must be configured when Spark is available."
                )
            append_delta_table_event_rows(self.spark, table_name, rows)
            return

        local_data_dir = getattr(self.settings.storage, "local_data_dir", "./.local_state")
        append_local_jsonl_event_rows(local_data_dir, rows)
