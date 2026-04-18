from __future__ import annotations

from pathlib import Path

import yaml

from databricks_mcp_agent_hello_world.versioning import (
    expected_bundle_wheel_path,
    read_project_name,
    read_project_version,
)

JOB_RESOURCE_PATH = Path("resources/jobs.yml")


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
    expected_dependency = expected_bundle_wheel_path(
        read_project_version(),
        read_project_name(),
    )

    assert environment["spec"]["environment_version"] == "4"
    assert dependency == expected_dependency
    assert "${workspace.file_path}/dist/*.whl" not in dependency
    assert "*" not in dependency


def test_init_storage_job_uses_versioned_wheel_dependency() -> None:
    jobs = _load_job_resource()["resources"]["jobs"]
    init_environment = jobs["init_storage_job"]["environments"][0]
    dependency = init_environment["spec"]["dependencies"][0]

    assert init_environment["spec"]["environment_version"] == "4"
    assert dependency == expected_bundle_wheel_path(
        read_project_version(),
        read_project_name(),
    )
    assert "${workspace.file_path}/dist/*.whl" not in dependency
    assert "*" not in dependency
