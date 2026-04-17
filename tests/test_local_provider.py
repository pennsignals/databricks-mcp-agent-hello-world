from types import SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world.models import ToolCall
from databricks_mcp_agent_hello_world.providers.factory import get_tool_provider
from databricks_mcp_agent_hello_world.providers.local_python import LocalPythonToolProvider
from databricks_mcp_agent_hello_world.providers.managed_mcp import (
    MANAGED_MCP_NOT_IMPLEMENTED_MESSAGE,
    ManagedMCPToolProvider,
)


def test_local_provider_lists_tools():
    provider = LocalPythonToolProvider()
    tools = provider.list_tools()
    assert [tool.tool_name for tool in tools] == [
        "get_user_profile",
        "search_onboarding_docs",
        "get_workspace_setting",
        "list_recent_job_runs",
        "create_support_ticket",
    ]


def test_inventory_hash_is_stable():
    provider = LocalPythonToolProvider()
    assert provider.inventory_hash() == provider.inventory_hash()


def test_provider_factory_returns_local_python_provider() -> None:
    provider = get_tool_provider(SimpleNamespace(tool_provider_type="local_python"))
    assert isinstance(provider, LocalPythonToolProvider)


def test_local_python_provider_executes_tools_without_touching_sql_config(monkeypatch) -> None:
    settings = SimpleNamespace(tool_provider_type="local_python")
    provider = LocalPythonToolProvider(settings)

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


def test_provider_factory_returns_managed_mcp_provider() -> None:
    provider = get_tool_provider(SimpleNamespace(tool_provider_type="managed_mcp"))

    assert isinstance(provider, ManagedMCPToolProvider)


@pytest.mark.parametrize("method_name", ["list_tools", "inventory_hash"])
def test_managed_mcp_is_explicitly_retained_but_not_implemented(method_name: str) -> None:
    provider = ManagedMCPToolProvider()

    with pytest.raises(NotImplementedError, match="near-term extension point"):
        getattr(provider, method_name)()

    with pytest.raises(NotImplementedError, match="near-term extension point"):
        provider.call_tool(
            ToolCall(
                tool_name="get_user_profile",
                arguments={},
                request_id="req-1",
            )
        )

    assert MANAGED_MCP_NOT_IMPLEMENTED_MESSAGE == (
        "managed_mcp is retained as a near-term extension point but is not implemented yet."
    )
