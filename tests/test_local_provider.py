from types import SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world.executors.factory import get_tool_executor
from databricks_mcp_agent_hello_world.providers.factory import get_tool_provider
from databricks_mcp_agent_hello_world.providers.local_python import (
    LocalPythonToolExecutor,
    LocalPythonToolProvider,
)


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


def test_provider_factory_returns_local_python_provider() -> None:
    provider = get_tool_provider(SimpleNamespace(tool_provider_type="local_python"))
    assert isinstance(provider, LocalPythonToolProvider)


def test_executor_factory_returns_local_python_executor() -> None:
    executor = get_tool_executor(
        SimpleNamespace(tool_provider_type="local_python", sql=SimpleNamespace(backend_mode="auto"))
    )
    assert isinstance(executor, LocalPythonToolExecutor)


def test_factories_reject_managed_mcp() -> None:
    with pytest.raises(NotImplementedError):
        get_tool_provider(SimpleNamespace(tool_provider_type="managed_mcp"))
    with pytest.raises(NotImplementedError):
        get_tool_executor(SimpleNamespace(tool_provider_type="managed_mcp"))
