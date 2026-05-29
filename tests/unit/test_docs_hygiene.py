from __future__ import annotations

import re
from pathlib import Path

CORE_DOC_RELATIVE_PATHS = [
    "README.md",
    "AGENTS.md",
    "src/databricks_mcp_agent_hello_world/app/README.md",
]

LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _doc_files(repo_root: Path) -> list[Path]:
    return [
        *(repo_root / path for path in CORE_DOC_RELATIVE_PATHS),
        *sorted((repo_root / "docs").glob("*.md")),
    ]


def _repo_local_target(path: str) -> str | None:
    target = path.strip()
    if not target or target.startswith(("http://", "https://", "mailto:", "#")):
        return None

    target_without_anchor = target.split("#", 1)[0]
    if target_without_anchor.startswith(".local_state"):
        return None

    return target_without_anchor


def test_repo_local_markdown_links_resolve(repo_root: Path) -> None:
    missing: list[str] = []

    for absolute_doc_path in _doc_files(repo_root):
        text = absolute_doc_path.read_text(encoding="utf-8")
        for raw_target in LINK_RE.findall(text):
            target = _repo_local_target(raw_target)
            if target is None:
                continue

            resolved = (absolute_doc_path.parent / target).resolve()
            if not resolved.exists():
                doc_path = absolute_doc_path.relative_to(repo_root)
                missing.append(f"{doc_path}: {raw_target}")

    assert not missing, "Broken repo-local markdown links:\n" + "\n".join(missing)


def test_conversion_guide_names_core_customization_files(repo_root: Path) -> None:
    text = (repo_root / "docs" / "CONVERT_TEMPLATE_TO_REAL_APP.md").read_text(encoding="utf-8")

    required = [
        "src/databricks_mcp_agent_hello_world/app/tools.py",
        "src/databricks_mcp_agent_hello_world/app/registry.py",
        "examples/demo_run_task.json",
        "evals/sample_scenarios.json",
    ]

    missing = [item for item in required if item not in text]
    assert not missing, f"Missing customization file references: {missing}"
