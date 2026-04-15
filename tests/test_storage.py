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
            "profile_name": "default",
            "profile_version": "v1",
            "tools_called": [],
        }
    )
    writer.write_output_record(
        {
            "run_id": "run-1",
            "task_name": "workspace_onboarding_brief",
            "status": "success",
            "profile_name": "default",
            "profile_version": "v1",
            "output_payload": {"final_response": "hello"},
        }
    )

    run_rows = (tmp_path / "agent_runs.jsonl").read_text(encoding="utf-8").strip().splitlines()
    output_rows = (
        tmp_path / "agent_outputs.jsonl"
    ).read_text(encoding="utf-8").strip().splitlines()

    assert len(run_rows) == 1
    assert len(output_rows) == 1
    assert '"run_id": "run-1"' in run_rows[0]
    assert '"final_response": "hello"' in output_rows[0]
