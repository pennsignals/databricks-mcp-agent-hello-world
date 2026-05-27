from __future__ import annotations

import json
from pathlib import Path

from databricks_mcp_agent_hello_world.config import load_settings
from databricks_mcp_agent_hello_world.evals.harness import load_eval_scenarios

DOC_FILES = [
    "README.md",
    "docs/ARCHITECTURE.md",
    "docs/CONVERT_TEMPLATE_TO_REAL_APP.md",
    "AGENTS.md",
    "workspace-config.example.yml",
]

REMOVED_TERMS = [
    "managed_mcp",
    "tool_provider_type",
    "provider_type",
    "databricks_cli_profile",
    "auth_mode",
    "local_tool_backend_mode",
    "storage.agent_runs_table",
    "storage.agent_output_table",
    "agent_runs_table",
    "agent_output_table",
    "deprecated",
    "legacy",
    "migration",
    "removed config keys",
]

CANONICAL_NOX_COMMANDS = [
    "python -m nox -s unit",
    "python -m nox -s contract",
    "python -m nox -s tests",
]

SUPPORTED_EVAL_ASSERTION_FIELDS = {
    "expected_status",
    "required_executed_tools",
    "required_output_substrings",
}


def test_docs_do_not_reference_removed_terms(repo_root: Path) -> None:
    text = "\n".join((repo_root / path).read_text(encoding="utf-8") for path in DOC_FILES)

    for term in REMOVED_TERMS:
        assert term not in text


def test_workspace_config_example_loads_as_valid_config(repo_root: Path) -> None:
    settings = load_settings(str(repo_root / "workspace-config.example.yml"))

    assert settings.llm_endpoint_name == "your-llm-endpoint-name"
    assert settings.tools.local_python.enabled is True
    assert settings.tools.databricks_mcp.enabled is False
    assert settings.storage.local_data_dir == "./.local_state"
    assert settings.storage.agent_events_table is None


def test_readme_contains_canonical_nox_commands(repo_root: Path) -> None:
    readme = (repo_root / "README.md").read_text(encoding="utf-8")

    for command in CANONICAL_NOX_COMMANDS:
        assert command in readme


def test_readme_does_not_claim_plain_pytest_is_unit_only(repo_root: Path) -> None:
    readme = (repo_root / "README.md").read_text(encoding="utf-8")

    assert "pytest means" not in readme
    assert "pytest is unit" not in readme
    assert "plain `pytest`" not in readme


def test_eval_docs_mention_only_supported_assertion_fields(repo_root: Path) -> None:
    text = "\n".join(
        (repo_root / path).read_text(encoding="utf-8")
        for path in [
            "README.md",
            "docs/ARCHITECTURE.md",
            "docs/CONVERT_TEMPLATE_TO_REAL_APP.md",
        ]
    )
    documented_fields = {field for field in SUPPORTED_EVAL_ASSERTION_FIELDS if f"`{field}`" in text}

    assert documented_fields == SUPPORTED_EVAL_ASSERTION_FIELDS
    assert "`expected_tools`" not in text
    assert "`required_tools`" not in text
    assert "`expected_output`" not in text
    assert "`output_substrings`" not in text


def test_sample_eval_scenarios_use_supported_assertions(repo_root: Path) -> None:
    scenario_path = repo_root / "evals" / "sample_scenarios.json"

    scenarios = json.loads(scenario_path.read_text(encoding="utf-8"))
    for scenario in scenarios:
        authored_assertion_fields = SUPPORTED_EVAL_ASSERTION_FIELDS.intersection(scenario)
        assert authored_assertion_fields
        assert set(scenario) <= {
            "scenario_id",
            "description",
            "task_input",
            "task_input_file",
            *SUPPORTED_EVAL_ASSERTION_FIELDS,
        }

    load_eval_scenarios(str(scenario_path))
