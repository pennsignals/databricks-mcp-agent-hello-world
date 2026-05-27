from __future__ import annotations

import re
from pathlib import Path

PACKAGE_ROOT = Path("src/databricks_mcp_agent_hello_world")
SHA_REF_PATTERN = re.compile(r"@[0-9a-f]{40}\b")
USES_REF_PATTERN = re.compile(
    r"^\s*uses:\s*(?P<action>[^@\s]+)@(?P<ref>\S+)\s*$",
    re.MULTILINE,
)
GITHUB_OWNED_ACTIONS = {
    "actions/checkout",
    "actions/setup-python",
    "actions/cache",
    "actions/upload-artifact",
}
THIRD_PARTY_ACTIONS_WITH_EXACT_RELEASE_TAGS = {
    "databricks/setup-cli",
}


def test_package_directories_have_init_files(repo_root: Path) -> None:
    package_root = repo_root / PACKAGE_ROOT

    for path in package_root.rglob("*"):
        if not path.is_dir() or path.name == "__pycache__":
            continue

        py_files = list(path.glob("*.py"))
        child_py_dirs = [
            child
            for child in path.iterdir()
            if child.is_dir() and child.name != "__pycache__" and any(child.glob("*.py"))
        ]
        if py_files or child_py_dirs:
            assert (path / "__init__.py").exists(), f"Missing {path}/__init__.py"


def test_github_actions_follow_repo_ref_policy(repo_root: Path) -> None:
    workflow_dir = repo_root / ".github" / "workflows"
    workflow_paths = [*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")]
    workflow_text = "\n".join(path.read_text(encoding="utf-8") for path in workflow_paths)

    assert SHA_REF_PATTERN.search(workflow_text) is None

    for match in USES_REF_PATTERN.finditer(workflow_text):
        action = match.group("action")
        ref = match.group("ref")

        if action.startswith("./"):
            continue

        if action in GITHUB_OWNED_ACTIONS:
            assert re.fullmatch(r"v\d+", ref), (
                f"{action} should use a readable floating major tag, got @{ref}"
            )
            continue

        if action in THIRD_PARTY_ACTIONS_WITH_EXACT_RELEASE_TAGS:
            assert re.fullmatch(r"v\d+\.\d+\.\d+", ref), (
                f"{action} should use an exact release tag, got @{ref}"
            )
            continue

        raise AssertionError(
            f"Unclassified GitHub Action {action}@{ref}. "
            "Classify it in test_repo_hygiene.py before using it."
        )
