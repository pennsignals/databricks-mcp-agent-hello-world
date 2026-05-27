from __future__ import annotations

import databricks_mcp_agent_hello_world as package_root


def test_package_all_exports_runtime_entrypoints() -> None:
    assert package_root.__all__ == [
        "__version__",
        "discover_tools",
        "run_agent_task",
        "run_init_storage",
    ]
