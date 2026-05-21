from __future__ import annotations

from pathlib import Path

import pytest

from databricks_mcp_agent_hello_world.devtools.wheel_build import discover_built_wheel
from databricks_mcp_agent_hello_world.versioning import (
    bundle_wheel_glob,
    read_project_name,
)


def test_bundle_wheel_glob_uses_project_distribution_name() -> None:
    assert (
        bundle_wheel_glob(read_project_name()) == "../dist/databricks_mcp_agent_hello_world-*.whl"
    )


def test_discover_built_wheel_rejects_missing_wheel(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Did not find a built wheel"):
        discover_built_wheel(
            tmp_path,
            project_name="databricks-mcp-agent-hello-world",
        )


def test_discover_built_wheel_rejects_ambiguous_wheels(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "databricks_mcp_agent_hello_world-0.1.0-py3-none-any.whl").write_text(
        "wheel-a",
        encoding="utf-8",
    )
    (dist_dir / "databricks_mcp_agent_hello_world-0.1.1-py3-none-any.whl").write_text(
        "wheel-b",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Expected exactly one built wheel"):
        discover_built_wheel(
            tmp_path,
            project_name="databricks-mcp-agent-hello-world",
        )
