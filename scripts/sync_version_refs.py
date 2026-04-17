from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _ensure_repo_src_on_sys_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    src_path_str = str(src_path)
    if src_path_str not in sys.path:
        sys.path.insert(0, src_path_str)


def _load_version_sync_helpers():
    _ensure_repo_src_on_sys_path()

    from databricks_mcp_agent_hello_world.devtools.version_sync import (
        format_sync_result,
        sync_version_refs,
    )

    return format_sync_result, sync_version_refs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync version-derived wheel references.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if versioned wheel references are stale.",
    )
    args = parser.parse_args(argv)
    format_sync_result, sync_version_refs = _load_version_sync_helpers()

    try:
        result = sync_version_refs(check=args.check)
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1

    print(format_sync_result(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
