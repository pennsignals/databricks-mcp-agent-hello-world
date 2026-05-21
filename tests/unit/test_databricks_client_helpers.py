from __future__ import annotations

import sys
from types import ModuleType

import pytest

from databricks_mcp_agent_hello_world.clients import databricks as db_clients
from tests.helpers import make_settings


@pytest.mark.parametrize(
    ("settings_kwargs", "expected"),
    [
        pytest.param(
            {"databricks_config_profile": None, "workspace_host": None},
            {},
            id="no-profile-or-host",
        ),
        pytest.param(
            {"databricks_config_profile": "DEFAULT", "workspace_host": None},
            {"profile": "DEFAULT"},
            id="profile-only",
        ),
        pytest.param(
            {"databricks_config_profile": None, "workspace_host": "https://example.com"},
            {"host": "https://example.com"},
            id="host-only",
        ),
        pytest.param(
            {"databricks_config_profile": "DEFAULT", "workspace_host": "https://example.com"},
            {"profile": "DEFAULT", "host": "https://example.com"},
            id="profile-and-host",
        ),
    ],
)
def test_workspace_client_config_kwargs_reflect_configured_auth_context(
    settings_kwargs: dict[str, object],
    expected: dict[str, str],
) -> None:
    assert db_clients._workspace_client_config_kwargs(make_settings(**settings_kwargs)) == expected


def test_databricks_client_factories_build_and_cache_sdk_clients(monkeypatch) -> None:
    captured_workspace_client_configs: list[object] = []
    captured_openai_workspace_clients: list[object] = []

    class FakeConfig:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.host = kwargs.get("host")

    class FakeWorkspaceClient:
        def __init__(self, *, config) -> None:
            self.config = config
            captured_workspace_client_configs.append(config)

    class FakeDatabricksOpenAI:
        def __init__(self, *, workspace_client) -> None:
            self.workspace_client = workspace_client
            captured_openai_workspace_clients.append(workspace_client)

    sdk_module = ModuleType("databricks.sdk")
    sdk_module.WorkspaceClient = FakeWorkspaceClient
    sdk_config_module = ModuleType("databricks.sdk.config")
    sdk_config_module.Config = FakeConfig
    openai_module = ModuleType("databricks_openai")
    openai_module.DatabricksOpenAI = FakeDatabricksOpenAI

    monkeypatch.setitem(sys.modules, "databricks.sdk", sdk_module)
    monkeypatch.setitem(sys.modules, "databricks.sdk.config", sdk_config_module)
    monkeypatch.setitem(sys.modules, "databricks_openai", openai_module)

    no_profile_or_host = make_settings(databricks_config_profile=None, workspace_host=None)
    profile_only = make_settings(databricks_config_profile="DEFAULT", workspace_host=None)
    host_only = make_settings(databricks_config_profile=None, workspace_host="https://example.com")
    both = make_settings(databricks_config_profile="DEFAULT", workspace_host="https://example.com")

    assert db_clients.get_workspace_client(no_profile_or_host).config.kwargs == {}
    assert db_clients.get_workspace_client(profile_only).config.kwargs == {"profile": "DEFAULT"}
    assert db_clients.get_workspace_client(host_only).config.kwargs == {
        "host": "https://example.com"
    }
    assert db_clients.get_workspace_client(both).config.kwargs == {
        "profile": "DEFAULT",
        "host": "https://example.com",
    }
    assert db_clients.get_openai_client(both).workspace_client.config.kwargs == {
        "profile": "DEFAULT",
        "host": "https://example.com",
    }
    assert len(captured_workspace_client_configs) == 4
    assert captured_openai_workspace_clients
