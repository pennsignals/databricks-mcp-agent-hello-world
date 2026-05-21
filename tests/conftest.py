from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from databricks_mcp_agent_hello_world.clients import databricks as db_clients

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"
DEMO_TASK_PATH = EXAMPLES_DIR / "demo_run_task.json"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        path = str(item.path)
        if "/tests/unit/" in path:
            item.add_marker(pytest.mark.unit)
        elif "/tests/contract/" in path:
            item.add_marker(pytest.mark.contract)


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


@pytest.fixture(autouse=True)
def reset_databricks_client_caches() -> Iterator[None]:
    db_clients._cached_config.cache_clear()
    db_clients._cached_workspace_client.cache_clear()
    db_clients._cached_openai_client.cache_clear()
    yield
    db_clients._cached_config.cache_clear()
    db_clients._cached_workspace_client.cache_clear()
    db_clients._cached_openai_client.cache_clear()


@pytest.fixture
def isolated_root_logger() -> Iterator[logging.Logger]:
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level
    try:
        yield root_logger
    finally:
        root_logger.handlers = original_handlers
        root_logger.setLevel(original_level)
