from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world.providers.databricks_mcp import DatabricksMCPToolProvider
from tests.helpers import make_settings


def _install_fake_databricks_mcp_modules(monkeypatch):
    captured = {"toolkit_calls": []}

    class FakeMcpServerToolkit:
        def __init__(self, *, url, name, workspace_client) -> None:
            self.url = url
            self.name = name
            self.workspace_client = workspace_client
            captured["toolkit_calls"].append(
                {
                    "url": url,
                    "name": name,
                    "workspace_client": workspace_client,
                }
            )

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
    return captured


def test_databricks_mcp_provider_uses_shared_workspace_client(monkeypatch) -> None:
    captured = _install_fake_databricks_mcp_modules(monkeypatch)
    workspace_client = object()
    workspace_client_calls = []
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.providers.databricks_mcp.get_workspace_client",
        lambda settings: workspace_client_calls.append(settings) or workspace_client,
    )
    settings = make_settings(
        databricks_config_profile="dev",
        tools={
            "databricks_mcp": {
                "enabled": True,
                "server": {
                    "name": "uc_functions",
                    "url": "https://example.cloud.databricks.com/api/2.0/mcp/functions/main/demo",
                },
            }
        },
    )

    provider = DatabricksMCPToolProvider(settings)
    tools = provider.list_tools()

    assert provider.provider_id == "uc_functions"
    assert tools[0].name == "uc_functions_lookup"
    assert tools[0].source.type == "databricks_mcp"
    assert tools[0].source.id == "uc_functions"
    assert tools[0].execute(value="x") == {"arguments": {"value": "x"}}
    assert workspace_client_calls == [settings]
    assert captured["toolkit_calls"] == [
        {
            "url": "https://example.cloud.databricks.com/api/2.0/mcp/functions/main/demo",
            "name": "uc_functions",
            "workspace_client": workspace_client,
        }
    ]


def test_databricks_mcp_provider_requires_server_config() -> None:
    with pytest.raises(ValueError, match=r"databricks_mcp requires tools\.databricks_mcp"):
        DatabricksMCPToolProvider(make_settings())
