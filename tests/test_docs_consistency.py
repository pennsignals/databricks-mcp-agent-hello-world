from __future__ import annotations

import re
from pathlib import Path


README_PATH = Path("README.md")
ARCHITECTURE_PATH = Path("docs/ARCHITECTURE.md")
CONVERSION_PATH = Path("docs/CONVERT_TEMPLATE_TO_REAL_APP.md")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_required_docs_exist() -> None:
    assert README_PATH.exists()
    assert ARCHITECTURE_PATH.exists()
    assert CONVERSION_PATH.exists()


def test_readme_contains_required_headings_and_llm_driven_rule() -> None:
    content = _read(README_PATH)

    required_headings = [
        "## How it works",
        "## Prerequisites",
        "## Required edits before your first run",
        "## What you should customize vs keep",
        "## Deploying to Databricks",
    ]

    for heading in required_headings:
        assert heading in content

    assert "Tool selection is **LLM-driven**" in content
    assert "the full discovered tool set" in content
    assert "The LLM decides which tools to call" in content


def test_architecture_doc_mentions_filter_tools_and_no_hard_coded_allowlist() -> None:
    content = _read(ARCHITECTURE_PATH)

    assert "There is no compile step." in content
    assert "There is no deterministic prefilter layer." in content


def test_conversion_guide_contains_all_steps_and_manual_allowlist_warning() -> None:
    content = _read(CONVERSION_PATH)

    required_headings = [
        "## Step 1 — Rename the demo task family",
        "## Step 2 — Replace the demo tools",
        "## Step 3 — Replace the runtime task file",
        "## Step 4 — Update prompts only if needed",
        "## Step 5 — Replace eval scenarios",
        "## Step 6 — Rename deployment resources",
        "## Step 7 — Verify the full workflow",
    ]

    for heading in required_headings:
        assert heading in content

    assert "Do not replace LLM-driven tool selection with a manual allowlist." in content


def test_docs_reference_existing_project_paths() -> None:
    expected_paths = [
        "docs/ARCHITECTURE.md",
        "docs/CONVERT_TEMPLATE_TO_REAL_APP.md",
        "examples/demo_run_task.json",
        "evals/sample_scenarios.json",
        "databricks.yml",
        "workspace-config.example.yml",
        "resources/databricks_mcp_agent_hello_world_job.yml",
        "src/databricks_mcp_agent_hello_world/runner/agent_runner.py",
        "src/databricks_mcp_agent_hello_world/storage/result_writer.py",
        "src/databricks_mcp_agent_hello_world/storage/result_repository.py",
        "src/databricks_mcp_agent_hello_world/evals/harness.py",
        "src/databricks_mcp_agent_hello_world/models.py",
        "src/databricks_mcp_agent_hello_world/config.py",
        "src/databricks_mcp_agent_hello_world/demo/tools.py",
        "src/databricks_mcp_agent_hello_world/tools/registry.py",
        "src/databricks_mcp_agent_hello_world/prompts/agent_system_prompt.txt",
    ]

    combined_docs = "\n".join(
        [
            _read(README_PATH),
            _read(ARCHITECTURE_PATH),
            _read(CONVERSION_PATH),
        ]
    )

    for relative_path in expected_paths:
        assert relative_path in combined_docs
        assert Path(relative_path).exists()


def test_docs_do_not_present_removed_manual_allowlist_pattern_as_supported() -> None:
    combined_docs = "\n".join(
        [
            _read(README_PATH),
            _read(ARCHITECTURE_PATH),
            _read(CONVERSION_PATH),
        ]
    )
    combined_docs_lower = combined_docs.lower()

    assert "out of scope for this template" in combined_docs
    assert "hello-world allowlist" not in combined_docs_lower
    assert "manual allowlist is the supported pattern" not in combined_docs_lower
    assert "compile-tool-profile" not in combined_docs_lower


def test_docs_do_not_use_machine_specific_absolute_paths() -> None:
    combined_docs = "\n".join(
        [
            _read(README_PATH),
            _read(ARCHITECTURE_PATH),
            _read(CONVERSION_PATH),
        ]
    )

    assert "/Users/" not in combined_docs
    assert "\\Users\\" not in combined_docs
    assert re.search(r"[A-Za-z]:\\\\", combined_docs) is None
