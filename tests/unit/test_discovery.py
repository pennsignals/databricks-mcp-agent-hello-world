from __future__ import annotations

from pathlib import Path

from databricks_mcp_agent_hello_world.cli import (
    print_discovery_report,
    print_json_report,
)
from databricks_mcp_agent_hello_world.config import load_settings
from databricks_mcp_agent_hello_world.discovery import discover_tools
from tests.conftest import write_workspace_config


def test_discover_tools_returns_current_app_inventory(tmp_path: Path) -> None:
    settings = load_settings(str(write_workspace_config(tmp_path)))

    report = discover_tools(settings)

    assert report.provider_type == "local_python"
    assert report.provider_id == "builtin_tools"
    assert report.tool_count == 5
    assert [tool.tool_name for tool in report.tools] == [
        "get_user_profile",
        "search_onboarding_docs",
        "get_workspace_setting",
        "list_recent_job_runs",
        "create_support_ticket",
    ]


def test_discovery_json_output_matches_runtime_shape(tmp_path: Path, capsys) -> None:
    report = discover_tools(load_settings(str(write_workspace_config(tmp_path))))

    print_json_report(report)
    output = capsys.readouterr().out

    assert '"provider_type": "local_python"' in output
    assert '"tool_count": 5' in output


def test_print_discovery_report_surfaces_contract_metadata(tmp_path: Path, capsys) -> None:
    report = discover_tools(load_settings(str(write_workspace_config(tmp_path))))

    print_discovery_report(report)
    output = capsys.readouterr().out

    assert "Side effect level: read_only" in output
    assert "Tags: identity, user_lookup" in output
    assert "Domains: user" in output
