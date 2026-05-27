from __future__ import annotations

import pytest

from databricks_mcp_agent_hello_world.providers.local_python import LocalPythonToolProvider
from databricks_mcp_agent_hello_world.tools.runtime import inventory_hash
from databricks_mcp_agent_hello_world.tools.validation import ToolInputValidationError


def test_local_python_provider_returns_runtime_tools_matching_local_registry() -> None:
    provider = LocalPythonToolProvider()
    tools = provider.list_tools()

    assert [tool.name for tool in tools] == [
        "lookup_customer",
        "create_support_ticket",
    ]
    assert all(tool.source.type == "local_python" for tool in tools)
    assert all(tool.source.id == "local_python" for tool in tools)
    assert all(tool.spec["function"]["name"] == tool.name for tool in tools)


def test_inventory_hash_is_stable_for_the_same_inventory() -> None:
    provider = LocalPythonToolProvider()

    assert inventory_hash(provider.list_tools()) == inventory_hash(provider.list_tools())


def test_local_python_provider_invokes_lookup_customer() -> None:
    provider = LocalPythonToolProvider()

    assert (
        provider.invoke_tool("lookup_customer", {"customer_id": "cust_acme"})["name"] == "Acme Co"
    )


def test_local_python_provider_validates_arguments_before_invocation() -> None:
    provider = LocalPythonToolProvider()

    with pytest.raises(ToolInputValidationError, match="Additional properties"):
        provider.invoke_tool(
            "lookup_customer",
            {"customer_id": "cust_acme", "extra": "ignored"},
        )


def test_local_python_provider_invokes_create_support_ticket() -> None:
    provider = LocalPythonToolProvider()

    assert (
        provider.invoke_tool(
            "create_support_ticket",
            {"summary": "Need help with onboarding"},
        )["status"]
        == "created"
    )


def test_local_python_provider_rejects_unknown_tool() -> None:
    provider = LocalPythonToolProvider()

    with pytest.raises(ValueError, match="Unknown local tool: missing"):
        provider.invoke_tool("missing", {})
