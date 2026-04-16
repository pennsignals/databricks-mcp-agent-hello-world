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


def test_executor_factory_returns_local_python_executor() -> None:
    executor = get_tool_executor(
        SimpleNamespace(tool_provider_type="local_python", local_tool_backend_mode="auto")
    )
    assert isinstance(executor, LocalPythonToolExecutor)


def test_local_python_executor_does_not_touch_sql_config(monkeypatch) -> None:
    class ExplodingSqlConfig:
        def __getattr__(self, name):
            raise AssertionError("sql config should not be accessed in local_python mode")

    executor = LocalPythonToolExecutor(
        SimpleNamespace(
            tool_provider_type="local_python",
            local_tool_backend_mode="auto",
            sql=ExplodingSqlConfig(),
        )
    )

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.providers.local_python.get_tool_function",
        lambda tool_name: lambda **kwargs: {"tool_name": tool_name, "arguments": kwargs},
    )

    result = executor.call_tool(
        SimpleNamespace(
            tool_name="get_user_profile",
            arguments={"user_id": "usr_ada_01"},
            request_id="req-1",
        )
    )

    assert result.status == "ok"
    assert result.metadata["backend_mode"] == "auto"
    assert "profile_name" not in result.metadata
    assert "profile_version" not in result.metadata


def test_factories_reject_managed_mcp() -> None:
    with pytest.raises(NotImplementedError):
        get_tool_provider(SimpleNamespace(tool_provider_type="managed_mcp"))
    with pytest.raises(NotImplementedError):
        get_tool_executor(SimpleNamespace(tool_provider_type="managed_mcp"))
