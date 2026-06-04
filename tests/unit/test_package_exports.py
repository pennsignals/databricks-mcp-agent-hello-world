from __future__ import annotations

import databricks_tool_agent_template as package_root
import databricks_tool_agent_template.tools as tools_package


def test_package_all_exports_runtime_entrypoints() -> None:
    assert package_root.__all__ == [
        "__version__",
        "discover_tools",
        "run_agent_task",
        "run_init_storage",
        "run_preflight",
    ]


def test_tools_all_exports_stable_runtime_surface() -> None:
    assert tools_package.__all__ == [
        "LocalToolDefinition",
        "RuntimeTool",
        "ToolSource",
        "ToolSourceType",
        "inventory_hash",
    ]
