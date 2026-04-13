from pathlib import Path
from types import SimpleNamespace

from databricks_mcp_agent_hello_world.config import load_settings
from databricks_mcp_agent_hello_world.ops import discover_tools, run_hello_world_demo, run_preflight


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

    class StubRepo:
        def __init__(self, settings):
            self.settings = settings

        def load_active(self, profile_name):
            return None

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.get_spark_session",
        lambda: None,
    )
    monkeypatch.setattr("databricks_mcp_agent_hello_world.ops.ToolProfileRepository", StubRepo)

    report = run_preflight(str(config_path))

    assert report.overall_status == "pass"
    assert report.has_active_profile is False
    assert report.can_compile_profile is True
    assert [check.name for check in report.checks] == [
        "config_file",
        "dotenv",
        "databricks_profile",
        "databricks_client",
        "llm_endpoint_name",
        "provider_factory",
        "tool_registry_nonempty",
        "persistence_targets",
        "persistence_reachability",
        "active_profile",
        "compile_capability",
    ]


def test_preflight_does_not_fail_solely_for_missing_active_profile(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)

    class StubRepo:
        def __init__(self, settings):
            self.settings = settings

        def load_active(self, profile_name):
            return None

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.get_spark_session",
        lambda: None,
    )
    monkeypatch.setattr("databricks_mcp_agent_hello_world.ops.ToolProfileRepository", StubRepo)

    report = run_preflight(str(config_path))

    assert report.overall_status == "pass"
    assert any(
        check.name == "active_profile"
        and check.details.get("has_active_profile") is False
        for check in report.checks
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

    assert report.tool_count == 4
    assert [tool.tool_name for tool in report.tools] == [
        "greet_user",
        "search_demo_handbook",
        "get_demo_setting",
        "tell_demo_joke",
    ]


def test_run_hello_world_demo_orchestrates_discover_and_run(tmp_path: Path, monkeypatch) -> None:
    settings = load_settings(str(_write_config(tmp_path)))
    calls = []

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.discover_tools",
        lambda passed_settings: calls.append(("discover", passed_settings)) or SimpleNamespace(),
    )

    class StubRunner:
        def __init__(self, passed_settings):
            assert passed_settings == settings

        def run(self, task):
            calls.append(("run", task.task_name))
            return {"task_name": task.task_name}

    monkeypatch.setattr("databricks_mcp_agent_hello_world.ops.AgentRunner", StubRunner)

    result = run_hello_world_demo(settings)

    assert result == {"task_name": "hello_world_demo"}
    assert calls == [("discover", settings), ("run", "hello_world_demo")]
