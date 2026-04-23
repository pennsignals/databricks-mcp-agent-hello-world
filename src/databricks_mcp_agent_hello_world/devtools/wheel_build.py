from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from databricks_mcp_agent_hello_world.versioning import (
    DEFAULT_BOOTSTRAP_VERSION,
    distribution_name_for_wheel,
    read_project_name,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
VERSION_TAG_GLOB = "v[0-9]*"


@dataclass(frozen=True)
class WheelBuildResult:
    wheel_path: Path
    pretend_version: str | None


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def repository_has_version_tags(repo_root: Path = PROJECT_ROOT) -> bool:
    return bool(_git(repo_root, "tag", "--list", VERSION_TAG_GLOB))


def repository_is_dirty(repo_root: Path = PROJECT_ROOT) -> bool:
    return bool(_git(repo_root, "status", "--short"))


def commit_count(repo_root: Path = PROJECT_ROOT) -> int:
    return int(_git(repo_root, "rev-list", "--count", "HEAD") or "0")


def short_revision(repo_root: Path = PROJECT_ROOT) -> str:
    return _git(repo_root, "rev-parse", "--short", "HEAD")


def bootstrap_pretend_version(
    repo_root: Path = PROJECT_ROOT,
    *,
    base_version: str = DEFAULT_BOOTSTRAP_VERSION,
) -> str:
    version = f"{base_version}.dev{commit_count(repo_root)}+g{short_revision(repo_root)}"
    if repository_is_dirty(repo_root):
        version = f"{version}.d{datetime.now(UTC).strftime('%Y%m%d')}"
    return version


def build_environment_overrides(repo_root: Path = PROJECT_ROOT) -> dict[str, str]:
    if repository_has_version_tags(repo_root):
        return {}
    return {"SETUPTOOLS_SCM_PRETEND_VERSION": bootstrap_pretend_version(repo_root)}


def clean_build_artifacts(repo_root: Path = PROJECT_ROOT) -> None:
    for path in (repo_root / "build", repo_root / "dist"):
        shutil.rmtree(path, ignore_errors=True)


def discover_built_wheel(
    repo_root: Path = PROJECT_ROOT,
    *,
    project_name: str | None = None,
) -> Path:
    if project_name is None:
        project_name = read_project_name(repo_root / "pyproject.toml")
    distribution_name = distribution_name_for_wheel(project_name)
    wheel_paths = sorted((repo_root / "dist").glob(f"{distribution_name}-*.whl"))
    if not wheel_paths:
        raise RuntimeError(f"Did not find a built wheel for {distribution_name!r} in dist/.")
    if len(wheel_paths) != 1:
        raise RuntimeError(
            f"Expected exactly one built wheel for {distribution_name!r}, found {len(wheel_paths)}."
        )
    return wheel_paths[0]


def build_wheel(
    repo_root: Path = PROJECT_ROOT,
    *,
    python_executable: str = sys.executable,
    clean: bool = True,
    no_isolation: bool = True,
) -> WheelBuildResult:
    if clean:
        clean_build_artifacts(repo_root)

    command = [python_executable, "-m", "build", "--wheel"]
    if no_isolation:
        command.append("--no-isolation")

    env = os.environ.copy()
    overrides = build_environment_overrides(repo_root)
    env.update(overrides)
    subprocess.run(command, cwd=repo_root, env=env, check=True)
    project_name = read_project_name(repo_root / "pyproject.toml")

    return WheelBuildResult(
        wheel_path=discover_built_wheel(repo_root, project_name=project_name),
        pretend_version=overrides.get("SETUPTOOLS_SCM_PRETEND_VERSION"),
    )
