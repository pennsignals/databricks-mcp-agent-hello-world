from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSIONING_PATH = (
    REPO_ROOT / "src" / "databricks_mcp_agent_hello_world" / "versioning.py"
)
BUNDLE_RESOURCE_PATH = REPO_ROOT / "resources" / "databricks_mcp_agent_hello_world_job.yml"


def _load_versioning_module():
    spec = importlib.util.spec_from_file_location("project_versioning", VERSIONING_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load versioning helper from {VERSIONING_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync version-derived wheel references.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if versioned wheel references are stale.",
    )
    args = parser.parse_args(argv)
    versioning = _load_versioning_module()

    try:
        version = versioning.read_project_version()
        project_name = versioning.read_project_name()
        expected_path = versioning.expected_bundle_wheel_path(version, project_name)
        original = BUNDLE_RESOURCE_PATH.read_text(encoding="utf-8")
        updated, replacements = versioning.sync_wheel_paths_in_text(
            original,
            expected_path=expected_path,
            project_name=project_name,
        )
        changed = updated != original
        if args.check and changed:
            raise RuntimeError(
                "Version references are stale. "
                f"Run python scripts/sync_version_refs.py to update {BUNDLE_RESOURCE_PATH}."
            )
        if changed:
            BUNDLE_RESOURCE_PATH.write_text(updated, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1

    if changed:
        print(f"Updated bundle wheel path(s) to version {version}")
    else:
        print("No version reference changes needed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
