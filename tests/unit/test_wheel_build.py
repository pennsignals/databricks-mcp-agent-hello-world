from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from packaging.version import Version

from databricks_mcp_agent_hello_world.devtools.wheel_build import (
    bootstrap_pretend_version,
    build_environment_overrides,
    build_wheel,
    clean_build_artifacts,
    discover_built_wheel,
    repository_has_version_tags,
)


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init")
    _git(repo_root, "config", "user.name", "Codex")
    _git(repo_root, "config", "user.email", "codex@example.com")
    (repo_root / "tracked.txt").write_text("hello\n", encoding="utf-8")
    _git(repo_root, "add", "tracked.txt")
    _git(repo_root, "commit", "-m", "initial")
    return repo_root


def test_bootstrap_pretend_version_is_pep440_and_traceable(tmp_path: Path) -> None:
    repo_root = _init_repo(tmp_path)

    version = bootstrap_pretend_version(repo_root)

    parsed = Version(version)
    assert parsed.is_devrelease is True
    assert parsed.local is not None
    assert version.startswith("0.1.0.dev1+g")


def test_bootstrap_pretend_version_marks_dirty_repo(tmp_path: Path) -> None:
    repo_root = _init_repo(tmp_path)
    (repo_root / "tracked.txt").write_text("hello\ndirty\n", encoding="utf-8")

    version = bootstrap_pretend_version(repo_root)

    assert Version(version).local is not None
    assert ".d" in version


def test_build_environment_overrides_only_apply_before_first_tag(tmp_path: Path) -> None:
    repo_root = _init_repo(tmp_path)

    overrides = build_environment_overrides(repo_root)
    assert "SETUPTOOLS_SCM_PRETEND_VERSION" in overrides
    assert repository_has_version_tags(repo_root) is False

    _git(repo_root, "tag", "v1.2.3")

    assert repository_has_version_tags(repo_root) is True
    assert build_environment_overrides(repo_root) == {}


def test_build_wheel_script_runs_from_plain_repo_checkout(repo_root: Path) -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    completed = subprocess.run(
        [sys.executable, "scripts/build_wheel.py", "--help"],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "Build the project wheel with SCM-derived versioning." in completed.stdout


def test_clean_build_artifacts_removes_build_and_dist(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    build_dir = repo_root / "build"
    dist_dir = repo_root / "dist"
    build_dir.mkdir(parents=True)
    dist_dir.mkdir(parents=True)
    (build_dir / "artifact.txt").write_text("build", encoding="utf-8")
    (dist_dir / "artifact.whl").write_text("dist", encoding="utf-8")

    clean_build_artifacts(repo_root)

    assert build_dir.exists() is False
    assert dist_dir.exists() is False


def test_discover_built_wheel_reads_project_name_from_pyproject(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    dist_dir = repo_root / "dist"
    dist_dir.mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "databricks-mcp-agent-hello-world"',
            ]
        ),
        encoding="utf-8",
    )
    wheel_path = dist_dir / "databricks_mcp_agent_hello_world-1.2.3-py3-none-any.whl"
    wheel_path.write_text("wheel", encoding="utf-8")

    assert discover_built_wheel(repo_root) == wheel_path


def test_build_wheel_cleans_and_discovers_artifact(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    expected_wheel = repo_root / "dist" / "artifact.whl"
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.devtools.wheel_build.clean_build_artifacts",
        lambda root: calls.append(("clean", root)),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.devtools.wheel_build.build_environment_overrides",
        lambda root: {"SETUPTOOLS_SCM_PRETEND_VERSION": "0.1.0.dev9+gabc"},
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.devtools.wheel_build.read_project_name",
        lambda path: "databricks-mcp-agent-hello-world",
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.devtools.wheel_build.discover_built_wheel",
        lambda root, *, project_name=None: expected_wheel,
    )

    def _fake_run(command: list[str], *, cwd: Path, env: dict[str, str], check: bool) -> None:
        calls.append(("run", command))
        assert cwd == repo_root
        assert check is True
        assert env["SETUPTOOLS_SCM_PRETEND_VERSION"] == "0.1.0.dev9+gabc"
        assert "--no-isolation" in command

    monkeypatch.setattr("subprocess.run", _fake_run)

    result = build_wheel(repo_root, python_executable="python-custom")

    assert calls[0] == ("clean", repo_root)
    assert calls[1] == ("run", ["python-custom", "-m", "build", "--wheel", "--no-isolation"])
    assert result.wheel_path == expected_wheel
    assert result.pretend_version == "0.1.0.dev9+gabc"


def test_build_wheel_can_skip_clean_and_build_without_no_isolation(
    monkeypatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "repo"
    expected_wheel = repo_root / "dist" / "artifact.whl"
    called = {"clean": False}

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.devtools.wheel_build.clean_build_artifacts",
        lambda root: called.__setitem__("clean", True),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.devtools.wheel_build.build_environment_overrides",
        lambda root: {},
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.devtools.wheel_build.read_project_name",
        lambda path: "databricks-mcp-agent-hello-world",
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.devtools.wheel_build.discover_built_wheel",
        lambda root, *, project_name=None: expected_wheel,
    )

    def _fake_run(command: list[str], *, cwd: Path, env: dict[str, str], check: bool) -> None:
        assert cwd == repo_root
        assert check is True
        assert command == ["python-alt", "-m", "build", "--wheel"]
        assert "SETUPTOOLS_SCM_PRETEND_VERSION" not in env

    monkeypatch.setattr("subprocess.run", _fake_run)

    result = build_wheel(
        repo_root,
        python_executable="python-alt",
        clean=False,
        no_isolation=False,
    )

    assert called["clean"] is False
    assert result.wheel_path == expected_wheel
    assert result.pretend_version is None
