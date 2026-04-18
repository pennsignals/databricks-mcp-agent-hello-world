from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"
DEMO_TASK_PATH = EXAMPLES_DIR / "demo_run_task.json"


def load_demo_task_input() -> dict[str, object]:
    return json.loads(DEMO_TASK_PATH.read_text(encoding="utf-8"))


def write_workspace_config(
    tmp_path: Path,
    *,
    extra_lines: list[str] | None = None,
    llm_endpoint_name: str = "endpoint-a",
    tool_provider_type: str = "local_python",
    include_databricks_profile: bool = True,
) -> Path:
    lines = [
        f"llm_endpoint_name: {llm_endpoint_name}",
        f"tool_provider_type: {tool_provider_type}",
        "databricks_config_profile: DEFAULT" if include_databricks_profile else None,
        "storage:",
        "  agent_events_table: main.agent.agent_events",
        "  local_data_dir: ./.local_state",
    ]
    if extra_lines:
        lines.extend(extra_lines)

    config_path = tmp_path / "workspace-config.yml"
    config_path.write_text("\n".join(line for line in lines if line is not None), encoding="utf-8")
    return config_path


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def demo_task_path() -> Path:
    return DEMO_TASK_PATH


@pytest.fixture
def demo_task_input() -> dict[str, object]:
    return load_demo_task_input()
