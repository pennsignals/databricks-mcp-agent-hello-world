from __future__ import annotations

import shutil
from pathlib import Path

import nox

PYTHON = "3.12"
REPO_ROOT = Path(__file__).resolve().parent
NOX_DEV_REQUIREMENTS = (
    "build>=1.2.0",
    "coverage[toml]>=7.13.5",
    "editables>=0.5",
    "hatchling>=1.27.0",
    "hatch-vcs>=0.5.0",
    "pytest>=8.3.0",
    "pytest-cov>=7.1.0",
    "ruff>=0.8.0",
)
NOX_BUILD_REQUIREMENTS = (
    "build>=1.2.0",
    "hatchling>=1.27.0",
    "hatch-vcs>=0.5.0",
)

nox.options.default_venv_backend = "venv"
nox.options.error_on_missing_interpreters = True
nox.options.reuse_existing_virtualenvs = True


def _install_tool_requirements(session: nox.Session, *requirements: str) -> None:
    session.install(*requirements)


def _install_project_editable(session: nox.Session) -> None:
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
    _install_tool_requirements(session, *NOX_DEV_REQUIREMENTS)
    _install_project_editable(session)

    if _is_fix_mode(session):
        session.run("ruff", "format", ".")
        session.run("ruff", "check", ".", "--fix")
        return

    session.run("ruff", "check", ".")
    session.run("ruff", "format", ".", "--check")


@nox.session(python=PYTHON)
def tests(session: nox.Session) -> None:
    """Run unit and contract tests with coverage."""
    _install_tool_requirements(session, *NOX_DEV_REQUIREMENTS)
    _install_project_editable(session)
    session.run("pytest")


@nox.session(python=PYTHON)
def build_wheel(session: nox.Session) -> None:
    """Build the wheel after cleaning local build artifacts."""
    _install_tool_requirements(session, *NOX_BUILD_REQUIREMENTS)
    shutil.rmtree(REPO_ROOT / "build", ignore_errors=True)
    shutil.rmtree(REPO_ROOT / "dist", ignore_errors=True)
    session.run("python", "scripts/build_wheel.py")


def _run_validation_flow(session: nox.Session, *, check_only: bool) -> None:
    mode_arg = "--check" if check_only else "--fix"

    for name in ("lint", "tests", "build_wheel"):
        session.notify(name, posargs=[mode_arg])


@nox.session(python=PYTHON)
def precommit(session: nox.Session) -> None:
    """Canonical local validation flow with safe auto-fix behavior."""
    _run_validation_flow(session, check_only=False)


@nox.session(python=PYTHON)
def ci(session: nox.Session) -> None:
    """Canonical CI validation flow in check-only mode."""
    _run_validation_flow(session, check_only=True)
