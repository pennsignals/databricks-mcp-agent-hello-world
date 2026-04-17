from __future__ import annotations

import re
import tomllib
from importlib.metadata import PackageNotFoundError, version as installed_version
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
BUNDLE_WHEEL_PREFIX = "${workspace.root_path}/artifacts/.internal/"
WHEEL_TAG_SUFFIX = "-py3-none-any.whl"
WHEEL_PATH_PATTERN_TEMPLATE = (
    r"(?P<prefix>\$\{{workspace\.root_path\}}/artifacts/\.internal/)"
    r"(?P<filename>{distribution}-[^/\s]+-py3-none-any\.whl)"
)


def read_pyproject_metadata(pyproject_path: Path = PYPROJECT_PATH) -> dict[str, str]:
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = pyproject["project"]
    return {
        "name": project["name"],
        "version": project["version"],
    }


def read_project_version(pyproject_path: Path = PYPROJECT_PATH) -> str:
    return read_pyproject_metadata(pyproject_path)["version"]


def read_project_name(pyproject_path: Path = PYPROJECT_PATH) -> str:
    return read_pyproject_metadata(pyproject_path)["name"]


def distribution_name_for_wheel(project_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9.]+", "_", project_name)


def expected_wheel_filename(version: str, project_name: str) -> str:
    distribution_name = distribution_name_for_wheel(project_name)
    return f"{distribution_name}-{version}{WHEEL_TAG_SUFFIX}"


def expected_bundle_wheel_path(version: str, project_name: str) -> str:
    return f"{BUNDLE_WHEEL_PREFIX}{expected_wheel_filename(version, project_name)}"


def read_installed_package_version(
    distribution_name: str,
    *,
    fallback: str = "0+unknown",
) -> str:
    try:
        return installed_version(distribution_name)
    except PackageNotFoundError:
        return fallback


def sync_wheel_paths_in_text(contents: str, *, expected_path: str, project_name: str) -> tuple[str, int]:
    distribution_name = distribution_name_for_wheel(project_name)
    pattern = re.compile(
        WHEEL_PATH_PATTERN_TEMPLATE.format(distribution=re.escape(distribution_name))
    )
    updated_contents, replacements = pattern.subn(expected_path, contents)
    if replacements == 0:
        raise ValueError(
            f"Did not find any bundle wheel path for distribution {distribution_name!r}."
        )
    return updated_contents, replacements
