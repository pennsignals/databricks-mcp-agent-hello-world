import json
from pathlib import Path


def test_demo_task_files_match_expected_contract() -> None:
    compile_task = json.loads(Path("examples/demo_compile_task.json").read_text(encoding="utf-8"))
    run_task = json.loads(Path("examples/demo_run_task.json").read_text(encoding="utf-8"))

    expected_fields = [
        "display_name",
        "setup_recommendation",
        "runtime_target",
        "recent_operational_note",
    ]

    assert compile_task["task_name"] == "workspace_onboarding_brief"
    assert run_task["task_name"] == "workspace_onboarding_brief"
    assert compile_task["payload"]["required_fields"] == expected_fields
    assert run_task["payload"]["required_fields"] == expected_fields
    assert compile_task["payload"]["allow_mutations"] is False
    assert run_task["payload"]["allow_mutations"] is False
