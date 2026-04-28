from __future__ import annotations

from pathlib import Path

import yaml

from databricks_mcp_agent_hello_world.versioning import (
    bundle_wheel_glob,
    read_project_name,
)

JOB_RESOURCE_PATH = Path("resources/jobs.yml")


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_bundle_includes_current_job_resource_file() -> None:
    bundle = _load_yaml(Path("databricks.yml"))

    assert "resources/*.yml" in bundle["include"]
    assert JOB_RESOURCE_PATH.exists()


def test_bundle_uses_databricks_auth_configuration_for_workspace_hosts() -> None:
    bundle = _load_yaml(Path("databricks.yml"))
    targets = bundle["targets"]

    assert "dev_workspace_host" not in bundle.get("variables", {})
    assert "prod_workspace_host" not in bundle.get("variables", {})
    assert "host" not in targets["local"]["workspace"]
    assert "host" not in targets["dev"]["workspace"]
    assert "host" not in targets["prod"]["workspace"]


def test_bundle_targets_separate_local_dev_and_prod_deployments() -> None:
    bundle = _load_yaml(Path("databricks.yml"))
    targets = bundle["targets"]

    assert set(targets) == {"local", "dev", "prod"}

    assert targets["local"]["mode"] == "development"
    assert targets["local"]["default"] is True
    assert targets["local"]["workspace"]["root_path"] == "~/.bundle/${bundle.name}/${bundle.target}"

    assert "mode" not in targets["dev"]
    assert (
        targets["dev"]["workspace"]["root_path"]
        == "/Shared/.bundle/${bundle.name}/${bundle.target}"
    )
    assert targets["dev"]["presets"]["name_prefix"] == "dev_"
    assert targets["dev"]["presets"]["trigger_pause_status"] == "PAUSED"

    assert targets["prod"]["mode"] == "production"
    assert (
        targets["prod"]["workspace"]["root_path"]
        == "/Shared/.bundle/${bundle.name}/${bundle.target}"
    )
    assert targets["prod"]["git"]["branch"] == "main"

    assert "permissions" not in targets["local"]
    assert "permissions" not in targets["dev"]
    assert "permissions" not in targets["prod"]


def test_jobs_use_current_python_wheel_entrypoints_and_environment_dependency_glob() -> None:
    jobs = _load_yaml(JOB_RESOURCE_PATH)["resources"]["jobs"]
    expected_library = bundle_wheel_glob(read_project_name())

    init_job = jobs["init_storage_job"]
    run_job = jobs["run_agent_task_job"]
    init_task = init_job["tasks"][0]
    run_task = run_job["tasks"][0]
    init_wheel_task = init_task["python_wheel_task"]
    run_wheel_task = run_task["python_wheel_task"]
    init_dependencies = init_job["environments"][0]["spec"]["dependencies"]
    run_dependencies = run_job["environments"][0]["spec"]["dependencies"]

    assert init_task["environment_key"] == "default"
    assert run_task["environment_key"] == "default"
    assert "libraries" not in init_task
    assert "libraries" not in run_task
    assert init_wheel_task["entry_point"] == "run_init_storage"
    assert run_wheel_task["entry_point"] == "run_agent_task"
    assert expected_library in init_dependencies
    assert expected_library in run_dependencies


def test_bundle_does_not_define_placeholder_task_variable() -> None:
    bundle = _load_yaml(Path("databricks.yml"))

    assert "task_input_json" not in bundle.get("variables", {})


def test_deployed_runtime_job_uses_canonical_sample_task_file() -> None:
    jobs = _load_yaml(JOB_RESOURCE_PATH)["resources"]["jobs"]
    run_task = jobs["run_agent_task_job"]["tasks"][0]["python_wheel_task"]

    assert run_task["parameters"] == [
        "--config-path",
        "${workspace.file_path}/workspace-config.yml",
        "--task-input-file",
        "${workspace.file_path}/examples/demo_run_task.json",
        "--output",
        "text",
    ]
