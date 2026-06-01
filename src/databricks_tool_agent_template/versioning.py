from __future__ import annotations

import re
import tomllib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
BOOTSTRAP_BASE_VERSION = "0.1.0"
BUNDLE_WHEEL_GLOB_TEMPLATE = "../dist/{distribution}-*.whl"


def read_pyproject_metadata(pyproject_path: Path = PYPROJECT_PATH) -> dict[str, object]:
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    return pyproject["project"]


def read_project_name(pyproject_path: Path = PYPROJECT_PATH) -> str:
    return str(read_pyproject_metadata(pyproject_path)["name"])


def distribution_name_for_wheel(project_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9.]+", "_", project_name)


def bundle_wheel_glob(project_name: str) -> str:
    distribution_name = distribution_name_for_wheel(project_name)
    return BUNDLE_WHEEL_GLOB_TEMPLATE.format(distribution=distribution_name)


def read_installed_package_version(
    distribution_name: str,
    *,
    fallback: str = "0+unknown",
) -> str:
    try:
        return installed_version(distribution_name)
    except PackageNotFoundError:
        return fallback
