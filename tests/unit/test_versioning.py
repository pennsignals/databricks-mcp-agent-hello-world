from __future__ import annotations

import tomllib
from pathlib import Path

from databricks_mcp_agent_hello_world.versioning import (
    bundle_wheel_glob,
    distribution_name_for_wheel,
    read_installed_package_version,
    read_project_name,
)

PYPROJECT_PATH = Path("pyproject.toml")


def test_read_project_name_from_pyproject() -> None:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    assert read_project_name() == pyproject["project"]["name"]


def test_distribution_name_for_wheel_normalizes_project_name() -> None:
    assert distribution_name_for_wheel("databricks-mcp-agent-hello-world") == (
        "databricks_mcp_agent_hello_world"
    )


def test_bundle_wheel_glob_uses_canonical_dist_pattern() -> None:
    assert bundle_wheel_glob("databricks-mcp-agent-hello-world") == (
        "../dist/databricks_mcp_agent_hello_world-*.whl"
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
