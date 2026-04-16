import json
from pathlib import Path


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
