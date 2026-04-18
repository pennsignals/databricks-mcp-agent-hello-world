from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from databricks_mcp_agent_hello_world.versioning import (
    expected_bundle_wheel_path,
    read_project_name,
    read_project_version,
    sync_wheel_paths_in_text,
)

BUNDLE_RESOURCE_PATH = Path("resources/jobs.yml")


@dataclass(frozen=True)
class SyncResult:
    changed: bool
    replacements: int
    version: str
    bundle_resource_path: Path


def sync_version_refs(
    *,
    check: bool = False,
    bundle_resource_path: Path = BUNDLE_RESOURCE_PATH,
) -> SyncResult:
    version = read_project_version()
    project_name = read_project_name()
    expected_path = expected_bundle_wheel_path(version, project_name)
    original = bundle_resource_path.read_text(encoding="utf-8")
    try:
        updated, replacements = sync_wheel_paths_in_text(
            original,
            expected_path=expected_path,
            project_name=project_name,
        )
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    changed = updated != original

    if check and changed:
        raise RuntimeError(
            "Version references are stale. "
            f"Run python scripts/sync_version_refs.py to update {bundle_resource_path}."
        )

    if changed:
        bundle_resource_path.write_text(updated, encoding="utf-8")

    return SyncResult(
        changed=changed,
        replacements=replacements,
        version=version,
        bundle_resource_path=bundle_resource_path,
    )


def format_sync_result(result: SyncResult) -> str:
    if result.changed:
        return f"Updated bundle wheel path(s) to version {result.version}"
    return "No version reference changes needed"
