from pathlib import Path

from databricks_mcp_agent_hello_world.cli import print_discovery_report, print_json_report
from databricks_mcp_agent_hello_world.config import load_settings
from databricks_mcp_agent_hello_world.discovery import discover_tools


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "workspace-config.yml"
    config_path.write_text(
        "\n".join(
            [
                "llm_endpoint_name: endpoint-a",
                "tool_provider_type: local_python",
                "databricks_config_profile: DEFAULT",
                "storage:",
                "  agent_events_table: main.agent.agent_events",
                "  local_data_dir: ./.local_state",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def test_discover_tools_returns_demo_registry_tools(tmp_path: Path) -> None:
    settings = load_settings(str(_write_config(tmp_path)))

    report = discover_tools(settings)

    assert report.tool_count == 5
    assert [tool.tool_name for tool in report.tools] == [
        "get_user_profile",
        "search_onboarding_docs",
        "get_workspace_setting",
        "list_recent_job_runs",
        "create_support_ticket",
    ]
    assert report.tools[0].capability_tags
    assert report.tools[0].data_domains
    assert report.tools[0].side_effect_level == "read_only"


def test_discover_tools_json_output_matches_runtime_shape(tmp_path: Path, capsys) -> None:
    settings = load_settings(str(_write_config(tmp_path)))

    report = discover_tools(settings)
    print_json_report(report)
    output = capsys.readouterr().out

    assert '"provider_type": "local_python"' in output
    assert '"tool_count": 5' in output


def test_print_discovery_report_shows_metadata(tmp_path: Path, capsys) -> None:
    settings = load_settings(str(_write_config(tmp_path)))
    report = discover_tools(settings)

    print_discovery_report(report)
    output = capsys.readouterr().out

    assert "Side effect level: read_only" in output
    assert "Tags: identity, user_lookup" in output
    assert "Domains: user" in output
