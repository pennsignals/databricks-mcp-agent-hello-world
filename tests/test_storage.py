import json
from pathlib import Path
from types import SimpleNamespace

from databricks_mcp_agent_hello_world.storage.result_writer import ResultWriter


def test_result_writer_appends_run_and_output_rows_locally(
    tmp_path: Path, monkeypatch
) -> None:
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
    output_rows = (tmp_path / "agent_outputs.jsonl").read_text(encoding="utf-8").strip().splitlines()

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
