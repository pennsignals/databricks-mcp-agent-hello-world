from __future__ import annotations

import argparse
import keyword
import re
from pathlib import Path

TEMPLATE_PACKAGE = "databricks_tool_agent_template"
TEMPLATE_DISTRIBUTION = "databricks_tool_agent_template"

REPO_ROOT = Path(__file__).resolve().parents[1]

TEXT_EXTENSIONS = {
    ".py",
    ".toml",
    ".yml",
    ".yaml",
    ".md",
    ".json",
    ".txt",
    ".cfg",
    ".ini",
    ".sh",
}
SKIPPED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "dist",
    "build",
    ".nox",
}
# These files intentionally keep the original template tokens so the
# customization script remains testable after a downstream rename.
SKIPPED_FILES = {
    Path("scripts/customize_template.py"),
    Path("tests/unit/test_customize_template.py"),
}
PACKAGE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Customize the Databricks tool agent template package name."
    )
    parser.add_argument("package_name", help="lowercase snake_case Python package name")
    return parser


def validate_package_name(package_name: str) -> None:
    if not PACKAGE_NAME_RE.fullmatch(package_name) or keyword.iskeyword(package_name):
        raise ValueError(
            "Name must be a lowercase Python identifier, start with a letter, "
            "use underscores instead of dashes, and not be a Python keyword."
        )


def iter_text_files(repo_root: Path = REPO_ROOT) -> list[Path]:
    text_files: list[Path] = []

    for path in repo_root.rglob("*"):
        relative_path = path.relative_to(repo_root)
        if any(part in SKIPPED_DIRS for part in relative_path.parts):
            continue
        if relative_path in SKIPPED_FILES:
            continue
        if not path.is_file() or path.suffix not in TEXT_EXTENSIONS:
            continue
        text_files.append(path)

    return text_files


def replace_text_in_repo(old: str, new: str, repo_root: Path = REPO_ROOT) -> None:
    for path in iter_text_files(repo_root):
        text = path.read_text(encoding="utf-8")
        updated = text.replace(old, new)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def rename_package_dir(package_name: str, repo_root: Path = REPO_ROOT) -> None:
    source = repo_root / "src" / TEMPLATE_PACKAGE
    target = repo_root / "src" / package_name

    if not source.is_dir():
        raise FileNotFoundError(f"Template source package directory does not exist: {source}")
    if target.exists():
        raise FileExistsError(f"Target package directory already exists: {target}")

    source.rename(target)


def validate_filesystem_preconditions(package_name: str, repo_root: Path = REPO_ROOT) -> None:
    source = repo_root / "src" / TEMPLATE_PACKAGE
    target = repo_root / "src" / package_name

    if not source.is_dir():
        raise FileNotFoundError(f"Template source package directory does not exist: {source}")
    if target.exists():
        raise FileExistsError(f"Target package directory already exists: {target}")


def main(argv: list[str] | None = None, repo_root: Path = REPO_ROOT) -> int:
    parser = build_parser()
    package_name = parser.parse_args(argv).package_name
    try:
        validate_package_name(package_name)
    except ValueError as error:
        parser.error(str(error))

    distribution_name = package_name
    try:
        validate_filesystem_preconditions(package_name, repo_root)
    except (FileExistsError, FileNotFoundError) as error:
        parser.error(str(error))

    replace_text_in_repo(TEMPLATE_PACKAGE, package_name, repo_root)
    replace_text_in_repo(TEMPLATE_DISTRIBUTION, distribution_name, repo_root)
    rename_package_dir(package_name, repo_root)

    print(f"repo/project/distribution/package/import/bundle/job prefix: {package_name}")
    print(f"Customized template for package {package_name!r}.")
    print('Next: run `python -m pip install -e ".[dev]"` then `python -m pytest`.')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
