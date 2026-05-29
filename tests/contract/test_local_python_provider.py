from __future__ import annotations

from databricks_mcp_agent_hello_world.providers.local_python import LocalPythonToolProvider
from databricks_mcp_agent_hello_world.tools.runtime import inventory_hash


def test_local_python_provider_returns_runtime_tools_matching_local_registry() -> None:
    provider = LocalPythonToolProvider()
    tools = provider.list_tools()

    assert [tool.name for tool in tools] == [
        "lookup_customer",
        "create_support_ticket",
    ]
    assert all(tool.source.type == "local_python" for tool in tools)
    assert all(tool.source.id == "local_python" for tool in tools)
    assert all(tool.spec["function"]["name"] == tool.name for tool in tools)


def test_inventory_hash_is_stable_for_the_same_inventory() -> None:
    provider = LocalPythonToolProvider()

    assert inventory_hash(provider.list_tools()) == inventory_hash(provider.list_tools())
