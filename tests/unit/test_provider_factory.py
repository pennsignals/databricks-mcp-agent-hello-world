from __future__ import annotations

import pytest

from databricks_mcp_agent_hello_world.providers import base, factory
from databricks_mcp_agent_hello_world.providers.local_python import LocalPythonToolProvider
from tests.helpers import make_settings


def test_local_python_provider_executes_registered_builtin_tool() -> None:
    provider = LocalPythonToolProvider(make_settings())
    tools_list = provider.list_tools()

    assert tools_list[0].execute(user_id="usr_ada_01")["user_id"] == "usr_ada_01"


@pytest.mark.parametrize(
    ("tool_provider_type", "message"),
    [
        pytest.param("something-else", "Unsupported tool_provider_type", id="unsupported"),
        pytest.param("managed_mcp", "managed_mcp has been replaced", id="removed-managed-mcp"),
    ],
)
def test_provider_factory_rejects_unsupported_provider_types(
    tool_provider_type: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        factory.get_tool_provider(make_settings(tool_provider_type=tool_provider_type))


def test_base_tool_provider_requires_subclasses_to_implement_list_tools() -> None:
    class DummyProvider(base.ToolProvider):
        provider_type = "dummy"
        provider_id = "dummy"

        def list_tools(self):
            return super().list_tools()

    with pytest.raises(NotImplementedError):
        DummyProvider().list_tools()
