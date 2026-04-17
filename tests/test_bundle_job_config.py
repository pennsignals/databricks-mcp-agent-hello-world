from __future__ import annotations

from pathlib import Path

import yaml

JOB_RESOURCE_PATH = Path("resources/databricks_mcp_agent_hello_world_job.yml")


def _load_job_resource() -> dict:
    return yaml.safe_load(JOB_RESOURCE_PATH.read_text(encoding="utf-8"))


def test_init_storage_job_uses_databricks_specific_wheel_entry_point() -> None:
    job = _load_job_resource()["resources"]["jobs"]["init_storage_job"]
    wheel_task = job["tasks"][0]["python_wheel_task"]

    assert wheel_task["package_name"] == "databricks_mcp_agent_hello_world"
    assert wheel_task["entry_point"] == "run_init_storage"
    assert "named_parameters" not in wheel_task
    assert wheel_task["parameters"] == [
        "--config-path",
        "${workspace.file_path}/workspace-config.yml",
    ]


def test_job_uses_databricks_specific_wheel_entry_point() -> None:
    job = _load_job_resource()["resources"]["jobs"]["run_agent_task_job"]
    wheel_task = job["tasks"][0]["python_wheel_task"]

    assert wheel_task["package_name"] == "databricks_mcp_agent_hello_world"
    assert wheel_task["entry_point"] == "run_agent_task"
    assert "named_parameters" not in wheel_task
    assert wheel_task["parameters"] == [
        "--config-path",
        "${workspace.file_path}/workspace-config.yml",
        "--task-input-json",
        "${var.task_input_json}",
        "--output",
        "text",
    ]


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


def test_init_storage_job_uses_same_environment_pattern_as_runtime_job() -> None:
    jobs = _load_job_resource()["resources"]["jobs"]
    init_environment = jobs["init_storage_job"]["environments"][0]
    runtime_environment = jobs["run_agent_task_job"]["environments"][0]

    assert init_environment == runtime_environment
