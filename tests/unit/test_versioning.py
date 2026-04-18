from __future__ import annotations

import tomllib
from pathlib import Path

from databricks_mcp_agent_hello_world.versioning import (
    expected_bundle_wheel_path,
    expected_wheel_filename,
    read_installed_package_version,
    read_project_name,
    read_project_version,
)

PYPROJECT_PATH = Path("pyproject.toml")


def test_read_project_version_from_pyproject() -> None:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    assert read_project_version() == pyproject["project"]["version"]


def test_expected_wheel_filename_uses_project_name_and_version() -> None:
    assert expected_wheel_filename("1.2.3", "databricks-mcp-agent-hello-world") == (
        "databricks_mcp_agent_hello_world-1.2.3-py3-none-any.whl"
    )


def test_expected_bundle_wheel_path_uses_canonical_bundle_prefix() -> None:
    assert expected_bundle_wheel_path("1.2.3", "databricks-mcp-agent-hello-world") == (
        "${workspace.root_path}/artifacts/.internal/"
        "databricks_mcp_agent_hello_world-1.2.3-py3-none-any.whl"
    )


def test_runtime_version_returns_installed_package_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.versioning.installed_version",
        lambda distribution_name: "9.9.9",
    )
    assert read_installed_package_version(read_project_name()) == "9.9.9"


def test_runtime_version_falls_back_when_package_metadata_is_missing(monkeypatch) -> None:
    from importlib.metadata import PackageNotFoundError

    def _raise(distribution_name: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr("databricks_mcp_agent_hello_world.versioning.installed_version", _raise)
    assert read_installed_package_version(read_project_name()) == "0+unknown"
