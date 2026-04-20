from __future__ import annotations

from tests.helpers import make_settings
from databricks_mcp_agent_hello_world.models import ToolCall
from databricks_mcp_agent_hello_world.providers.factory import get_tool_provider
from databricks_mcp_agent_hello_world.providers.local_python import LocalPythonToolProvider
from databricks_mcp_agent_hello_world.providers.managed_mcp import ManagedMCPToolProvider


def test_local_python_provider_injects_provider_metadata_and_matches_authored_registry() -> None:
    provider = LocalPythonToolProvider()
    tools = provider.list_tools()

    assert [tool.tool_name for tool in tools] == [
        "get_user_profile",
        "search_onboarding_docs",
        "get_workspace_setting",
        "list_recent_job_runs",
        "create_support_ticket",
    ]
    assert all(tool.provider_type == "local_python" for tool in tools)
    assert all(tool.provider_id == "builtin_tools" for tool in tools)


def test_inventory_hash_is_stable_for_the_same_inventory() -> None:
    provider = LocalPythonToolProvider()
    assert provider.inventory_hash() == provider.inventory_hash()


def test_provider_factory_selects_current_provider_types() -> None:
    assert isinstance(
        get_tool_provider(make_settings(tool_provider_type="local_python")),
        LocalPythonToolProvider,
    )
    assert isinstance(
        get_tool_provider(make_settings(tool_provider_type="managed_mcp")),
        ManagedMCPToolProvider,
    )


def test_local_python_provider_executes_tools_with_request_metadata(monkeypatch) -> None:
    provider = LocalPythonToolProvider(make_settings(tool_provider_type="local_python"))
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.providers.local_python.get_tool_function",
        lambda tool_name: lambda **kwargs: {"tool_name": tool_name, "arguments": kwargs},
    )

    result = provider.call_tool(
        ToolCall(
            tool_name="get_user_profile",
            arguments={"user_id": "usr_ada_01"},
            request_id="req-1",
        )
    )

    assert result.status == "ok"
    assert result.metadata == {
        "provider_type": "local_python",
        "request_id": "req-1",
    }
