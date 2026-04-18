from __future__ import annotations

import json
from pathlib import Path

import yaml

from databricks_mcp_agent_hello_world.versioning import (
    expected_bundle_wheel_path,
    read_project_name,
    read_project_version,
)

JOB_RESOURCE_PATH = Path("resources/jobs.yml")


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_bundle_includes_current_job_resource_file() -> None:
    bundle = _load_yaml(Path("databricks.yml"))

    assert "resources/*.yml" in bundle["include"]
    assert JOB_RESOURCE_PATH.exists()


def test_jobs_use_current_python_wheel_entrypoints_and_dependency() -> None:
    jobs = _load_yaml(JOB_RESOURCE_PATH)["resources"]["jobs"]
    expected_dependency = expected_bundle_wheel_path(read_project_version(), read_project_name())

    init_task = jobs["init_storage_job"]["tasks"][0]["python_wheel_task"]
    run_task = jobs["run_agent_task_job"]["tasks"][0]["python_wheel_task"]
    init_dependency = jobs["init_storage_job"]["environments"][0]["spec"]["dependencies"][0]
    run_dependency = jobs["run_agent_task_job"]["environments"][0]["spec"]["dependencies"][0]

    assert init_task["entry_point"] == "run_init_storage"
    assert run_task["entry_point"] == "run_agent_task"
    assert init_dependency == expected_dependency
    assert run_dependency == expected_dependency


def test_bundle_task_input_variable_references_canonical_sample_without_embedding_it() -> None:
    bundle = _load_yaml(Path("databricks.yml"))
    task_input_json = bundle["variables"]["task_input_json"]
    placeholder = json.loads(task_input_json["default"])

    assert "examples/demo_run_task.json" in task_input_json["description"]
    assert placeholder["task_name"] == "replace_me"
    assert placeholder["payload"] == {}
    assert placeholder["instructions"].startswith("See examples/demo_run_task.json")
