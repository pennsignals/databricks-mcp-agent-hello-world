from __future__ import annotations

from pathlib import Path

from databricks_tool_agent_template.cli import (
    print_discovery_report,
    print_json_report,
)
from databricks_tool_agent_template.config import load_settings
from databricks_tool_agent_template.discovery import discover_tools
from tests.conftest import write_workspace_config
from tests.helpers import make_settings


def test_discover_tools_returns_current_app_inventory(tmp_path: Path) -> None:
    settings = load_settings(str(write_workspace_config(tmp_path)))

    report = discover_tools(settings)

    assert report.enabled_tool_sources == ["local_python"]
    assert report.provider_id == "local_python"
    assert report.tool_count == 2
    assert [tool.name for tool in report.tools] == [
        "lookup_customer",
        "create_support_ticket",
    ]
    assert {tool.source_type for tool in report.tools} == {"local_python"}


def test_discovery_json_output_matches_runtime_shape(tmp_path: Path, capsys) -> None:
    report = discover_tools(load_settings(str(write_workspace_config(tmp_path))))

    print_json_report(report)
    output = capsys.readouterr().out

    assert '"enabled_tool_sources": [' in output
    assert '"local_python"' in output
    assert '"tool_count": 2' in output


def test_discovery_reports_enabled_sources_even_when_no_tools_are_returned(monkeypatch) -> None:
    class EmptyProvider:
        provider_id = "empty"

        def list_tools(self):
            return []

    monkeypatch.setattr(
        "databricks_tool_agent_template.discovery.get_tool_provider",
        lambda settings: EmptyProvider(),
    )
    settings = make_settings(
        tools={
            "databricks_mcp": {
                "enabled": True,
                "server": {
                    "name": "uc_functions",
                    "url": "https://example.cloud.databricks.com/api/2.0/mcp/functions/main/demo",
                },
            }
        }
    )

    report = discover_tools(settings)

    assert report.enabled_tool_sources == ["local_python", "databricks_mcp"]
    assert report.tool_count == 0


def test_print_discovery_report_surfaces_contract_metadata(tmp_path: Path, capsys) -> None:
    report = discover_tools(load_settings(str(write_workspace_config(tmp_path))))

    print_discovery_report(report)
    output = capsys.readouterr().out

    assert "Source: local_python/local_python" in output
    assert "Input schema:" in output
    assert "Side effect level" not in output
