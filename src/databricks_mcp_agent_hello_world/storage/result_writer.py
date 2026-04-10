from __future__ import annotations

from ..config import Settings
from ..models import AgentOutputRecord, AgentRunRecord
from .result_repository import DeltaOrLocalRepository
from .spark_utils import get_spark_session


class ResultWriter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.repository = DeltaOrLocalRepository(
            get_spark_session(), settings.storage.local_data_dir
        )

    def write_run_record(self, record: AgentRunRecord) -> None:
        self.repository.append(self.settings.storage.agent_runs_table, "agent_runs", record)

    def write_output_record(self, output_record: AgentOutputRecord) -> None:
        self.repository.append(
            self.settings.storage.agent_outputs_table, "agent_outputs", output_record
        )
