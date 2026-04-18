import json
from pathlib import Path

import yaml


def test_demo_run_task_matches_expected_contract() -> None:
    run_task = json.loads(Path("examples/demo_run_task.json").read_text(encoding="utf-8"))

    expected_fields = [
        "display_name",
        "setup_recommendation",
        "runtime_target",
        "recent_operational_note",
    ]

    assert run_task["task_name"] == "workspace_onboarding_brief"
    assert run_task["payload"]["required_fields"] == expected_fields
    assert run_task["payload"]["allow_mutations"] is False


def test_sample_scenarios_reference_canonical_demo_task_file() -> None:
    scenarios = json.loads(Path("evals/sample_scenarios.json").read_text(encoding="utf-8"))

    assert scenarios[0]["task_input_file"] == "../examples/demo_run_task.json"
    assert "task_input" not in scenarios[0]


def test_databricks_bundle_uses_minimal_placeholder_task_input() -> None:
    bundle = yaml.safe_load(Path("databricks.yml").read_text(encoding="utf-8"))
    task_input_json = bundle["variables"]["task_input_json"]
    expected_description = (
        "JSON string containing task-specific input. "
        "See examples/demo_run_task.json for the canonical sample task."
    )
    expected_default = (
        '{"task_name":"replace_me","instructions":"See examples/demo_run_task.json '
        'for the canonical sample task.","payload":{}}'
    )

    assert task_input_json["description"] == expected_description
    assert task_input_json["default"] == expected_default
