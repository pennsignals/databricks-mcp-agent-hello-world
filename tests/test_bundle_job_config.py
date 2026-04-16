from __future__ import annotations

from pathlib import Path

import yaml

JOB_RESOURCE_PATH = Path("resources/databricks_mcp_agent_hello_world_job.yml")


def _load_job_resource() -> dict:
    return yaml.safe_load(JOB_RESOURCE_PATH.read_text(encoding="utf-8"))


def test_job_uses_databricks_specific_wheel_entry_point() -> None:
    job = _load_job_resource()["resources"]["jobs"]["run_agent_task_job"]
    wheel_task = job["tasks"][0]["python_wheel_task"]

    assert wheel_task["package_name"] == "databricks-mcp-agent-hello-world"
    assert wheel_task["entry_point"] == "run-agent-task-job"
    assert wheel_task["named_parameters"] == {
        "config_path": "${workspace.file_path}/workspace-config.yml",
        "task_input_json": "${var.task_input_json}",
        "output": "text",
    }


def test_job_uses_concrete_artifact_dependency_without_wildcards() -> None:
    environment = _load_job_resource()["resources"]["jobs"]["run_agent_task_job"]["environments"][0]
    dependency = environment["spec"]["dependencies"][0]

    assert environment["spec"]["environment_version"] == "4"
    assert dependency == (
        "${workspace.root_path}/artifacts/.internal/"
        "databricks_mcp_agent_hello_world-0.1.0-py3-none-any.whl"
    )
    assert "${workspace.file_path}/dist/*.whl" not in dependency
    assert "*" not in dependency
