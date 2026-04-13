from pathlib import Path
from types import SimpleNamespace

from databricks_mcp_agent_hello_world.config import load_settings
from databricks_mcp_agent_hello_world.ops import discover_tools, run_preflight


def _write_config(tmp_path: Path, *, include_profile: bool = True) -> Path:
    lines = [
        "llm_endpoint_name: endpoint-a",
        "tool_provider_type: local_python",
        "active_profile_name: default",
        "storage:",
        "  tool_profile_table: main.agent.tool_profiles",
        "  agent_runs_table: main.agent.agent_runs",
        "  agent_output_table: main.agent.agent_outputs",
    ]
    if include_profile:
        lines.insert(3, "databricks_config_profile: DEFAULT")
    config_path = tmp_path / "workspace-config.yml"
    config_path.write_text("\n".join(lines), encoding="utf-8")
    return config_path


def test_preflight_returns_pass_with_stubbed_client(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )

    report = run_preflight(str(config_path))

    assert report.overall_status == "pass"
    assert [check.name for check in report.checks] == [
        "config_file",
        "dotenv",
        "databricks_profile",
        "databricks_client",
        "llm_endpoint_name",
        "tool_registry_import",
        "tool_registry_nonempty",
        "tool_provider_type",
        "persistence_targets",
    ]


def test_preflight_fails_fast_when_profile_is_missing(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path, include_profile=False)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )

    report = run_preflight(str(config_path))

    assert report.overall_status == "fail"
    assert any(
        check.name == "databricks_profile" and check.status == "fail" for check in report.checks
    )


def test_preflight_fails_when_profile_is_invalid(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)

    def _raise_invalid_profile(settings):
        raise ValueError("profile DEFAULT is not configured")

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.get_workspace_client",
        _raise_invalid_profile,
    )

    report = run_preflight(str(config_path))

    assert report.overall_status == "fail"
    assert any(
        check.name == "databricks_client" and check.status == "fail" for check in report.checks
    )


def test_discover_tools_returns_demo_registry_tools(tmp_path: Path) -> None:
    settings = load_settings(str(_write_config(tmp_path)))

    report = discover_tools(settings)

    assert report.tool_count >= 1
    assert any(tool.tool_name == "search_incident_kb" for tool in report.tools)
