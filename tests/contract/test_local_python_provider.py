from __future__ import annotations

from databricks_mcp_agent_hello_world.providers.local_python import LocalPythonToolProvider
from databricks_mcp_agent_hello_world.tools.runtime import RuntimeTool, ToolSource, inventory_hash


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


def test_local_python_provider_accepts_injected_runtime_registry() -> None:
    custom_tool = _runtime_tool("custom_tool")
    injected_registry = {"custom_tool": custom_tool}
    provider = LocalPythonToolProvider(tool_registry=injected_registry)

    injected_registry["other_tool"] = _runtime_tool("other_tool")

    assert provider.list_tools() == [custom_tool]


def _runtime_tool(name: str) -> RuntimeTool:
    return RuntimeTool(
        name=name,
        spec={
            "type": "function",
            "function": {
                "name": name,
                "description": f"{name} description",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        execute=dict,
        source=ToolSource(type="local_python", id="local_python"),
    )
