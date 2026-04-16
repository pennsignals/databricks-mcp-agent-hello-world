from __future__ import annotations

from ..config import Settings
from ..models import AgentOutputRecord, AgentRunRecord
from .result_repository import append_delta_table_record, append_local_jsonl_record
from .spark_utils import get_spark_session


class ResultWriter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.spark = get_spark_session()

    def write_run_record(self, record: AgentRunRecord) -> None:
        if self.spark is not None:
            table_name = (self.settings.storage.agent_runs_table or "").strip()
            if not table_name:
                raise ValueError(
                    "storage.agent_runs_table must be configured when Spark is available."
                )
            append_delta_table_record(self.spark, table_name, record)
            return
        append_local_jsonl_record(self.settings.storage.local_data_dir, "agent_runs", record)

    def write_output_record(self, output_record: AgentOutputRecord) -> None:
        if self.spark is not None:
            table_name = (self.settings.storage.agent_output_table or "").strip()
            if not table_name:
                raise ValueError(
                    "storage.agent_output_table must be configured when Spark is available."
                )
            append_delta_table_record(self.spark, table_name, output_record)
            return
        append_local_jsonl_record(
            self.settings.storage.local_data_dir, "agent_outputs", output_record
        )
