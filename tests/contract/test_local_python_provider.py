from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world.config import MCPConfig, MCPServerConfig
from databricks_mcp_agent_hello_world.providers import factory
from databricks_mcp_agent_hello_world.providers.databricks_mcp import DatabricksMCPToolProvider
from databricks_mcp_agent_hello_world.providers.factory import get_tool_provider
from databricks_mcp_agent_hello_world.providers.local_python import LocalPythonToolProvider
from databricks_mcp_agent_hello_world.tools.runtime import inventory_hash
from tests.helpers import make_settings


def test_local_python_provider_returns_runtime_tools_matching_local_registry() -> None:
    provider = LocalPythonToolProvider()
    tools = provider.list_tools()

    assert [tool.name for tool in tools] == [
        "get_user_profile",
        "search_onboarding_docs",
        "get_workspace_setting",
        "list_recent_job_runs",
        "create_support_ticket",
    ]
    assert all(tool.source.type == "local_python" for tool in tools)
    assert all(tool.source.id == "builtin_tools" for tool in tools)
    assert all(tool.spec["function"]["name"] == tool.name for tool in tools)


def test_inventory_hash_is_stable_for_the_same_inventory() -> None:
    provider = LocalPythonToolProvider()
    assert inventory_hash(provider.list_tools()) == inventory_hash(provider.list_tools())


def test_provider_factory_selects_current_provider_types() -> None:
    assert isinstance(
        get_tool_provider(make_settings(tool_provider_type="local_python")),
        LocalPythonToolProvider,
    )


def test_provider_factory_selects_databricks_mcp_provider(monkeypatch) -> None:
    captured_settings = []

    class FakeDatabricksMCPToolProvider:
        provider_type = "databricks_mcp"
        provider_id = "fake"

        def __init__(self, settings) -> None:
            captured_settings.append(settings)

        def list_tools(self):
            return []

    monkeypatch.setattr(
        factory,
        "DatabricksMCPToolProvider",
        FakeDatabricksMCPToolProvider,
    )
    settings = make_settings(
        tool_provider_type="databricks_mcp",
        mcp=MCPConfig(
            server=MCPServerConfig(
                name="uc_functions",
                url="https://example.cloud.databricks.com/api/2.0/mcp/functions/main/demo",
            )
        ),
    )

    provider = get_tool_provider(settings)

    assert isinstance(provider, FakeDatabricksMCPToolProvider)
    assert captured_settings == [settings]


def test_provider_factory_rejects_old_managed_mcp_value() -> None:
    try:
        get_tool_provider(make_settings(tool_provider_type="managed_mcp"))
    except ValueError as exc:
        assert "managed_mcp has been replaced by databricks_mcp" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("managed_mcp should fail fast")


def test_databricks_mcp_provider_adapts_toolkit_tools(monkeypatch) -> None:
    class FakeMcpServerToolkit:
        def __init__(self, *, url, name) -> None:
            self.url = url
            self.name = name

        def get_tools(self):
            return [
                SimpleNamespace(
                    name="uc_functions_lookup",
                    spec={"type": "function", "function": {"name": "uc_functions_lookup"}},
                    execute=lambda **kwargs: {"arguments": kwargs},
                )
            ]

    openai_module = ModuleType("databricks_openai")
    openai_module.McpServerToolkit = FakeMcpServerToolkit
    monkeypatch.setitem(sys.modules, "databricks_openai", openai_module)

    provider = DatabricksMCPToolProvider(
        make_settings(
            tool_provider_type="databricks_mcp",
            mcp=MCPConfig(
                server=MCPServerConfig(
                    name="uc_functions",
                    url="https://example.cloud.databricks.com/api/2.0/mcp/functions/main/demo",
                )
            ),
        )
    )
    tools = provider.list_tools()

    assert provider.provider_type == "databricks_mcp"
    assert provider.provider_id == "uc_functions"
    assert tools[0].name == "uc_functions_lookup"
    assert tools[0].source.type == "databricks_mcp"
    assert tools[0].source.id == "uc_functions"
    assert tools[0].execute(value="x") == {"arguments": {"value": "x"}}


def test_databricks_mcp_provider_requires_server_config() -> None:
    with pytest.raises(ValueError, match="databricks_mcp requires mcp.server.url"):
        DatabricksMCPToolProvider(make_settings(tool_provider_type="databricks_mcp"))
