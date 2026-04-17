from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from databricks_mcp_agent_hello_world.devtools.version_sync import (
    format_sync_result,
    sync_version_refs,
)
from databricks_mcp_agent_hello_world.versioning import (
    expected_bundle_wheel_path,
    read_project_name,
    read_project_version,
)


def _bundle_yaml_with_dependency(dependency: str) -> str:
    return "\n".join(
        [
            "resources:",
            "  jobs:",
            "    run_agent_task_job:",
            "      environments:",
            "        - environment_key: default",
            "          spec:",
            '            environment_version: "4"',
            "            dependencies:",
            f"              - {dependency}",
            "    init_storage_job:",
            "      environments:",
            "        - environment_key: default",
            "          spec:",
            '            environment_version: "4"',
            "            dependencies:",
            f"              - {dependency}",
            "",
        ]
    )


def test_sync_version_refs_updates_stale_yaml_resource_file(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.yml"
    stale_dependency = (
        "${workspace.root_path}/artifacts/.internal/"
        "databricks_mcp_agent_hello_world-0.0.1-py3-none-any.whl"
    )
    bundle_path.write_text(_bundle_yaml_with_dependency(stale_dependency), encoding="utf-8")

    result = sync_version_refs(bundle_resource_path=bundle_path)
    updated = bundle_path.read_text(encoding="utf-8")

    assert result.changed is True
    assert result.replacements == 2
    assert result.version == read_project_version()
    assert expected_bundle_wheel_path(read_project_version(), read_project_name()) in updated
    assert stale_dependency not in updated
    assert format_sync_result(result) == (
        f"Updated bundle wheel path(s) to version {read_project_version()}"
    )


def test_sync_version_refs_is_noop_when_bundle_resource_is_already_in_sync(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.yml"
    dependency = expected_bundle_wheel_path(read_project_version(), read_project_name())
    original = _bundle_yaml_with_dependency(dependency)
    bundle_path.write_text(original, encoding="utf-8")

    result = sync_version_refs(bundle_resource_path=bundle_path)

    assert result.changed is False
    assert result.replacements == 2
    assert bundle_path.read_text(encoding="utf-8") == original
    assert format_sync_result(result) == "No version reference changes needed"


def test_sync_version_refs_check_mode_fails_when_bundle_resource_is_stale(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.yml"
    bundle_path.write_text(
        _bundle_yaml_with_dependency(
            "${workspace.root_path}/artifacts/.internal/"
            "databricks_mcp_agent_hello_world-0.0.1-py3-none-any.whl"
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Version references are stale"):
        sync_version_refs(check=True, bundle_resource_path=bundle_path)


def test_sync_version_refs_fails_clearly_when_expected_pattern_is_missing(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.yml"
    bundle_path.write_text(
        "\n".join(
            [
                "resources:",
                "  jobs:",
                "    run_agent_task_job:",
                "      environments:",
                "        - environment_key: default",
                "          spec:",
                "            dependencies:",
                "              - ${workspace.file_path}/dist/*.whl",
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Did not find any bundle wheel path"):
        sync_version_refs(bundle_resource_path=bundle_path)


def test_sync_version_refs_script_runs_from_plain_repo_checkout() -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    completed = subprocess.run(
        [sys.executable, "scripts/sync_version_refs.py", "--help"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "Sync version-derived wheel references." in completed.stdout
