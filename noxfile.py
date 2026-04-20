from __future__ import annotations

import shutil
from pathlib import Path

import nox

PYTHON = "3.11"
REPO_ROOT = Path(__file__).resolve().parent
BUILD_ARTIFACT_DIRS = (REPO_ROOT / "build", REPO_ROOT / "dist")
NOX_TOOL_REQUIREMENTS = (
    "build>=1.2.0",
    "coverage[toml]>=7.13.5",
    "editables>=0.5",
    "hatchling>=1.27.0",
    "pytest>=8.3.0",
    "pytest-cov>=7.1.0",
    "ruff>=0.8.0",
)

nox.options.default_venv_backend = "venv"
nox.options.error_on_missing_interpreters = True
nox.options.reuse_existing_virtualenvs = True


def _install_dev_dependencies(session: nox.Session) -> None:
    session.install(*NOX_TOOL_REQUIREMENTS)
    session.install("--no-build-isolation", "-e", ".")


def _is_fix_mode(session: nox.Session) -> bool:
    if "--fix" in session.posargs:
        return True
    if "--check" in session.posargs:
        return False
    return session.name == "precommit"


@nox.session(python=PYTHON)
def lint(session: nox.Session) -> None:
    """Run Ruff in fix or check mode."""
    _install_dev_dependencies(session)

    if _is_fix_mode(session):
        session.run("ruff", "format", ".")
        session.run("ruff", "check", ".", "--fix")
        return

    session.run("ruff", "check", ".")
    session.run("ruff", "format", ".", "--check")


@nox.session(python=PYTHON)
def tests(session: nox.Session) -> None:
    """Run unit and contract tests with coverage."""
    _install_dev_dependencies(session)
    session.run("pytest")


@nox.session(python=PYTHON)
def version_refs(session: nox.Session) -> None:
    """Sync or verify version-derived Databricks wheel references."""
    _install_dev_dependencies(session)

    command = ["python", "scripts/sync_version_refs.py"]
    if not _is_fix_mode(session):
        command.append("--check")
    session.run(*command)


@nox.session(python=PYTHON)
def build_wheel(session: nox.Session) -> None:
    """Build the wheel after cleaning local build artifacts."""
    _install_dev_dependencies(session)

    for path in BUILD_ARTIFACT_DIRS:
        shutil.rmtree(path, ignore_errors=True)

    session.run("python", "-m", "build", "--wheel", "--no-isolation")


def _run_validation_flow(session: nox.Session, *, check_only: bool) -> None:
    mode_arg = "--check" if check_only else "--fix"

    for name in ("lint", "version_refs", "tests", "build_wheel"):
        session.notify(name, posargs=[mode_arg])


@nox.session(python=PYTHON)
def precommit(session: nox.Session) -> None:
    """Canonical local validation flow with safe auto-fix behavior."""
    _run_validation_flow(session, check_only=False)


@nox.session(python=PYTHON)
def ci(session: nox.Session) -> None:
    """Canonical CI validation flow in check-only mode."""
    _run_validation_flow(session, check_only=True)
