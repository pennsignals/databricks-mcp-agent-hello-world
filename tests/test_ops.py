from pathlib import Path

from databricks_mcp_agent_hello_world.models import ToolProfile
from databricks_mcp_agent_hello_world.ops import discover_tools, run_preflight


class StubGateway:
    def __init__(self, settings):
        self.settings = settings

    def get_serving_endpoint(self):
        return {"name": self.settings.llm_endpoint_name}


def test_preflight_returns_pass_with_stubbed_gateway(tmp_path: Path, monkeypatch) -> None:
    filter_prompt = tmp_path / "filter.txt"
    audit_prompt = tmp_path / "audit.txt"
    agent_prompt = tmp_path / "agent.txt"
    config_path = tmp_path / "config.yml"
    local_state = tmp_path / ".local_state"
    filter_prompt.write_text("filter", encoding="utf-8")
    audit_prompt.write_text("audit", encoding="utf-8")
    agent_prompt.write_text("agent", encoding="utf-8")
    config_path.write_text(
        "\n".join(
            [
                "llm_endpoint_name: endpoint-a",
                "tool_provider_type: local_python",
                "active_profile_name: default",
                f"tool_filter_prompt_path: {filter_prompt}",
                f"tool_audit_prompt_path: {audit_prompt}",
                f"agent_system_prompt_path: {agent_prompt}",
                "storage:",
                "  tool_profiles_table: main.agent.tool_profiles",
                "  agent_runs_table: main.agent.agent_runs",
                "  agent_outputs_table: main.agent.agent_outputs",
                f"  local_data_dir: {local_state}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.DatabricksWorkspaceGateway",
        StubGateway,
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.Config",
        lambda **_: object(),
    )

    from databricks_mcp_agent_hello_world.config import load_settings

    report = run_preflight(load_settings(str(config_path)))

    assert report.overall_status == "pass"
    assert any(check.name == "tool_registry" and check.status == "pass" for check in report.checks)


def test_discover_tools_includes_active_profile(tmp_path: Path, monkeypatch) -> None:
    from databricks_mcp_agent_hello_world.config import load_settings

    filter_prompt = tmp_path / "filter.txt"
    audit_prompt = tmp_path / "audit.txt"
    agent_prompt = tmp_path / "agent.txt"
    config_path = tmp_path / "config.yml"
    local_state = tmp_path / ".local_state"
    filter_prompt.write_text("filter", encoding="utf-8")
    audit_prompt.write_text("audit", encoding="utf-8")
    agent_prompt.write_text("agent", encoding="utf-8")
    config_path.write_text(
        "\n".join(
            [
                "llm_endpoint_name: endpoint-a",
                "tool_provider_type: local_python",
                "active_profile_name: default",
                f"tool_filter_prompt_path: {filter_prompt}",
                f"tool_audit_prompt_path: {audit_prompt}",
                f"agent_system_prompt_path: {agent_prompt}",
                "storage:",
                "  tool_profiles_table: main.agent.tool_profiles",
                "  agent_runs_table: main.agent.agent_runs",
                "  agent_outputs_table: main.agent.agent_outputs",
                f"  local_data_dir: {local_state}",
            ]
        ),
        encoding="utf-8",
    )
    settings = load_settings(str(config_path))
    profile = ToolProfile(
        profile_name="default",
        profile_version="v1",
        inventory_hash="hash",
        provider_type="local_python",
        provider_id="builtin_tools",
        llm_endpoint_name="endpoint-a",
        prompt_version="v1",
        discovered_tools=[],
        allowed_tools=[],
        disallowed_tools=[],
        justifications={},
        audit_report_text="audit",
        selection_policy="policy",
    )
    profile_path = Path(settings.storage.local_data_dir) / "active_tool_profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(profile.model_dump_json(), encoding="utf-8")

    report = discover_tools(settings)

    assert report.active_profile is not None
    assert report.inventory_hash
