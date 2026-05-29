from __future__ import annotations

import json
from pathlib import Path

from databricks_mcp_agent_hello_world.config import ALLOWED_LOCAL_DOTENV_KEYS, load_settings
from databricks_mcp_agent_hello_world.evals.harness import load_eval_scenarios

DOC_FILES = [
    "README.md",
    "src/databricks_mcp_agent_hello_world/app/README.md",
    "docs/ARCHITECTURE.md",
    "docs/CONVERT_TEMPLATE_TO_REAL_APP.md",
    "AGENTS.md",
    "docs/CD_DEPLOYMENT.md",
    ".env.example",
    "pyproject.toml",
    "workspace-config.example.yml",
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


def test_docs_describe_current_template_concepts(repo_root: Path) -> None:
    text = "\n".join((repo_root / path).read_text(encoding="utf-8") for path in DOC_FILES)

    for expected in [
        "customer_account_brief",
        "lookup_customer",
        "create_support_ticket",
        "examples/demo_run_task.json",
        "evals/sample_scenarios.json",
    ]:
        assert expected in text


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

    assert "Eval summary reports" in text
    assert "`storage.local_data_dir`" in text
    assert "configured storage route" in text


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


def test_sample_evals_omit_allow_mutations(repo_root: Path) -> None:
    scenarios = json.loads((repo_root / "evals" / "sample_scenarios.json").read_text())

    for scenario in scenarios:
        serialized_scenario = json.dumps(scenario)
        assert "allow_mutations" not in serialized_scenario


def test_docs_explain_two_tool_demo_and_mutation_contract(repo_root: Path) -> None:
    combined_docs = "\n".join(
        (repo_root / path).read_text(encoding="utf-8")
        for path in [
            "README.md",
            "docs/CONVERT_TEMPLATE_TO_REAL_APP.md",
            "src/databricks_mcp_agent_hello_world/app/README.md",
        ]
    )

    for token in [
        "lookup_customer",
        "create_support_ticket",
        "tool sub-selection",
        "runtime safety gate",
    ]:
        assert token in combined_docs


def test_conversion_guide_mentions_canonical_customization_files(repo_root: Path) -> None:
    text = (repo_root / "docs" / "CONVERT_TEMPLATE_TO_REAL_APP.md").read_text(encoding="utf-8")

    for expected_path in [
        "app/tools.py",
        "app/registry.py",
        "examples/demo_run_task.json",
        "evals/sample_scenarios.json",
    ]:
        assert expected_path in text

    for deployment_token in [
        "databricks.yml",
        "resources/jobs.yml",
        "shared-workspace deployment",
    ]:
        assert deployment_token in text


def test_readme_links_to_customization_guides(repo_root: Path) -> None:
    readme = (repo_root / "README.md").read_text(encoding="utf-8")

    assert "[Convert the template into a real app](docs/CONVERT_TEMPLATE_TO_REAL_APP.md)" in readme
    assert "[app customization guide](src/databricks_mcp_agent_hello_world/app/README.md)" in readme


def test_conversion_guide_says_package_renaming_is_optional(repo_root: Path) -> None:
    text = (repo_root / "docs" / "CONVERT_TEMPLATE_TO_REAL_APP.md").read_text(encoding="utf-8")
    normalized_text = " ".join(text.split()).lower()

    assert "do not rename python package/import paths by default" in normalized_text
    assert "package renaming is optional" in normalized_text


def test_conversion_guide_includes_config_customization_table(repo_root: Path) -> None:
    text = (repo_root / "docs" / "CONVERT_TEMPLATE_TO_REAL_APP.md").read_text(encoding="utf-8")

    assert "| Need | File | What to change |" in text
    for expected in [
        "Serving endpoint",
        "`llm_endpoint_name`",
        "Workspace/auth",
        "`workspace_host`, `databricks_config_profile`",
        "Local tools",
        "`app/tools.py`, `app/registry.py`",
        "MCP tools",
        "`tools.databricks_mcp` settings",
        "Local event files",
        "`storage.local_data_dir`",
        "Table persistence",
        "`storage.agent_events_table`",
        "Bundle identity",
        "Job identity",
    ]:
        assert expected in text


def test_app_readme_points_to_primary_edit_files(repo_root: Path) -> None:
    text = (repo_root / "src" / "databricks_mcp_agent_hello_world" / "app" / "README.md").read_text(
        encoding="utf-8"
    )

    for expected in [
        "`tools.py`",
        "`registry.py`",
        "examples/demo_run_task.json",
        "evals/sample_scenarios.json",
    ]:
        assert expected in text
