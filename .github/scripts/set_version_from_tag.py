from __future__ import annotations

import re
import sys
from pathlib import Path

PYPROJECT = Path("pyproject.toml")
VERSION_LINE_RE = re.compile(r'(?m)^version = "[^"]+"$')
SEMVER_RE = re.compile(r"^v?(\d+\.\d+\.\d+(?:[-+][A-Za-z0-9._-]+)?)$")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        raise SystemExit("Usage: python .github/scripts/set_version_from_tag.py <tag>")

    match = SEMVER_RE.fullmatch(args[0].strip())
    if not match:
        raise SystemExit(f"Tag must look like v1.2.3 or 1.2.3, got: {args[0]!r}")

    version = match.group(1)
    original = PYPROJECT.read_text(encoding="utf-8")
    updated, replacements = VERSION_LINE_RE.subn(f'version = "{version}"', original, count=1)

    if replacements != 1:
        raise SystemExit("Failed to update version in pyproject.toml")

    PYPROJECT.write_text(updated, encoding="utf-8")
    print(f"Set pyproject.toml version to {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
