from __future__ import annotations

import pytest

from databricks_mcp_agent_hello_world.providers import base, factory
from databricks_mcp_agent_hello_world.providers.composite import CompositeToolProvider
from databricks_mcp_agent_hello_world.providers.local_python import LocalPythonToolProvider
from databricks_mcp_agent_hello_world.tools.runtime import RuntimeTool, ToolSource, ToolSourceType
from tests.helpers import make_settings


def test_local_python_provider_executes_registered_builtin_tool() -> None:
    provider = LocalPythonToolProvider()
    tools_list = provider.list_tools()

    assert tools_list[0].execute(customer_id="cust_acme")["customer_id"] == "cust_acme"


def test_provider_factory_returns_local_provider_when_only_local_is_enabled() -> None:
    provider = factory.get_tool_provider(
        make_settings(tools={"databricks_mcp": {"enabled": False}})
    )

    assert isinstance(provider, LocalPythonToolProvider)


def test_provider_factory_returns_mcp_provider_when_only_mcp_is_enabled(monkeypatch) -> None:
    class FakeDatabricksMCPToolProvider:
        provider_id = "fake"

        def __init__(self, settings) -> None:
            self.settings = settings

        def list_tools(self):
            return []

    monkeypatch.setattr(factory, "DatabricksMCPToolProvider", FakeDatabricksMCPToolProvider)
    settings = make_settings(
        tools={
            "local_python": {"enabled": False},
            "databricks_mcp": {
                "enabled": True,
                "server": {
                    "name": "uc_functions",
                    "url": "https://example.cloud.databricks.com/api/2.0/mcp/functions/main/demo",
                },
            },
        }
    )

    provider = factory.get_tool_provider(settings)

    assert isinstance(provider, FakeDatabricksMCPToolProvider)
    assert provider.settings is settings


def test_provider_factory_returns_composite_provider_when_both_sources_are_enabled(
    monkeypatch,
) -> None:
    class FakeDatabricksMCPToolProvider:
        provider_id = "uc_functions"

        def __init__(self, settings) -> None:
            self.settings = settings

        def list_tools(self):
            return [
                _runtime_tool(
                    "remote_lookup",
                    source_type="databricks_mcp",
                    source_id="uc_functions",
                )
            ]

    monkeypatch.setattr(factory, "DatabricksMCPToolProvider", FakeDatabricksMCPToolProvider)
    provider = factory.get_tool_provider(
        make_settings(
            tools={
                "databricks_mcp": {
                    "enabled": True,
                    "server": {
                        "name": "uc_functions",
                        "url": (
                            "https://example.cloud.databricks.com/api/2.0/mcp/functions/main/demo"
                        ),
                    },
                }
            }
        )
    )

    assert provider.provider_id == "composite:local_python,uc_functions"
    assert "lookup_customer" in {tool.name for tool in provider.list_tools()}
    assert "remote_lookup" in {tool.name for tool in provider.list_tools()}


def test_provider_factory_rejects_zero_enabled_sources() -> None:
    with pytest.raises(ValueError, match="At least one tool source"):
        factory.get_tool_provider(
            make_settings(
                tools={
                    "local_python": {"enabled": False},
                    "databricks_mcp": {"enabled": False},
                }
            )
        )


def test_composite_provider_discovers_tools_from_all_sources_and_delegates_execution() -> None:
    local_calls = []
    mcp_calls = []
    provider = CompositeToolProvider(
        [
            _StaticProvider(
                "local_python",
                [
                    _runtime_tool(
                        "local_lookup",
                        source_type="local_python",
                        source_id="local_python",
                        calls=local_calls,
                    )
                ],
            ),
            _StaticProvider(
                "uc_functions",
                [
                    _runtime_tool(
                        "remote_lookup",
                        source_type="databricks_mcp",
                        source_id="uc_functions",
                        calls=mcp_calls,
                    )
                ],
            ),
        ]
    )

    tools = provider.list_tools()

    assert provider.provider_id == "composite:local_python,uc_functions"
    assert [tool.name for tool in tools] == ["local_lookup", "remote_lookup"]
    assert tools[0].execute(value="a") == {"source": "local_python", "arguments": {"value": "a"}}
    assert tools[1].execute(value="b") == {"source": "databricks_mcp", "arguments": {"value": "b"}}
    assert local_calls == [{"value": "a"}]
    assert mcp_calls == [{"value": "b"}]


def test_composite_provider_caches_discovered_tools_and_returns_copies() -> None:
    child_provider = _StaticProvider(
        "local_python",
        [_runtime_tool("local_lookup", source_type="local_python")],
    )
    provider = CompositeToolProvider([child_provider])

    first_tools = provider.list_tools()
    first_tools.clear()
    second_tools = provider.list_tools()

    assert child_provider.list_calls == 1
    assert [tool.name for tool in second_tools] == ["local_lookup"]


def test_composite_provider_rejects_duplicate_tool_names() -> None:
    provider = CompositeToolProvider(
        [
            _StaticProvider(
                "local_python",
                [_runtime_tool("lookup_customer", source_type="local_python")],
            ),
            _StaticProvider(
                "uc_functions",
                [_runtime_tool("lookup_customer", source_type="databricks_mcp")],
            ),
        ]
    )

    with pytest.raises(
        ValueError,
        match="Duplicate tool name 'lookup_customer' from local_python and uc_functions",
    ):
        provider.list_tools()


def test_base_tool_provider_requires_subclasses_to_implement_list_tools() -> None:
    class DummyProvider(base.ToolProvider):
        provider_id = "dummy"

        def list_tools(self):
            return super().list_tools()

    with pytest.raises(NotImplementedError):
        DummyProvider().list_tools()


class _StaticProvider(base.ToolProvider):
    def __init__(self, provider_id: str, tools: list[RuntimeTool]) -> None:
        self.provider_id = provider_id
        self.tools = tools
        self.list_calls = 0

    def list_tools(self) -> list[RuntimeTool]:
        self.list_calls += 1
        return self.tools


def _runtime_tool(
    name: str,
    *,
    source_type: ToolSourceType,
    source_id: str = "source",
    calls: list[dict[str, object]] | None = None,
) -> RuntimeTool:
    def _execute(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        return {"source": source_type, "arguments": kwargs}

    return RuntimeTool(
        name=name,
        spec={
            "type": "function",
            "function": {
                "name": name,
                "description": f"{name} description",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        execute=_execute,
        source=ToolSource(type=source_type, id=source_id),
    )
