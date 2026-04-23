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


def _load_build_helpers():
    _ensure_repo_src_on_sys_path()

    from databricks_mcp_agent_hello_world.devtools.wheel_build import build_wheel

    return build_wheel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the project wheel with SCM-derived versioning."
    )
    parser.add_argument(
        "--isolation",
        action="store_true",
        help="Use build isolation instead of the active environment.",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Keep any existing build/ and dist/ contents before building.",
    )
    args = parser.parse_args(argv)
    build_wheel = _load_build_helpers()

    try:
        result = build_wheel(clean=not args.no_clean, no_isolation=not args.isolation)
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1

    if result.pretend_version:
        print(f"Built {result.wheel_path} using bootstrap version {result.pretend_version}")
    else:
        print(f"Built {result.wheel_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
