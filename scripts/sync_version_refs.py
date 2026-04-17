from __future__ import annotations

import argparse
import sys

from databricks_mcp_agent_hello_world.devtools.version_sync import (
    format_sync_result,
    sync_version_refs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync version-derived wheel references.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if versioned wheel references are stale.",
    )
    args = parser.parse_args(argv)

    try:
        result = sync_version_refs(check=args.check)
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1

    print(format_sync_result(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
