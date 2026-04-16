import json
from pathlib import Path
from types import SimpleNamespace

from databricks_mcp_agent_hello_world.storage.result_repository import (
    append_delta_table_record,
)
from databricks_mcp_agent_hello_world.storage.result_writer import ResultWriter


def test_result_writer_appends_run_and_output_rows_locally(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.result_writer.get_spark_session",
        lambda: None,
    )

    settings = SimpleNamespace(
        storage=SimpleNamespace(
            local_data_dir=str(tmp_path),
            agent_runs_table="main.agent.agent_runs",
            agent_output_table="main.agent.agent_outputs",
        )
    )
    writer = ResultWriter(settings)

    writer.write_run_record(
        {
            "run_id": "run-1",
            "task_name": "workspace_onboarding_brief",
            "status": "success",
            "tools_called": [],
            "llm_turn_count": 2,
            "result": {"final_response": "done", "available_tools": ["tool_a"]},
        }
    )
    writer.write_output_record(
        {
            "run_id": "run-1",
            "task_name": "workspace_onboarding_brief",
            "status": "success",
            "output_payload": {"final_response": "hello"},
        }
    )

    run_rows = (tmp_path / "agent_runs.jsonl").read_text(encoding="utf-8").strip().splitlines()
    output_rows = (
        (tmp_path / "agent_outputs.jsonl").read_text(encoding="utf-8").strip().splitlines()
    )

    assert len(run_rows) == 1
    assert len(output_rows) == 1

    run_payload = json.loads(run_rows[0])
    output_payload = json.loads(output_rows[0])

    assert set(run_payload) == {
        "run_id",
        "task_name",
        "status",
        "tools_called",
        "llm_turn_count",
        "result",
    }
    assert run_payload["run_id"] == "run-1"
    assert run_payload["result"]["final_response"] == "done"

    assert set(output_payload) == {
        "run_id",
        "task_name",
        "status",
        "output_payload",
    }
    assert output_payload["run_id"] == "run-1"
    assert output_payload["output_payload"]["final_response"] == "hello"


class _FakeDeltaWriter:
    def __init__(self, frame: "_FakeDataFrame"):
        self.frame = frame
        self.mode_name: str | None = None
        self.table_name: str | None = None

    def mode(self, mode_name: str) -> "_FakeDeltaWriter":
        self.mode_name = mode_name
        return self

    def saveAsTable(self, table_name: str) -> None:
        self.table_name = table_name


class _FakeDataFrame:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.write = _FakeDeltaWriter(self)


class _FakeSparkSession:
    def __init__(self):
        self.rows: list[dict] | None = None
        self.last_dataframe: _FakeDataFrame | None = None

    def createDataFrame(self, rows: list[dict]) -> _FakeDataFrame:
        self.rows = rows
        self.last_dataframe = _FakeDataFrame(rows)
        return self.last_dataframe


def test_append_delta_table_record_serializes_nested_values_to_json() -> None:
    spark = _FakeSparkSession()

    append_delta_table_record(
        spark,
        "main.agent.agent_runs",
        {
            "run_id": "run-1",
            "task_name": "workspace_onboarding_brief",
            "status": "success",
            "llm_turn_count": 2,
            "tools_called": [{"tool_name": "lookup_user", "arguments": {"name": "Renée"}}],
            "result": {
                "final_response": "All set",
                "available_tools": ["lookup_user"],
                "tool_calls": [{"tool_name": "lookup_user", "error": None}],
                "metadata": {"emoji": "cafe ☕"},
            },
            "error_message": None,
        },
    )

    assert spark.rows is not None
    persisted = spark.rows[0]

    assert persisted["run_id"] == "run-1"
    assert persisted["llm_turn_count"] == 2
    assert persisted["error_message"] is None
    assert json.loads(persisted["tools_called"]) == [
        {"tool_name": "lookup_user", "arguments": {"name": "Renée"}}
    ]
    assert json.loads(persisted["result"]) == {
        "final_response": "All set",
        "available_tools": ["lookup_user"],
        "tool_calls": [{"tool_name": "lookup_user", "error": None}],
        "metadata": {"emoji": "cafe ☕"},
    }
    assert spark.last_dataframe is not None
    assert spark.last_dataframe.write.mode_name == "append"
    assert spark.last_dataframe.write.table_name == "main.agent.agent_runs"


def test_result_writer_uses_delta_path_for_run_records_with_serialized_payloads(
    monkeypatch,
) -> None:
    spark = _FakeSparkSession()
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.result_writer.get_spark_session",
        lambda: spark,
    )

    settings = SimpleNamespace(
        storage=SimpleNamespace(
            local_data_dir=".local_state",
            agent_runs_table="main.agent.agent_runs",
            agent_output_table="main.agent.agent_outputs",
        )
    )
    writer = ResultWriter(settings)

    writer.write_run_record(
        {
            "run_id": "run-1",
            "task_name": "workspace_onboarding_brief",
            "status": "success",
            "tools_called": [{"tool_name": "lookup_user", "arguments": {"team": "support"}}],
            "llm_turn_count": 2,
            "result": {"final_response": "done", "available_tools": ["tool_a"]},
        }
    )

    assert spark.rows is not None
    persisted = spark.rows[0]
    assert persisted["run_id"] == "run-1"
    assert isinstance(persisted["tools_called"], str)
    assert isinstance(persisted["result"], str)
    assert json.loads(persisted["tools_called"]) == [
        {"tool_name": "lookup_user", "arguments": {"team": "support"}}
    ]
    assert json.loads(persisted["result"]) == {
        "final_response": "done",
        "available_tools": ["tool_a"],
    }


def test_result_writer_uses_delta_path_for_output_records_with_serialized_payloads(
    monkeypatch,
) -> None:
    spark = _FakeSparkSession()
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.result_writer.get_spark_session",
        lambda: spark,
    )

    settings = SimpleNamespace(
        storage=SimpleNamespace(
            local_data_dir=".local_state",
            agent_runs_table="main.agent.agent_runs",
            agent_output_table="main.agent.agent_outputs",
        )
    )
    writer = ResultWriter(settings)

    writer.write_output_record(
        {
            "run_id": "run-1",
            "task_name": "workspace_onboarding_brief",
            "status": "success",
            "output_payload": {
                "final_response": "hello",
                "sections": ["setup", "validation"],
                "details": {"owner": "Renée"},
            },
        }
    )

    assert spark.rows is not None
    persisted = spark.rows[0]
    assert persisted["run_id"] == "run-1"
    assert isinstance(persisted["output_payload"], str)
    assert json.loads(persisted["output_payload"]) == {
        "final_response": "hello",
        "sections": ["setup", "validation"],
        "details": {"owner": "Renée"},
    }
