from __future__ import annotations

import json
from pathlib import Path

from databricks_mcp_agent_hello_world.config import ALLOWED_LOCAL_DOTENV_KEYS, load_settings
from databricks_mcp_agent_hello_world.evals.harness import load_eval_scenarios

DOC_FILES = [
    "README.md",
    "docs/ARCHITECTURE.md",
    "docs/CONVERT_TEMPLATE_TO_REAL_APP.md",
    "AGENTS.md",
    "docs/CD_DEPLOYMENT.md",
    ".env.example",
    "pyproject.toml",
    "workspace-config.example.yml",
]

REMOVED_TERMS = [
    "managed_mcp",
    "tool_provider_type",
    "provider_type",
    "databricks_cli_profile",
    "auth_mode",
    "local_tool_backend_mode",
    "compile-tool-profile",
    "future MCP",
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
    "forbidden_executed_tools",
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


def test_docs_document_local_eval_report_output(repo_root: Path) -> None:
    text = "\n".join(
        (repo_root / path).read_text(encoding="utf-8")
        for path in [
            "README.md",
            "docs/ARCHITECTURE.md",
            "docs/CONVERT_TEMPLATE_TO_REAL_APP.md",
        ]
    )

    assert "Eval summary reports are written locally under `storage.local_data_dir`" in text
    assert "agent execution events still follow the configured storage route" in text


def test_docs_links_exist(repo_root: Path) -> None:
    assert (repo_root / "docs" / "CD_DEPLOYMENT.md").exists()
    assert "[CD deployment](docs/CD_DEPLOYMENT.md)" in (repo_root / "README.md").read_text(
        encoding="utf-8"
    )


def test_env_example_uses_supported_keys(repo_root: Path) -> None:
    env_path = repo_root / ".env.example"
    keys = {
        line.removeprefix("# ").split("=", 1)[0]
        for line in env_path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("# Copy") and "=" in line
    }
    active_keys = {
        line.split("=", 1)[0]
        for line in env_path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    }

    assert keys == ALLOWED_LOCAL_DOTENV_KEYS
    assert active_keys <= ALLOWED_LOCAL_DOTENV_KEYS


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


def test_default_sample_eval_forbids_write_like_tool(repo_root: Path) -> None:
    scenarios = json.loads((repo_root / "evals" / "sample_scenarios.json").read_text())
    scenarios_by_id = {scenario["scenario_id"]: scenario for scenario in scenarios}

    default_demo = scenarios_by_id["customer_brief_selects_lookup_customer"]

    assert "Default customer brief task" in default_demo["description"]
    assert default_demo["task_input_file"] == "../examples/demo_run_task.json"
    assert default_demo["required_executed_tools"] == ["lookup_customer"]
    assert default_demo["forbidden_executed_tools"] == ["create_support_ticket"]


def test_explicit_ticket_sample_eval_expects_write_like_tool(repo_root: Path) -> None:
    scenarios = json.loads((repo_root / "evals" / "sample_scenarios.json").read_text())
    scenarios_by_id = {scenario["scenario_id"]: scenario for scenario in scenarios}

    ticket_demo = scenarios_by_id["explicit_ticket_request_selects_create_support_ticket"]

    assert "Explicit support-ticket task" in ticket_demo["description"]
    assert "should use create_support_ticket" in ticket_demo["description"]
    assert ticket_demo["required_executed_tools"] == ["create_support_ticket"]


def test_default_demo_task_omits_allow_mutations(repo_root: Path) -> None:
    task_input = json.loads((repo_root / "examples" / "demo_run_task.json").read_text())
    task_instructions = task_input["instructions"].lower()

    assert "allow_mutations" not in task_input["payload"]
    assert "instructions" not in task_input["payload"]
    assert "read-only" in task_instructions
    assert "support ticket" in task_instructions


def test_docs_explain_two_tool_demo_and_mutation_contract(repo_root: Path) -> None:
    for path in ["README.md", "docs/CONVERT_TEMPLATE_TO_REAL_APP.md"]:
        text = (repo_root / path).read_text(encoding="utf-8")

        assert "### Why are there two demo tools?" in text
        assert "`lookup_customer`: relevant to the default customer brief task" in text
        assert "only `lookup_customer` is selected for the default customer brief task" in text
        assert "prompt context used to demonstrate LLM behavior" in text
        assert "does not implement a generic mutation-safety policy" in text
