from __future__ import annotations

import ast
import sys
from pathlib import Path
from types import ModuleType

from databricks_tool_agent_template.clients import databricks as db_clients
from tests.helpers import make_settings

FORBIDDEN_CLIENT_IMPORTS = {
    ("databricks.sdk", "WorkspaceClient"),
    ("databricks_openai", "OpenAI"),
    ("databricks_openai", "DatabricksOpenAI"),
}
FORBIDDEN_CLIENT_MODULE_IMPORTS = {"databricks.sdk", "databricks_openai"}


def test_databricks_client_factories_build_sdk_clients_with_shared_workspace_client(
    monkeypatch,
) -> None:
    captured_workspace_client_kwargs: list[dict[str, str]] = []
    captured_openai_workspace_clients: list[object] = []

    class FakeWorkspaceClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.config = SimpleConfig(host=kwargs.get("host"))
            captured_workspace_client_kwargs.append(kwargs)

    class SimpleConfig:
        def __init__(self, host: str | None) -> None:
            self.host = host

    class FakeDatabricksOpenAI:
        def __init__(self, *, workspace_client) -> None:
            self.workspace_client = workspace_client
            captured_openai_workspace_clients.append(workspace_client)

    sdk_module = ModuleType("databricks.sdk")
    sdk_module.WorkspaceClient = FakeWorkspaceClient
    openai_module = ModuleType("databricks_openai")
    openai_module.DatabricksOpenAI = FakeDatabricksOpenAI

    monkeypatch.setitem(sys.modules, "databricks.sdk", sdk_module)
    monkeypatch.setitem(sys.modules, "databricks_openai", openai_module)

    no_profile_or_host = make_settings(databricks_config_profile=None, workspace_host=None)
    profile_only = make_settings(databricks_config_profile="DEFAULT", workspace_host=None)
    host_only = make_settings(databricks_config_profile=None, workspace_host="https://example.com")
    both = make_settings(databricks_config_profile="DEFAULT", workspace_host="https://example.com")

    assert db_clients.get_workspace_client(no_profile_or_host).kwargs == {}
    assert db_clients.get_workspace_client(profile_only).kwargs == {"profile": "DEFAULT"}
    assert db_clients.get_workspace_client(host_only).kwargs == {"host": "https://example.com"}
    assert db_clients.get_workspace_client(both).kwargs == {
        "profile": "DEFAULT",
        "host": "https://example.com",
    }
    assert db_clients.get_openai_client(both).workspace_client.kwargs == {
        "profile": "DEFAULT",
        "host": "https://example.com",
    }
    assert captured_workspace_client_kwargs == [
        {},
        {"profile": "DEFAULT"},
        {"host": "https://example.com"},
        {"profile": "DEFAULT", "host": "https://example.com"},
        {"profile": "DEFAULT", "host": "https://example.com"},
    ]
    assert captured_openai_workspace_clients


def test_databricks_sdk_clients_are_constructed_only_in_shared_client_module(
    repo_root: Path,
) -> None:
    allowed = repo_root / "src" / "databricks_tool_agent_template" / "clients" / "databricks.py"
    offenders: list[str] = []

    # This is a narrow architecture-boundary test: Databricks SDK client
    # construction stays centralized so auth/config behavior has one owner.
    for path in (repo_root / "src" / "databricks_tool_agent_template").rglob("*.py"):
        if path == allowed:
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    if (module, alias.name) in FORBIDDEN_CLIENT_IMPORTS:
                        offenders.append(str(path.relative_to(repo_root)))

            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in FORBIDDEN_CLIENT_MODULE_IMPORTS:
                        offenders.append(str(path.relative_to(repo_root)))

    assert sorted(set(offenders)) == []
