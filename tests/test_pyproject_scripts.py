import tomllib
from pathlib import Path

PYPROJECT_PATH = Path("pyproject.toml")


def test_databricks_job_script_entry_point_is_absent() -> None:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    scripts = pyproject["project"]["scripts"]

    assert "run-agent-task-job" not in scripts
    assert (
        scripts["init-storage"]
        == "databricks_mcp_agent_hello_world.cli:init_storage_entrypoint"
    )
    assert (
        scripts["run-agent-task"]
        == "databricks_mcp_agent_hello_world.cli:run_agent_task_entrypoint"
    )
