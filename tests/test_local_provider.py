from databricks_mcp_agent_hello_world.providers.local_python import LocalPythonToolProvider


def test_local_provider_lists_tools():
    provider = LocalPythonToolProvider()
    tools = provider.list_tools()
    assert tools
    assert {tool.tool_name for tool in tools} >= {
        "search_incident_kb",
        "search_runbook_sections",
        "lookup_customer_summary",
        "lookup_service_dependencies",
        "get_open_incidents_for_service",
    }


def test_inventory_hash_is_stable():
    provider = LocalPythonToolProvider()
    assert provider.inventory_hash() == provider.inventory_hash()
