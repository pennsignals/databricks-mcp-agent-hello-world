from databricks_mcp_agent_hello_world.providers.local_python import LocalPythonToolProvider


def test_local_provider_lists_tools():
    provider = LocalPythonToolProvider()
    tools = provider.list_tools()
    assert [tool.tool_name for tool in tools] == [
        "greet_user",
        "search_demo_handbook",
        "get_demo_setting",
        "tell_demo_joke",
    ]


def test_inventory_hash_is_stable():
    provider = LocalPythonToolProvider()
    assert provider.inventory_hash() == provider.inventory_hash()
